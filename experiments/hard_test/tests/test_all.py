"""Integration tests for the pricing system.

Tests cover calculator, formatter, and validator working together.
Several tests are currently failing.
"""

import pytest
from decimal import Decimal

from src.calculator import Calculator, LineItem, PriceResult
from src.formatter import Formatter
from src.validator import OrderValidator, ValidationError


# =====================================================================
# Calculator tests
# =====================================================================

class TestCalculatorBasic:
    def test_single_item_no_discount(self):
        calc = Calculator()
        item = LineItem("WIDGET", Decimal("10.00"), 5)
        result = calc.add_item(item)
        assert result.subtotal == Decimal("50.00")
        assert result.discount_pct == Decimal("0.00")
        assert result.total == Decimal("50.00")

    def test_volume_discount_20_plus(self):
        calc = Calculator()
        item = LineItem("WIDGET", Decimal("10.00"), 25)
        result = calc.add_item(item)
        assert result.discount_pct == Decimal("0.05")
        assert result.discount_amount == Decimal("12.50")

    def test_cumulative_discount_across_items(self):
        """Second item should get discount based on CUMULATIVE qty."""
        calc = Calculator()
        calc.add_item(LineItem("A", Decimal("10.00"), 15))
        result2 = calc.add_item(LineItem("B", Decimal("10.00"), 10))
        # Cumulative: 15 + 10 = 25 → 5% tier
        assert result2.discount_pct == Decimal("0.05")
        assert result2.breakdown["cumulative_qty"] == 25

    def test_tax_applied_after_discount(self):
        calc = Calculator()
        item = LineItem("WIDGET", Decimal("100.00"), 1, tax_rate=Decimal("0.10"))
        result = calc.add_item(item)
        assert result.tax == Decimal("10.00")
        assert result.total == Decimal("110.00")

    def test_currency_conversion_eur_to_usd(self):
        """100 EUR should convert to ~108.70 USD."""
        calc = Calculator(target_currency="USD")
        item = LineItem("EU-WIDGET", Decimal("100.00"), 1, currency="EUR")
        result = calc.add_item(item)
        # 100 EUR / 0.92 = ~108.70 USD
        assert result.subtotal > Decimal("108.00")
        assert result.subtotal < Decimal("109.00")

    def test_currency_conversion_usd_to_eur(self):
        """100 USD should convert to 92.00 EUR."""
        calc = Calculator(target_currency="EUR")
        item = LineItem("US-WIDGET", Decimal("100.00"), 1, currency="USD")
        result = calc.add_item(item)
        assert result.subtotal == Decimal("92.00")

    def test_currency_roundtrip(self):
        """Converting USD→EUR→USD should return approximately the original."""
        calc_to_eur = Calculator(target_currency="EUR")
        r1 = calc_to_eur.add_item(LineItem("X", Decimal("100.00"), 1, currency="USD"))

        calc_to_usd = Calculator(target_currency="USD")
        r2 = calc_to_usd.add_item(LineItem("Y", r1.subtotal, 1, currency="EUR"))

        # Should be close to original $100
        assert abs(r2.subtotal - Decimal("100.00")) < Decimal("0.50")

    def test_promo_stacks_with_volume(self):
        calc = Calculator()
        calc.register_promo("SAVE10", 0.10)
        item = LineItem("WIDGET", Decimal("10.00"), 25, promo_code="SAVE10")
        result = calc.add_item(item)
        assert result.discount_pct == Decimal("0.15")

    def test_running_total_matches_sum(self):
        calc = Calculator()
        r1 = calc.add_item(LineItem("A", Decimal("20.00"), 10))
        r2 = calc.add_item(LineItem("B", Decimal("15.00"), 5,
                                     tax_rate=Decimal("0.08")))
        expected = r1.total + r2.total
        assert calc.get_running_total() == expected

    def test_lock_prevents_add(self):
        calc = Calculator()
        calc.lock()
        with pytest.raises(RuntimeError):
            calc.add_item(LineItem("X", Decimal("10.00"), 1))

    def test_reset_clears_cumulative(self):
        calc = Calculator()
        calc.add_item(LineItem("A", Decimal("10.00"), 30))
        calc.reset()
        result = calc.add_item(LineItem("B", Decimal("10.00"), 5))
        assert result.breakdown["cumulative_qty"] == 5
        assert result.discount_pct == Decimal("0.00")

    def test_reset_unlocks(self):
        """After lock + reset, should be able to add items again."""
        calc = Calculator()
        calc.lock()
        calc.reset()
        # Should NOT raise RuntimeError
        result = calc.add_item(LineItem("X", Decimal("10.00"), 1))
        assert result.total == Decimal("10.00")


