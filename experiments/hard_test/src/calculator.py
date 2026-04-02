"""Multi-currency price calculator with discount tiers.

Handles product pricing across currencies with volume discounts,
tax calculations, and promotional adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


# Exchange rates relative to USD
_RATES: dict[str, Decimal] = {
    "USD": Decimal("1.00"),
    "EUR": Decimal("0.92"),
    "GBP": Decimal("0.79"),
    "JPY": Decimal("149.50"),
    "CAD": Decimal("1.36"),
}

# Discount tiers: (min_quantity, discount_pct)
_TIERS: list[tuple[int, Decimal]] = [
    (100, Decimal("0.15")),
    (50, Decimal("0.10")),
    (20, Decimal("0.05")),
    (1, Decimal("0.00")),
]


@dataclass
class LineItem:
    product_id: str
    unit_price: Decimal
    quantity: int
    currency: str = "USD"
    tax_rate: Decimal = Decimal("0.0")
    promo_code: str = ""


@dataclass
class PriceResult:
    subtotal: Decimal
    discount_amount: Decimal
    discount_pct: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    breakdown: dict[str, Any] = field(default_factory=dict)


class Calculator:
    """Stateful price calculator that accumulates line items.

    The calculator tracks a running total and applies cross-item
    discount logic — a second item's discount tier depends on the
    cumulative quantity of all items added so far.
    """

    def __init__(self, target_currency: str = "USD") -> None:
        if target_currency not in _RATES:
            raise ValueError(f"Unsupported currency: {target_currency}")
        self.target_currency = target_currency
        self._items: list[LineItem] = []
        self._cumulative_qty: int = 0
        self._promo_discounts: dict[str, Decimal] = {}
        self._locked = False

    def register_promo(self, code: str, discount_pct: float) -> None:
        """Register a promotional discount code."""
        if self._locked:
            raise RuntimeError("Cannot modify locked calculator")
        self._promo_discounts[code.upper()] = Decimal(str(discount_pct))

    def add_item(self, item: LineItem) -> PriceResult:
        """Add a line item and return its computed price.

        Discount tier is based on cumulative quantity across ALL items,
        not just this item's quantity.
        """
        if self._locked:
            raise RuntimeError("Cannot add to locked calculator")

        self._cumulative_qty += item.quantity

        converted_price = self._convert(item.unit_price, item.currency)
        subtotal = converted_price * item.quantity

        discount_pct = self._tier_discount(self._cumulative_qty)

        if item.promo_code:
            promo = self._promo_discounts.get(item.promo_code.upper(), Decimal("0"))
            discount_pct = discount_pct + promo

        discount_amount = (subtotal * discount_pct).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        after_discount = subtotal - discount_amount

        tax = (after_discount * item.tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total = after_discount + tax

        result = PriceResult(
            subtotal=subtotal.quantize(Decimal("0.01")),
            discount_amount=discount_amount,
            discount_pct=discount_pct,
            tax=tax,
            total=total.quantize(Decimal("0.01")),
            currency=self.target_currency,
            breakdown={
                "unit_price_converted": converted_price.quantize(Decimal("0.01")),
                "quantity": item.quantity,
                "cumulative_qty": self._cumulative_qty,
                "promo_applied": item.promo_code.upper() if item.promo_code else None,
            },
        )

        self._items.append(item)
        return result

    def get_running_total(self) -> Decimal:
        """Return the sum of all item totals computed so far."""
        total = Decimal("0")
        qty = 0
        for item in self._items:
            qty += item.quantity
            converted = self._convert(item.unit_price, item.currency)
            sub = converted * item.quantity
            disc = self._tier_discount(qty)
            if item.promo_code:
                promo = self._promo_discounts.get(item.promo_code.upper(), Decimal("0"))
                disc = disc + promo
            disc_amt = (sub * disc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            after = sub - disc_amt
            tax = (after * item.tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += after + tax
        return total.quantize(Decimal("0.01"))

    def lock(self) -> None:
        """Lock the calculator — no more items or promo changes."""
        self._locked = True

    def reset(self) -> None:
        """Clear all state and unlock."""
        self._items.clear()
        self._cumulative_qty = 0
        self._locked = False

    def _convert(self, amount: Decimal, from_currency: str) -> Decimal:
        """Convert amount from from_currency to target_currency."""
        if from_currency == self.target_currency:
            return amount
        if from_currency not in _RATES:
            raise ValueError(f"Unknown currency: {from_currency}")
        usd_amount = amount / _RATES[from_currency]
        return usd_amount * _RATES[self.target_currency]

    @staticmethod
    def _tier_discount(cumulative_qty: int) -> Decimal:
        """Return discount percentage for the given cumulative quantity."""
        for min_qty, pct in _TIERS:
            if cumulative_qty >= min_qty:
                return pct
        return Decimal("0")
