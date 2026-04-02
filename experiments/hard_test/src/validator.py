"""Order validator — validates complete orders before submission.

Depends on both calculator and formatter.  Validates business rules
like maximum order value, minimum quantities, currency consistency,
and promotional code constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from src.calculator import Calculator, LineItem, PriceResult
from src.formatter import Formatter, Invoice


_MAX_ORDER_VALUE: dict[str, Decimal] = {
    "USD": Decimal("50000"),
    "EUR": Decimal("45000"),
    "GBP": Decimal("40000"),
    "JPY": Decimal("7000000"),
    "CAD": Decimal("65000"),
}

_MAX_PROMO_DISCOUNT_PCT = Decimal("0.30")


@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    invoice: Invoice | None = None
    total: Decimal = Decimal("0")


class OrderValidator:
    """Validates a complete order by running it through the calculator
    and formatter, then checking business rules.

    Usage:
        validator = OrderValidator("USD")
        validator.register_promo("SAVE10", 0.10)
        result = validator.validate(items)
        if not result.valid:
            for err in result.errors:
                print(f"{err.field}: {err.message}")
    """

    def __init__(self, currency: str = "USD") -> None:
        self.currency = currency
        self._calc = Calculator(target_currency=currency)
        self._fmt = Formatter()
        self._min_quantities: dict[str, int] = {}

    def register_promo(self, code: str, discount_pct: float) -> None:
        """Register a promo code. Validates that discount doesn't exceed max."""
        if Decimal(str(discount_pct)) > _MAX_PROMO_DISCOUNT_PCT:
            raise ValueError(
                f"Promo discount {discount_pct} exceeds maximum "
                f"{_MAX_PROMO_DISCOUNT_PCT}"
            )
        self._calc.register_promo(code, discount_pct)

    def set_min_quantity(self, product_id: str, min_qty: int) -> None:
        """Set minimum order quantity for a product."""
        self._min_quantities[product_id] = min_qty

    def validate(self, items: Sequence[LineItem]) -> ValidationResult:
        """Validate an order of line items.

        Runs all items through the calculator, formats an invoice,
        and checks business rules.  Returns ValidationResult with
        errors/warnings.
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        if not items:
            errors.append(ValidationError("order", "Order must have at least one item"))
            return ValidationResult(valid=False, errors=errors)

        # Reset calculator for fresh order
        self._calc.reset()

        # Check for duplicate product IDs
        seen_products: dict[str, int] = {}
        for item in items:
            seen_products[item.product_id] = seen_products.get(item.product_id, 0) + 1
        for pid, count in seen_products.items():
            if count > 1:
                warnings.append(ValidationError(
                    f"product:{pid}",
                    f"Product {pid} appears {count} times — consider merging",
                    severity="warning",
                ))

        # Validate individual items
        results: list[PriceResult] = []
        labels: list[str] = []
        for i, item in enumerate(items):
            item_errors = self._validate_item(item, i)
            errors.extend(item_errors)

            if not item_errors:
                result = self._calc.add_item(item)
                results.append(result)
                labels.append(f"{item.product_id} x{item.quantity}")

                # Check if combined discount is suspiciously high
                if result.discount_pct > Decimal("0.25"):
                    warnings.append(ValidationError(
                        f"item:{i}",
                        f"Combined discount {result.discount_pct:.0%} is unusually high",
                        severity="warning",
                    ))

        if errors:
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        # Format invoice
        invoice = self._fmt.format_batch(results, labels)

        # Check order-level business rules
        max_value = _MAX_ORDER_VALUE.get(self.currency, Decimal("50000"))
        if invoice.grand_total > max_value:
            errors.append(ValidationError(
                "total",
                f"Order total {invoice.grand_total} exceeds maximum "
                f"{max_value} {self.currency}",
            ))

        if invoice.grand_total <= Decimal("0"):
            errors.append(ValidationError(
                "total",
                "Order total must be positive",
            ))

        # Check minimum quantities
        for item in items:
            min_qty = self._min_quantities.get(item.product_id, 0)
            if min_qty > 0 and item.quantity < min_qty:
                errors.append(ValidationError(
                    f"quantity:{item.product_id}",
                    f"Minimum quantity for {item.product_id} is {min_qty}, "
                    f"got {item.quantity}",
                ))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            invoice=invoice,
            total=invoice.grand_total,
        )

    def _validate_item(self, item: LineItem, index: int) -> list[ValidationError]:
        """Validate a single line item."""
        errors: list[ValidationError] = []

        if item.quantity <= 0:
            errors.append(ValidationError(
                f"item:{index}:quantity",
                f"Quantity must be positive, got {item.quantity}",
            ))

        if item.unit_price < Decimal("0"):
            errors.append(ValidationError(
                f"item:{index}:price",
                f"Price cannot be negative: {item.unit_price}",
            ))

        if item.unit_price == Decimal("0"):
            warnings_list = []
            warnings_list.append(ValidationError(
                f"item:{index}:price",
                "Zero-price item detected",
                severity="warning",
            ))

        if item.tax_rate < Decimal("0") or item.tax_rate > Decimal("1"):
            errors.append(ValidationError(
                f"item:{index}:tax",
                f"Tax rate must be 0-100%, got {item.tax_rate}",
            ))

        if item.promo_code and item.promo_code.upper() not in self._calc._promo_discounts:
            errors.append(ValidationError(
                f"item:{index}:promo",
                f"Unknown promo code: {item.promo_code}",
            ))

        return errors