# =====================================================================
# Formatter tests
# =====================================================================

class TestFormatter:
    def test_single_item_format(self):
        result = PriceResult(
            subtotal=Decimal("100.00"),
            discount_amount=Decimal("5.00"),
            discount_pct=Decimal("0.05"),
            tax=Decimal("9.50"),
            total=Decimal("104.50"),
            currency="USD",
        )
        fmt = Formatter()
        invoice = fmt.format_single(result, "Test Widget")
        assert invoice.grand_total == Decimal("104.50")
        assert len(invoice.lines) == 1
        assert invoice.lines[0].label == "Test Widget"

    def test_batch_format_totals(self):
        results = [
            PriceResult(Decimal("100.00"), Decimal("0"), Decimal("0"),
                       Decimal("10.00"), Decimal("110.00"), "USD"),
            PriceResult(Decimal("50.00"), Decimal("5.00"), Decimal("0.10"),
                       Decimal("4.50"), Decimal("49.50"), "USD"),
        ]
        fmt = Formatter()
        invoice = fmt.format_batch(results, ["Item A", "Item B"])
        assert invoice.grand_total == Decimal("159.50")
        assert len(invoice.lines) == 2

    def test_empty_batch(self):
        fmt = Formatter()
        invoice = fmt.format_batch([])
        assert invoice.grand_total == Decimal("0")

    def test_jpy_no_decimals(self):
        result = PriceResult(
            subtotal=Decimal("14950"),
            discount_amount=Decimal("0"),
            discount_pct=Decimal("0"),
            tax=Decimal("1495"),
            total=Decimal("16445"),
            currency="JPY",
        )
        fmt = Formatter()
        invoice = fmt.format_single(result, "Japanese Widget")
        assert "." not in invoice.total_line
        assert "¥" in invoice.total_line

    def test_cached_invoice(self):
        fmt = Formatter()
        assert fmt.get_last_invoice() is None
        result = PriceResult(
            Decimal("10"), Decimal("0"), Decimal("0"),
            Decimal("0"), Decimal("10"), "USD",
        )
        invoice = fmt.format_single(result)
        assert fmt.get_last_invoice() is invoice

    def test_render_text_no_discount_line(self):
        """When discount is zero, render_text should NOT show a Discount row."""
        result = PriceResult(
            Decimal("100"), Decimal("0"), Decimal("0"),
            Decimal("10"), Decimal("110"), "USD",
        )
        fmt = Formatter()
        invoice = fmt.format_single(result, "Widget")
        text = fmt.render_text(invoice)
        assert "INVOICE" in text
        assert "Discount" not in text

    def test_render_text_with_discount(self):
        result = PriceResult(
            Decimal("100"), Decimal("10"), Decimal("0.10"),
            Decimal("9"), Decimal("99"), "USD",
        )
        fmt = Formatter()
        invoice = fmt.format_single(result, "Widget")
        text = fmt.render_text(invoice)
        assert "Discount" in text


# =====================================================================
# Validator tests
# =====================================================================

class TestValidatorBasic:
    def test_valid_simple_order(self):
        v = OrderValidator("USD")
        items = [LineItem("WIDGET", Decimal("25.00"), 10)]
        result = v.validate(items)
        assert result.valid is True
        assert result.total > Decimal("0")

    def test_empty_order_rejected(self):
        v = OrderValidator()
        result = v.validate([])
        assert result.valid is False
        assert any(e.field == "order" for e in result.errors)

    def test_negative_quantity_rejected(self):
        v = OrderValidator()
        items = [LineItem("X", Decimal("10.00"), -5)]
        result = v.validate(items)
        assert result.valid is False

    def test_negative_price_rejected(self):
        v = OrderValidator()
        items = [LineItem("X", Decimal("-10.00"), 5)]
        result = v.validate(items)
        assert result.valid is False

    def test_unknown_promo_rejected(self):
        v = OrderValidator()
        items = [LineItem("X", Decimal("10.00"), 5, promo_code="FAKE")]
        result = v.validate(items)
        assert result.valid is False
        assert any("promo" in e.field for e in result.errors)

    def test_promo_over_max_raises(self):
        v = OrderValidator()
        with pytest.raises(ValueError, match="exceeds maximum"):
            v.register_promo("HUGE", 0.50)


