"""Invoice formatter — renders PriceResults into display strings.

Depends on calculator.PriceResult structure.  The formatter caches
the last rendered invoice for reprinting and applies locale-specific
number formatting.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from src.calculator import PriceResult


_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CAD": "CA$",
}

_DECIMAL_PLACES: dict[str, int] = {
    "JPY": 0,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CAD": 2,
}


@dataclass(frozen=True)
class InvoiceLine:
    label: str
    amount: str
    raw_amount: Decimal


@dataclass(frozen=True)
class Invoice:
    lines: list[InvoiceLine]
    subtotal_line: str
    discount_line: str
    tax_line: str
    total_line: str
    currency: str
    grand_total: Decimal


class Formatter:
    """Renders PriceResults into human-readable invoice strings.

    Maintains a cache of the last invoice generated so callers can
    re-render without recomputing.
    """

    def __init__(self) -> None:
        self._last_invoice: Invoice | None = None
        self._line_count = 0

    def format_single(self, result: PriceResult, label: str = "") -> Invoice:
        """Format a single PriceResult into an Invoice."""
        return self.format_batch([result], [label] if label else None)

    def format_batch(
        self,
        results: Sequence[PriceResult],
        labels: Sequence[str] | None = None,
    ) -> Invoice:
        """Format multiple PriceResults into one Invoice.

        If labels are provided, they are used as line descriptions.
        Otherwise, lines are numbered sequentially.
        """
        if not results:
            empty = Invoice(
                lines=[],
                subtotal_line=self._fmt_money(Decimal("0"), "USD"),
                discount_line=self._fmt_money(Decimal("0"), "USD"),
                tax_line=self._fmt_money(Decimal("0"), "USD"),
                total_line=self._fmt_money(Decimal("0"), "USD"),
                currency="USD",
                grand_total=Decimal("0"),
            )
            self._last_invoice = empty
            return empty

        currency = results[0].currency
        lines: list[InvoiceLine] = []
        running_subtotal = Decimal("0")
        running_discount = Decimal("0")
        running_tax = Decimal("0")
        running_total = Decimal("0")

        for i, r in enumerate(results):
            lbl = labels[i] if labels and i < len(labels) else f"Item #{i + 1}"
            lines.append(InvoiceLine(
                label=lbl,
                amount=self._fmt_money(r.total, r.currency),
                raw_amount=r.total,
            ))
            running_subtotal += r.subtotal
            running_discount += r.discount_amount
            running_tax += r.tax
            running_total += r.total

        invoice = Invoice(
            lines=lines,
            subtotal_line=self._fmt_money(running_subtotal, currency),
            discount_line=self._fmt_money(running_discount, currency),
            tax_line=self._fmt_money(running_tax, currency),
            total_line=self._fmt_money(running_total, currency),
            currency=currency,
            grand_total=running_total,
        )

        self._last_invoice = invoice
        self._line_count += len(lines)
        return invoice

    def get_last_invoice(self) -> Invoice | None:
        """Return the last generated invoice, or None if no invoice
        has been formatted yet."""
        return self._last_invoice

    def render_text(self, invoice: Invoice | None = None) -> str:
        """Render an Invoice (or the cached one) as a plain-text block."""
        inv = invoice or self._last_invoice
        if inv is None:
            return "(no invoice)"

        width = 50
        out: list[str] = []
        out.append("=" * width)
        out.append("INVOICE".center(width))
        out.append("-" * width)

        for line in inv.lines:
            padding = width - len(line.label) - len(line.amount)
            out.append(f"{line.label}{'.' * max(padding, 1)}{line.amount}")

        out.append("-" * width)
        out.append(f"{'Subtotal':<20}{inv.subtotal_line:>30}")
        if inv.discount_line and inv.discount_line != self._fmt_money(Decimal("0"), inv.currency):
            out.append(f"{'Discount':<20}{'-' + inv.discount_line:>30}")
        out.append(f"{'Tax':<20}{inv.tax_line:>30}")
        out.append("=" * width)
        out.append(f"{'TOTAL':<20}{inv.total_line:>30}")
        out.append("=" * width)

        return "\n".join(out)

    def _fmt_money(self, amount: Decimal, currency: str) -> str:
        """Format a Decimal amount with currency symbol.

        Uses the appropriate number of decimal places for the currency.
        JPY has 0 decimal places; most others have 2.
        """
        sym = _CURRENCY_SYMBOLS.get(currency, currency + " ")
        places = _DECIMAL_PLACES.get(currency, 2)
        if places == 0:
            formatted = f"{int(amount):,}"
        else:
            quantized = amount.quantize(Decimal(10) ** -places)
            formatted = f"{quantized:,}"
        return f"{sym}{formatted}"
