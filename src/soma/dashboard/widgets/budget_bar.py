"""BudgetBar widget — shows budget utilization with color coding."""

from __future__ import annotations

from textual.widgets import Static


class BudgetBar(Static):
    """A static widget displaying a text-based budget utilization bar."""

    DEFAULT_CSS = """
    BudgetBar {
        height: 3;
        background: #141414;
        border: solid #222222;
        padding: 0 2;
        margin: 0 1;
        color: #aaaaaa;
    }
    """

    _BAR_WIDTH = 30

    def __init__(self, dimension: str = "tokens", **kwargs) -> None:
        super().__init__(**kwargs)
        self._dimension = dimension
        self._utilization: float = 0.0
        self._remaining: float = 1.0

    def on_mount(self) -> None:
        self._refresh_bar()

    def update_budget(
        self,
        dimension: str,
        utilization: float,
        remaining: float,
    ) -> None:
        """Refresh the bar display.

        Args:
            dimension:   Budget dimension name (e.g. 'tokens', 'cost_usd').
            utilization: Fraction used, in [0, 1].
            remaining:   Absolute remaining amount.
        """
        self._dimension = dimension
        self._utilization = max(0.0, min(1.0, utilization))
        self._remaining = remaining
        self._refresh_bar()

    def _refresh_bar(self) -> None:
        u = self._utilization
        filled = int(u * self._BAR_WIDTH)
        empty = self._BAR_WIDTH - filled

        if u >= 0.90:
            color = "red"
            color_hex = "#ef4444"
        elif u >= 0.70:
            color = "yellow"
            color_hex = "#eab308"
        else:
            color = "green"
            color_hex = "#22c55e"

        bar_filled = f"[{color_hex}]{'█' * filled}[/{color_hex}]"
        bar_empty = f"[#333333]{'░' * empty}[/#333333]"
        pct = f"{u * 100:.1f}%"
        label = f"{self._dimension:<12} [{bar_filled}{bar_empty}] {pct:>6}  remaining: {self._remaining:.2f}"
        self.update(label)