class TestValidatorEdgeCases:
    def test_max_order_value_rejected(self):
        v = OrderValidator("USD")
        items = [LineItem("EXPENSIVE", Decimal("10000.00"), 10)]
        result = v.validate(items)
        assert result.valid is False
        assert any("exceeds" in e.message for e in result.errors)

    def test_duplicate_product_warning(self):
        v = OrderValidator()
        items = [
            LineItem("WIDGET", Decimal("10.00"), 5),
            LineItem("WIDGET", Decimal("10.00"), 3),
        ]
        result = v.validate(items)
        assert result.valid is True
        assert any("merging" in w.message for w in result.warnings)

    def test_min_quantity_enforced(self):
        v = OrderValidator()
        v.set_min_quantity("BULK", 10)
        items = [LineItem("BULK", Decimal("5.00"), 3)]
        result = v.validate(items)
        assert result.valid is False
        assert any("Minimum" in e.message for e in result.errors)

    def test_tax_rate_over_100_rejected(self):
        v = OrderValidator()
        items = [LineItem("X", Decimal("10.00"), 1, tax_rate=Decimal("1.50"))]
        result = v.validate(items)
        assert result.valid is False

    def test_validator_uses_correct_currency_conversion(self):
        """100 EUR item in USD order should be ~108.70, not 92.00."""
        v = OrderValidator("USD")
        items = [
            LineItem("EU-ITEM", Decimal("100.00"), 1, currency="EUR"),
        ]
        result = v.validate(items)
        assert result.valid is True
        # 100 EUR = ~108.70 USD (dividing by 0.92)
        assert result.total > Decimal("108.00")
        assert result.total < Decimal("109.00")

    def test_promo_with_volume_discount_order(self):
        """Promo + volume discount in validator should work correctly."""
        v = OrderValidator("USD")
        v.register_promo("VIP20", 0.20)
        items = [
            LineItem("A", Decimal("10.00"), 60, promo_code="VIP20"),
        ]
        result = v.validate(items)
        assert result.valid is True
        # qty=60 → 10% volume + 20% promo = 30% total discount
        # Subtotal: 600, discount: 180, after: 420
        assert result.total == Decimal("420.00")
        # Should trigger high discount warning (30% > threshold)
        assert any("unusually high" in w.message for w in result.warnings)

    def test_multi_currency_order_total(self):
        """Mixed USD + EUR order total should be correct."""
        v = OrderValidator("USD")
        items = [
            LineItem("US-ITEM", Decimal("100.00"), 1, currency="USD"),
            LineItem("EU-ITEM", Decimal("100.00"), 1, currency="EUR"),
        ]
        result = v.validate(items)
        assert result.valid is True
        # USD: $100, EUR→USD: ~$108.70, total ~$208.70
        assert result.total > Decimal("200.00")
        assert result.total < Decimal("220.00")

    def test_reset_between_validations(self):
        """Validating twice should give independent results."""
        v = OrderValidator("USD")
        items1 = [LineItem("A", Decimal("10.00"), 50)]
        result1 = v.validate(items1)

        items2 = [LineItem("B", Decimal("10.00"), 5)]
        result2 = v.validate(items2)

        # Second validation should NOT carry cumulative qty from first
        assert result2.total == Decimal("50.00")

    def test_validate_after_lock_reset(self):
        """Validator should work after its internal calculator is locked+reset."""
        v = OrderValidator("USD")
        items1 = [LineItem("A", Decimal("10.00"), 5)]
        v.validate(items1)

        # Internal calc should be reset for next validate call
        items2 = [LineItem("B", Decimal("20.00"), 3)]
        result = v.validate(items2)
        assert result.valid is True
        assert result.total == Decimal("60.00")
