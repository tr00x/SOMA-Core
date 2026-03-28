"""SOMA Hub — Replay Tab (Tab 3).

Load a session JSON file, scrub through its timeline step-by-step,
and optionally auto-play at adjustable speed.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, RichLog, Input, Button, TabPane
from textual.timer import Timer

from soma.recorder import SessionRecorder, RecordedAction
from soma.engine import SOMAEngine
from soma.types import Level

# ── Color helpers ────────────────────────────────────────────────

LEVEL_COLORS = {
    Level.HEALTHY:    "#22c55e",
    Level.CAUTION:    "#eab308",
    Level.DEGRADE:    "#f97316",
    Level.QUARANTINE: "#ef4444",
    Level.RESTART:    "#a855f7",
    Level.SAFE_MODE:  "#ffffff",
}


# ── ReplayTab ────────────────────────────────────────────────────

class ReplayTab(TabPane):
    """Tab 3 — load a session recording and scrub through it."""

    DEFAULT_CSS = """
    ReplayTab {
        layout: vertical;
    }
    #replay-load-row {
        layout: horizontal; height: 5; padding: 1 2; background: #111;
    }
    #replay-path-input {
        width: 1fr; margin-right: 1;
    }
    #replay-load-btn {
        width: 16;
    }
    #replay-status {
        height: 3; background: #0d1117; padding: 1 2; color: #58a6ff;
    }
    #replay-scrubber {
        height: 3; background: #111; padding: 1 2;
    }
    #replay-controls {
        layout: horizontal; height: 5; padding: 1 2; background: #0d1117;
    }
    #replay-play-btn  { width: 14; margin-right: 1; }
    #replay-slower-btn { width: 12; margin-right: 1; }
    #replay-faster-btn { width: 12; }
    #replay-state {
        height: 1fr; background: #0f0f0f; border: round #333; padding: 0 1;
    }
    #replay-hints {
        height: 3; background: #141414; padding: 1 2; color: #555;
    }
    """

    BINDINGS = [
        Binding("left",  "step_back",  "Step Back"),
        Binding("right", "step_forward", "Step Forward"),
        Binding("p",     "toggle_play", "Play/Pause"),
        Binding("comma", "slower",     "Slower"),
        Binding("period","faster",     "Faster"),
    ]

    def __init__(self) -> None:
        super().__init__("Replay", id="tab-replay")
        self._recording: SessionRecorder | None = None
        self._engine: SOMAEngine | None = None
        self._steps: list[RecordedAction] = []
        self._cursor: int = -1          # index of last applied step
        self._playing: bool = False
        self._play_speed: float = 0.5   # seconds between auto-steps
        self._timer: Timer | None = None

    # ── Compose ──────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(id="replay-load-row"):
            yield Input(
                placeholder="Path to session JSON, e.g. soma_session.json",
                id="replay-path-input",
            )
            yield Button("Load", id="replay-load-btn", variant="primary")
        yield Static("No session loaded.  Enter a path above and click Load.", id="replay-status")
        yield Static("Timeline: —", id="replay-scrubber")
        with Horizontal(id="replay-controls"):
            yield Button("Play", id="replay-play-btn", variant="success")
            yield Button("Slower", id="replay-slower-btn")
            yield Button("Faster", id="replay-faster-btn")
        yield RichLog(id="replay-state", markup=True, wrap=True)
        yield Static(
            "  [#58a6ff]←/→[/]=Step   [#58a6ff]P[/]=Play/Pause   "
            "[#58a6ff],[/]=Slower   [#58a6ff].[/]=Faster",
            id="replay-hints",
        )

    # ── Load ─────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "replay-load-btn":
            self._load_session()
        elif event.button.id == "replay-play-btn":
            self.action_toggle_play()
        elif event.button.id == "replay-slower-btn":
            self.action_slower()
        elif event.button.id == "replay-faster-btn":
            self.action_faster()

    def _load_session(self) -> None:
        try:
            path_str = self.query_one("#replay-path-input", Input).value.strip()
        except Exception:
            return
        path = Path(path_str)
        if not path.exists():
            self._set_status(f"[#ef4444]File not found:[/] {path_str}")
            return

        try:
            self._recording = SessionRecorder.load(path)
        except Exception as exc:
            self._set_status(f"[#ef4444]Load error:[/] {exc}")
            return

        self._steps = self._recording.actions
        self._cursor = -1

        # Build fresh engine for replay
        self._engine = SOMAEngine()
        seen: set[str] = set()
        for ra in self._steps:
            if ra.agent_id not in seen:
                seen.add(ra.agent_id)
                self._engine.register_agent(ra.agent_id)

        total = len(self._steps)
        self._set_status(
            f"[#22c55e]Loaded:[/] {path.name}  —  "
            f"{total} actions, {len(seen)} agents"
        )
        self._update_scrubber()
        self._log_state(f"[bold]Session loaded.[/bold]  Press → or Play to start.")

    # ── Scrubbing ────────────────────────────────────────────────

    def _apply_step(self, idx: int) -> None:
        """Apply step at *idx* to the engine and render its state."""
        if self._engine is None or not self._steps:
            return
        if idx < 0 or idx >= len(self._steps):
            return

        ra = self._steps[idx]
        result = self._engine.record_action(ra.agent_id, ra.action)
        color = LEVEL_COLORS.get(result.level, "white")
        snap = self._engine.get_snapshot(ra.agent_id)
        self._log_state(
            f"[dim]{idx+1}/{len(self._steps)}[/]  "
            f"[bold]{ra.agent_id}[/bold]  "
            f"[{color}]{result.level.name}[/]  "
            f"p={result.pressure:.3f}  "
            f"tool=[italic]{ra.action.tool_name}[/]  "
            f"tokens={ra.action.token_count}"
            + (f"  [#ef4444]ERR[/]" if ra.action.error else "")
        )
        self._cursor = idx
        self._update_scrubber()

    def _update_scrubber(self) -> None:
        total = len(self._steps)
        if total == 0:
            text = "Timeline: —"
        else:
            pos = self._cursor + 1  # 1-based display
            bar_len = 40
            filled = int((pos / total) * bar_len)
            bar = f"[#58a6ff]{'█' * filled}[/]{'░' * (bar_len - filled)}"
            text = f"  {bar}  {pos}/{total}"
        try:
            self.query_one("#replay-scrubber", Static).update(text)
        except Exception:
            pass

    def _log_state(self, msg: str) -> None:
        try:
            log = self.query_one("#replay-state", RichLog)
            log.write(msg)
        except Exception:
            pass

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#replay-status", Static).update(f"  {msg}")
        except Exception:
            pass

    # ── Auto-play ────────────────────────────────────────────────

    def _play_tick(self) -> None:
        if not self._playing:
            return
        next_idx = self._cursor + 1
        if next_idx >= len(self._steps):
            # End of recording
            self._playing = False
            if self._timer:
                self._timer.stop()
                self._timer = None
            self._set_status("[#eab308]Playback complete.[/]")
            try:
                self.query_one("#replay-play-btn", Button).label = "Play"
            except Exception:
                pass
            return
        self._apply_step(next_idx)

    # ── Actions ─────────────────────────────────────────────────

    def action_step_forward(self) -> None:
        next_idx = self._cursor + 1
        if self._steps and next_idx < len(self._steps):
            self._apply_step(next_idx)

    def action_step_back(self) -> None:
        """Step back by rebuilding engine up to (cursor-1)."""
        if self._cursor <= 0 or not self._steps or self._engine is None:
            return
        target = self._cursor - 1

        # Rebuild engine from scratch up to target
        self._engine = SOMAEngine()
        seen: set[str] = set()
        for ra in self._steps:
            if ra.agent_id not in seen:
                seen.add(ra.agent_id)
                self._engine.register_agent(ra.agent_id)

        self._cursor = -1
        for i in range(target + 1):
            self._apply_step(i)

    def action_toggle_play(self) -> None:
        if not self._steps:
            self._set_status("[dim]Load a session first.[/]")
            return
        self._playing = not self._playing
        try:
            btn = self.query_one("#replay-play-btn", Button)
            btn.label = "Pause" if self._playing else "Play"
        except Exception:
            pass
        if self._playing:
            if self._timer:
                self._timer.stop()
            self._timer = self.set_interval(self._play_speed, self._play_tick)
        else:
            if self._timer:
                self._timer.stop()
                self._timer = None

    def action_slower(self) -> None:
        self._play_speed = min(self._play_speed + 0.2, 3.0)
        self._set_status(f"  Speed: {self._play_speed:.1f}s/step")
        if self._playing and self._timer:
            self._timer.stop()
            self._timer = self.set_interval(self._play_speed, self._play_tick)

    def action_faster(self) -> None:
        self._play_speed = max(self._play_speed - 0.1, 0.05)
        self._set_status(f"  Speed: {self._play_speed:.2f}s/step")
        if self._playing and self._timer:
            self._timer.stop()
            self._timer = self.set_interval(self._play_speed, self._play_tick)
