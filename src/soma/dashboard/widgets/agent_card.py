"""AgentCard widget — displays one agent's live vitals."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive

from soma.types import Level


# Map Level -> (border color class, label)
_LEVEL_STYLES: dict[str, tuple[str, str]] = {
    "HEALTHY":    ("level--healthy",    "HEALTHY"),
    "CAUTION":    ("level--caution",    "CAUTION"),
    "DEGRADE":    ("level--degrade",    "DEGRADE"),
    "QUARANTINE": ("level--quarantine", "QUARANTINE"),
    "RESTART":    ("level--restart",    "RESTART"),
    "SAFE_MODE":  ("level--safe-mode",  "SAFE MODE"),
}


class AgentCard(Static):
    """A card that shows live vitals for a single agent."""

    DEFAULT_CSS = """
    AgentCard {
        width: 1fr;
        height: auto;
        min-height: 8;
        background: #141414;
        border: solid #22c55e;
        padding: 1 2;
        margin: 1;
    }
    AgentCard.level--healthy    { border: solid #22c55e; }
    AgentCard.level--caution    { border: solid #eab308; }
    AgentCard.level--degrade    { border: solid #f97316; }
    AgentCard.level--quarantine { border: solid #ef4444; }
    AgentCard.level--restart    { border: solid #a855f7; }
    AgentCard.level--safe-mode  { border: solid #ef4444; }

    AgentCard .card-title {
        text-style: bold;
        color: #e5e5e5;
    }
    AgentCard .card-level {
        text-style: bold;
    }
    AgentCard .level--healthy    { color: #22c55e; }
    AgentCard .level--caution    { color: #eab308; }
    AgentCard .level--degrade    { color: #f97316; }
    AgentCard .level--quarantine { color: #ef4444; }
    AgentCard .level--restart    { color: #a855f7; }
    AgentCard .level--safe-mode  { color: #ef4444; }

    AgentCard .card-metric {
        color: #888888;
    }
    AgentCard .card-metric-value {
        color: #cccccc;
    }
    """

    def __init__(self, agent_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._agent_id = agent_id
        self._level: str = "HEALTHY"
        self._pressure: float = 0.0
        self._uncertainty: float = 0.0
        self._drift: float = 0.0
        self._error_rate: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static(self._agent_id, classes="card-title")
        yield Static("", id=f"card-level-{self._agent_id}")
        yield Static("", id=f"card-pressure-{self._agent_id}")
        yield Static("", id=f"card-uncertainty-{self._agent_id}")
        yield Static("", id=f"card-drift-{self._agent_id}")
        yield Static("", id=f"card-error-rate-{self._agent_id}")

    def on_mount(self) -> None:
        self._refresh_display()

    def update_vitals(
        self,
        level: Level | str,
        pressure: float,
        uncertainty: float,
        drift: float,
        error_rate: float,
    ) -> None:
        """Refresh all vitals on this card."""
        self._level = level.name if isinstance(level, Level) else str(level)
        self._pressure = pressure
        self._uncertainty = uncertainty
        self._drift = drift
        self._error_rate = error_rate
        self._refresh_display()

    def _refresh_display(self) -> None:
        level_key = self._level
        css_class, label = _LEVEL_STYLES.get(level_key, ("level--healthy", level_key))

        # Update border class on self
        for cls in _LEVEL_STYLES.values():
            self.remove_class(cls[0])
        self.add_class(css_class)

        safe_id = self._agent_id

        level_widget = self.query_one(f"#card-level-{safe_id}", Static)
        level_widget.update(f"Level: [{css_class}]{label}[/{css_class}]")

        pressure_widget = self.query_one(f"#card-pressure-{safe_id}", Static)
        pressure_widget.update(f"Pressure:    {self._pressure:.3f}")

        uncertainty_widget = self.query_one(f"#card-uncertainty-{safe_id}", Static)
        uncertainty_widget.update(f"Uncertainty: {self._uncertainty:.3f}")

        drift_widget = self.query_one(f"#card-drift-{safe_id}", Static)
        drift_widget.update(f"Drift:       {self._drift:.3f}")

        error_widget = self.query_one(f"#card-error-rate-{safe_id}", Static)
        error_widget.update(f"Error Rate:  {self._error_rate:.3f}")
