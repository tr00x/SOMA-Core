"""SOMA Hub — Config Tab (Tab 4).

Displays current soma.toml values in editable fields grouped by category.
Save button writes changes back.  Preview shows effect of threshold changes
if thresholds changed.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Static, Input, Button, Rule, TabPane

from soma.cli.config_loader import load_config, save_config, DEFAULT_CONFIG, CLAUDE_CODE_CONFIG
from soma.types import ResponseMode
from soma.guidance import pressure_to_mode


MODE_COLORS = {
    ResponseMode.OBSERVE:  "#22c55e",
    ResponseMode.GUIDE:    "#eab308",
    ResponseMode.WARN:     "#f97316",
    ResponseMode.BLOCK:    "#ef4444",
}

# Example pressure for threshold preview
_PREVIEW_PRESSURE: float = 0.42


# ── ConfigTab ────────────────────────────────────────────────────

class ConfigTab(TabPane):
    """Tab 4 — editable soma.toml with save and live preview."""

    DEFAULT_CSS = """
    ConfigTab {
        layout: vertical;
    }
    #config-scroll {
        height: 1fr;
    }
    #config-inner {
        layout: vertical; padding: 1 2;
    }
    .config-section-title {
        height: 2; color: #58a6ff; padding: 1 0 0 0;
    }
    .config-row {
        layout: horizontal; height: 3; margin: 0 0 0 0;
    }
    .config-label {
        width: 28; padding: 1 0; color: #ccc;
    }
    .config-input {
        width: 20;
    }
    #config-preview {
        height: 4; background: #0d1117; border: round #444; padding: 1 2;
        margin: 1 0;
    }
    #config-btn-row {
        layout: horizontal; height: 5; padding: 1 2; background: #111;
    }
    #config-save-btn { width: 16; margin-right: 1; }
    #config-reload-btn { width: 18; }
    #config-status {
        height: 3; background: #0a0a0a; padding: 1 2; color: #666;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save_config", "Save"),
    ]

    def __init__(self) -> None:
        super().__init__("Config", id="tab-config")
        self._config: dict[str, Any] = self._load_effective_config()

    @staticmethod
    def _load_effective_config() -> dict[str, Any]:
        """Load config from soma.toml, falling back to engine_state.json,
        then CLAUDE_CODE_CONFIG defaults. This ensures the Config tab shows
        the actual values the engine is using, not just DEFAULT_CONFIG."""
        import os
        if os.path.exists("soma.toml"):
            return load_config()

        # No soma.toml — try to read from engine state
        try:
            from soma.hooks.common import ENGINE_STATE_PATH
            if ENGINE_STATE_PATH.exists():
                import json
                state = json.loads(ENGINE_STATE_PATH.read_text())
                cfg = dict(CLAUDE_CODE_CONFIG)
                if state.get("custom_thresholds"):
                    cfg["thresholds"] = state["custom_thresholds"]
                if state.get("custom_weights"):
                    cfg["weights"] = state["custom_weights"]
                if state.get("budget", {}).get("limits"):
                    cfg["budget"] = state["budget"]["limits"]
                return cfg
        except Exception:
            pass

        return CLAUDE_CODE_CONFIG

    # ── Compose ──────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        cfg = self._config
        th = cfg.get("thresholds", DEFAULT_CONFIG["thresholds"])
        wt = cfg.get("weights",    DEFAULT_CONFIG["weights"])
        bud = cfg.get("budget",    DEFAULT_CONFIG["budget"])
        gr = cfg.get("graph",      DEFAULT_CONFIG["graph"])

        with ScrollableContainer(id="config-scroll"):
            with Vertical(id="config-inner"):
                # ── Thresholds ───────────────────────────────
                yield Static("[bold]Thresholds[/bold]", classes="config-section-title")
                for key, default in [
                    ("guide",  0.25),
                    ("warn",   0.50),
                    ("block",  0.75),
                ]:
                    with Horizontal(classes="config-row"):
                        yield Static(f"thresholds.{key}:", classes="config-label")
                        yield Input(
                            str(th.get(key, default)),
                            id=f"th-{key}",
                            classes="config-input",
                        )

                yield Rule()

                # ── Weights ──────────────────────────────────
                yield Static("[bold]Weights[/bold]", classes="config-section-title")
                for key, default in [
                    ("uncertainty",  2.0),
                    ("drift",        1.8),
                    ("error_rate",   1.5),
                    ("cost",         1.0),
                    ("token_usage",  0.8),
                ]:
                    with Horizontal(classes="config-row"):
                        yield Static(f"weights.{key}:", classes="config-label")
                        yield Input(
                            str(wt.get(key, default)),
                            id=f"wt-{key}",
                            classes="config-input",
                        )

                yield Rule()

                # ── Budget ───────────────────────────────────
                yield Static("[bold]Budget[/bold]", classes="config-section-title")
                for key, default in [
                    ("tokens",   100000),
                    ("cost_usd", 5.0),
                ]:
                    with Horizontal(classes="config-row"):
                        yield Static(f"budget.{key}:", classes="config-label")
                        yield Input(
                            str(bud.get(key, default)),
                            id=f"bud-{key}",
                            classes="config-input",
                        )

                yield Rule()

                # ── Graph ────────────────────────────────────
                yield Static("[bold]Graph[/bold]", classes="config-section-title")
                for key, default in [
                    ("damping",             0.6),
                    ("trust_decay_rate",    0.05),
                    ("trust_recovery_rate", 0.02),
                ]:
                    with Horizontal(classes="config-row"):
                        yield Static(f"graph.{key}:", classes="config-label")
                        yield Input(
                            str(gr.get(key, default)),
                            id=f"gr-{key}",
                            classes="config-input",
                        )

                yield Rule()

                # ── Preview ──────────────────────────────────
                yield Static(
                    self._build_preview(th),
                    id="config-preview",
                )

        with Horizontal(id="config-btn-row"):
            yield Button("Save", id="config-save-btn", variant="primary")
            yield Button("Reload from disk", id="config-reload-btn")
        yield Static(
            "  [dim]Ctrl+S to save.  Changes take effect on next engine start.[/dim]",
            id="config-status",
        )

    # ── Preview ──────────────────────────────────────────────────

    def _build_preview(self, thresholds: dict[str, Any]) -> str:
        """Show what mode an agent at example pressure would get."""
        current_level = pressure_to_mode(_PREVIEW_PRESSURE)
        orig_level = pressure_to_mode(_PREVIEW_PRESSURE)

        color = MODE_COLORS.get(current_level, "white")
        orig_color = MODE_COLORS.get(orig_level, "white")

        if current_level == orig_level:
            change = "[dim](no change from default)[/]"
        else:
            change = (
                f"[bold]changed from [/bold]"
                f"[{orig_color}]{orig_level.name}[/]"
                f"[bold] to [/bold]"
                f"[{color}]{current_level.name}[/]"
            )

        return (
            f"  [bold]Preview:[/bold]  pressure={_PREVIEW_PRESSURE:.2f}  →  "
            f"[{color}]{current_level.name}[/]  {change}"
        )

    def _read_thresholds_from_inputs(self) -> dict[str, float]:
        th: dict[str, float] = {}
        for key in ("guide", "warn", "block"):
            try:
                val = float(self.query_one(f"#th-{key}", Input).value)
                th[key] = val
            except (ValueError, Exception):
                th[key] = DEFAULT_CONFIG["thresholds"][key]
        return th

    def _refresh_preview(self) -> None:
        th = self._read_thresholds_from_inputs()
        try:
            self.query_one("#config-preview", Static).update(self._build_preview(th))
        except Exception:
            pass

    # ── Input changes -> live preview ────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("th-"):
            self._refresh_preview()

    # ── Button presses ───────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-save-btn":
            self.action_save_config()
        elif event.button.id == "config-reload-btn":
            self._reload_from_disk()

    def _collect_config(self) -> dict[str, Any]:
        """Read all Input widgets and build a config dict."""
        cfg: dict[str, Any] = dict(self._config)  # start from loaded config

        # Thresholds
        th: dict[str, float] = {}
        for key in ("guide", "warn", "block"):
            try:
                th[key] = float(self.query_one(f"#th-{key}", Input).value)
            except Exception:
                th[key] = DEFAULT_CONFIG["thresholds"][key]
        cfg["thresholds"] = th

        # Weights
        wt: dict[str, float] = {}
        for key in ("uncertainty", "drift", "error_rate", "cost", "token_usage"):
            try:
                wt[key] = float(self.query_one(f"#wt-{key}", Input).value)
            except Exception:
                wt[key] = DEFAULT_CONFIG["weights"][key]
        cfg["weights"] = wt

        # Budget
        bud: dict[str, float] = {}
        for key, cast in (("tokens", int), ("cost_usd", float)):
            try:
                bud[key] = cast(self.query_one(f"#bud-{key}", Input).value)  # type: ignore[operator]
            except Exception:
                bud[key] = DEFAULT_CONFIG["budget"][key]
        cfg["budget"] = bud

        # Graph
        gr: dict[str, float] = {}
        for key in ("damping", "trust_decay_rate", "trust_recovery_rate"):
            try:
                gr[key] = float(self.query_one(f"#gr-{key}", Input).value)
            except Exception:
                gr[key] = DEFAULT_CONFIG["graph"][key]
        cfg["graph"] = gr

        return cfg

    def action_save_config(self) -> None:
        cfg = self._collect_config()
        try:
            save_config(cfg, "soma.toml")
            self._config = cfg
            self._set_status("[#22c55e]Saved to soma.toml[/]")
        except Exception as exc:
            self._set_status(f"[#ef4444]Save error:[/] {exc}")

    def _reload_from_disk(self) -> None:
        self._config = load_config()
        self._set_status("[#58a6ff]Reloaded from disk.[/]  (Restart tab to see new values in fields.)")

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#config-status", Static).update(f"  {msg}")
        except Exception:
            pass
