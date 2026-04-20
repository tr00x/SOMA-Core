"""SOMA Mirror — proprioceptive session context for tool response injection.

Generates compact factual blocks about the current session state.
No opinions, no suggestions, no "SOMA" branding — just facts and numbers
that look like part of the environment output.

Three generation modes (cheapest first):
  PATTERN — known pattern from memory, cached context (0 cost)
  STATS   — numeric facts from current vitals (0 cost)
  SEMANTIC — external LLM call for behavioral observation

Self-learning: after each injection, Mirror watches the next 3 actions.
If pressure drops ≥10%, the context helped. Results accumulate in pattern_db
so effective contexts get reused and ineffective ones get pruned.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from soma.engine import SOMAEngine
from soma.types import Action


PATTERN_DB_PATH = Path.home() / ".soma" / "patterns.json"
PENDING_DB_PATH = Path.home() / ".soma" / "mirror_pending.json"

# Pressure below this threshold → no context injected (agent is healthy)
SILENCE_THRESHOLD = 0.25

# Pressure at or above this → eligible for semantic mode
SEMANTIC_THRESHOLD = 0.40

# How many actions to wait before evaluating whether injection helped
EVAL_WINDOW = 3

# Pressure must drop by at least this fraction of injection-time pressure
IMPROVEMENT_RATIO = 0.10

# Minimum attempts before pruning a low-success pattern
MIN_ATTEMPTS_FOR_PRUNE = 5

# Success rate thresholds
EFFECTIVE_THRESHOLD = 0.6    # above → use cached context
PRUNE_THRESHOLD = 0.3        # below after MIN_ATTEMPTS → delete

# How far back a Read must be to count as "stale" for VBD detection
VBD_READ_STALENESS = 5

# LLM config
_LLM_MAX_TOKENS = 80
_LLM_TIMEOUT = 3.0

_SEMANTIC_SYSTEM = (
    "You analyze AI agent behavior. Describe in 1-2 factual sentences "
    "what the agent is doing vs what it should be doing. "
    "No opinions, no suggestions, no warnings. Only observable facts."
)


@dataclass
class PendingEval:
    """Tracks an injection awaiting outcome evaluation."""
    agent_id: str
    pattern_key: str
    context_text: str
    pressure_at_injection: float
    actions_since: int
    timestamp: float


@dataclass
class PatternRecord:
    """Learned pattern with success/fail statistics."""
    context_text: str
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0

    @property
    def total(self) -> int:
        return self.success_count + self.fail_count

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success_count / self.total

    def to_dict(self) -> dict:
        return {
            "context_text": self.context_text,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PatternRecord:
        return cls(
            context_text=d.get("context_text", ""),
            success_count=d.get("success_count", 0),
            fail_count=d.get("fail_count", 0),
            last_used=d.get("last_used", 0.0),
        )


class Mirror:
    """Generates proprioceptive session context for injection into tool responses.

    Output is a factual block between ``--- session context ---`` markers.
    Maximum 3 lines, ~40 tokens. No directives, no branding.
    """

    def __init__(self, engine: SOMAEngine) -> None:
        self.engine = engine
        self.pattern_db: dict[str, PatternRecord] = {}
        self._pending: list[PendingEval] = []
        self._semantic_enabled: bool = True
        self._semantic_provider: str = "auto"
        self._semantic_threshold: float = SEMANTIC_THRESHOLD
        self._load_pattern_db()
        self._load_pending()
        self._load_mirror_config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        agent_id: str,
        action: Action,
        tool_output: str,
        task_description: str | None = None,
    ) -> str | None:
        """Return a session context block, or ``None`` when the agent is healthy."""
        snap = self.engine.get_snapshot(agent_id)
        pressure: float = snap["pressure"]

        if pressure < SILENCE_THRESHOLD:
            return None

        # Try PATTERN mode first (cheapest)
        detected = self._detect_pattern(agent_id)

        if detected is not None and pressure < self._semantic_threshold:
            # Low-to-medium pressure: PATTERN or STATS
            pattern_key, pattern_desc = detected
            record = self.pattern_db.get(pattern_key)
            if record is not None and record.success_rate >= EFFECTIVE_THRESHOLD and record.total >= 2:
                context_text = record.context_text
            else:
                context_text = pattern_desc
            self.track_injection(agent_id, pattern_key, context_text, pressure)
            return self._wrap(context_text)

        if pressure < self._semantic_threshold:
            # Medium pressure, no pattern → STATS
            if detected is not None:
                pattern_key, pattern_desc = detected
                self.track_injection(agent_id, pattern_key, pattern_desc, pressure)
                return self._wrap(pattern_desc)
            # v2026.5.0: drop `_stats` user-facing emission. It fatigued
            # users (31% helped on 242 firings — largest noise source) and
            # reference data shows mirror raw stats don't change agent
            # behavior. Keep internal tracking off too so analytics stop
            # receiving a row that nobody acts on.
            return None

        # High pressure (>= semantic_threshold): check if semantic is warranted
        needs_semantic = self._needs_semantic(agent_id, detected)

        if needs_semantic and self._semantic_enabled:
            semantic_text = self._generate_semantic_sync(
                agent_id, action, task_description
            )
            if semantic_text is not None:
                # v2026.5.0: drop the aggregate `_stats` prefix here too.
                # Semantic output stands on its own; the stats one-liner
                # was part of the same fatigue surface we already pruned
                # from the medium-pressure branch.
                self.track_injection(agent_id, "_semantic", semantic_text, pressure)
                return self._wrap(semantic_text)

        # Fallback: PATTERN if available, else STATS
        if detected is not None:
            pattern_key, pattern_desc = detected
            record = self.pattern_db.get(pattern_key)
            if record is not None and record.success_rate >= EFFECTIVE_THRESHOLD and record.total >= 2:
                context_text = record.context_text
            else:
                context_text = pattern_desc
            self.track_injection(agent_id, pattern_key, context_text, pressure)
            return self._wrap(context_text)

        # v2026.5.0: same drop at the high-pressure fallback path. No
        # pattern matched, no semantic override available — prefer
        # silence over emitting a generic stats block.
        return None

    # ------------------------------------------------------------------
    # Semantic mode
    # ------------------------------------------------------------------

    def _needs_semantic(self, agent_id: str, detected: tuple[str, str] | None) -> bool:
        """Decide whether semantic analysis is warranted.

        Returns True when:
        - No pattern detected at high pressure (agent is lost, not in a known loop)
        - Goal drift: goal_coherence < 0.5 (if available)
        - Verbal-behavioral divergence: recent edits without recent reads
        """
        state = self.engine._agents[agent_id]
        actions = list(state.ring_buffer)

        # No pattern match at high pressure
        if detected is None:
            return True

        # VBD: edit/write and last Read was > VBD_READ_STALENESS actions ago
        if self._detect_vbd(actions):
            return True

        # Goal drift via vitals
        snap = self.engine.get_snapshot(agent_id)
        vitals = snap.get("vitals", {})
        gc = vitals.get("goal_coherence")
        if gc is not None and gc < 0.5:
            return True

        return False

    def _detect_vbd(self, actions: list[Action]) -> bool:
        """Detect verbal-behavioral divergence: recent edits without recent reads.

        Returns True if the last Write/Edit has no Read within the prior
        VBD_READ_STALENESS actions targeting a related file.
        """
        if len(actions) < 3:
            return False

        # Find last edit/write
        last_edit_idx = None
        last_edit_file = ""
        for i in range(len(actions) - 1, -1, -1):
            if actions[i].tool_name in ("Write", "Edit"):
                last_edit_idx = i
                last_edit_file = actions[i].metadata.get("file_path", "")
                break

        if last_edit_idx is None:
            return False

        # Look for a Read of the same file in the prior window
        start = max(0, last_edit_idx - VBD_READ_STALENESS)
        for i in range(start, last_edit_idx):
            if actions[i].tool_name == "Read":
                read_file = actions[i].metadata.get("file_path", "")
                if read_file == last_edit_file:
                    return False
        return True

    def _generate_semantic_sync(
        self,
        agent_id: str,
        action: Action,
        task_description: str | None,
    ) -> str | None:
        """Call a cheap LLM for behavioral observation.

        Returns 1-2 factual sentences or None if LLM unavailable.
        """
        state = self.engine._agents[agent_id]
        actions = list(state.ring_buffer)

        # Build action history for context
        history_lines: list[str] = []
        recent = actions[-5:] if len(actions) >= 5 else actions
        for i, a in enumerate(recent, 1):
            err_str = " [ERROR]" if a.error else ""
            file_str = ""
            fp = a.metadata.get("file_path", "")
            if fp:
                file_str = f" file={fp.rsplit('/', 1)[-1]}"
            history_lines.append(f"  {i}. {a.tool_name}{file_str}{err_str}")

        task_str = task_description or "(unknown task)"
        user_prompt = (
            f"Task: {task_str}\n"
            f"Last actions:\n"
            f"{''.join(line + chr(10) for line in history_lines)}\n"
            f"Factual observation:"
        )

        result = self._call_llm(_SEMANTIC_SYSTEM, user_prompt)
        if result is None:
            return None

        # Truncate to 2 sentences max
        sentences = result.replace("\n", " ").strip().split(". ")
        truncated = ". ".join(sentences[:2])
        if not truncated.endswith("."):
            truncated += "."
        return truncated

    def _call_llm(self, system: str, user: str) -> str | None:
        """Call an LLM via HTTP. Provider chosen from config/env.

        Priority: GEMINI_API_KEY → ANTHROPIC_API_KEY → OPENAI_API_KEY.
        Returns response text or None on any failure.
        """
        try:
            import httpx
        except ImportError:
            return None

        provider = self._semantic_provider
        if provider == "auto":
            provider = self._detect_provider()
        if provider is None:
            return None

        try:
            if provider == "gemini":
                return self._call_gemini(httpx, system, user)
            elif provider == "anthropic":
                return self._call_anthropic(httpx, system, user)
            elif provider == "openai":
                return self._call_openai(httpx, system, user)
        except Exception:
            pass
        return None

    def _detect_provider(self) -> str | None:
        """Auto-detect available LLM provider from env vars."""
        if os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return None

    def _call_gemini(self, httpx_mod, system: str, user: str) -> str | None:
        key = os.environ.get("GEMINI_API_KEY", "")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": _LLM_MAX_TOKENS,
                "temperature": 0,
            },
        }
        resp = httpx_mod.post(url, json=body, timeout=_LLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
        return None

    def _call_anthropic(self, httpx_mod, system: str, user: str) -> str | None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        resp = httpx_mod.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20250514",
                "max_tokens": _LLM_MAX_TOKENS,
                "temperature": 0,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=_LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [])
        if content:
            return content[0].get("text", "").strip()
        return None

    def _call_openai(self, httpx_mod, system: str, user: str) -> str | None:
        key = os.environ.get("OPENAI_API_KEY", "")
        resp = httpx_mod.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": _LLM_MAX_TOKENS,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=_LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        return None

    # ------------------------------------------------------------------
    # Self-learning
    # ------------------------------------------------------------------

    def track_injection(
        self,
        agent_id: str,
        pattern_key: str,
        context_text: str,
        pressure_at_injection: float,
    ) -> None:
        """Record that a context was just injected. Starts the evaluation timer."""
        self._pending.append(PendingEval(
            agent_id=agent_id,
            pattern_key=pattern_key,
            context_text=context_text,
            pressure_at_injection=pressure_at_injection,
            actions_since=0,
            timestamp=time.time(),
        ))
        self._save_pending()

    def evaluate_pending(
        self,
        agent_id: str,
        current_pressure: float,
    ) -> None:
        """Check pending evaluations. Call after each record_action.

        After EVAL_WINDOW actions post-injection, compares current pressure
        to injection-time pressure. Pressure drop ≥ IMPROVEMENT_RATIO means
        the context helped.

        Stale entries (>1 hour old) are discarded to prevent unbounded growth.
        """
        still_pending: list[PendingEval] = []
        now = time.time()
        stale_cutoff = now - 3600  # 1 hour

        for pending in self._pending:
            # Discard stale entries from dead sessions
            if pending.timestamp < stale_cutoff:
                continue

            if pending.agent_id != agent_id:
                still_pending.append(pending)
                continue

            pending.actions_since += 1

            if pending.actions_since < EVAL_WINDOW:
                still_pending.append(pending)
                continue

            # Evaluate: did pressure drop enough?
            if pending.pressure_at_injection > 0:
                drop = pending.pressure_at_injection - current_pressure
                helped = drop >= (pending.pressure_at_injection * IMPROVEMENT_RATIO)
            else:
                helped = False

            self.record_outcome(
                agent_id,
                pending.pattern_key,
                pending.context_text,
                helped,
                pressure_at_injection=pending.pressure_at_injection,
                pressure_after=current_pressure,
            )

        self._pending = still_pending
        self._save_pending()

    def record_outcome(
        self,
        agent_id: str,
        pattern_key: str,
        context_text: str,
        helped: bool,
        pressure_at_injection: float = 0.0,
        pressure_after: float = 0.0,
    ) -> None:
        """Update pattern_db with outcome and persist to analytics."""
        if not pattern_key:
            return

        record = self.pattern_db.get(pattern_key)
        if record is None:
            record = PatternRecord(context_text=context_text)
            self.pattern_db[pattern_key] = record

        if helped:
            record.success_count += 1
            record.context_text = context_text
        else:
            record.fail_count += 1

        record.last_used = time.time()

        # Persist to analytics DB for cross-session tracking
        try:
            from soma.analytics import AnalyticsStore
            analytics = AnalyticsStore()
            analytics.record_guidance_outcome(
                agent_id=agent_id,
                session_id=agent_id,
                pattern_key=pattern_key,
                helped=helped,
                pressure_at_injection=pressure_at_injection,
                pressure_after=pressure_after,
            )
        except Exception:
            pass  # Never crash for analytics

        # Prune ineffective patterns
        if record.total >= MIN_ATTEMPTS_FOR_PRUNE and record.success_rate < PRUNE_THRESHOLD:
            del self.pattern_db[pattern_key]

        self._save_pattern_db()

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def _detect_pattern(self, agent_id: str) -> tuple[str, str] | None:
        """Detect a behavioral pattern from the agent's action history."""
        state = self.engine._agents[agent_id]
        actions = list(state.ring_buffer)
        if len(actions) < 2:
            return None

        # ── retry_loop: 2+ identical Bash commands in a row ──
        bash_actions = [a for a in actions if a.tool_name == "Bash"]
        if len(bash_actions) >= 2:
            last_cmds: list[str] = []
            for a in reversed(actions):
                if a.tool_name == "Bash":
                    cmd = a.output_text[:200].strip()
                    if last_cmds and cmd != last_cmds[-1]:
                        break
                    last_cmds.append(cmd)
                elif last_cmds:
                    break
            if len(last_cmds) >= 2:
                return (
                    "retry_loop",
                    f"same bash cmd repeated {len(last_cmds)}x — read the error output before retrying",
                )

        # ── blind_edit: Write/Edit without prior Read of that file ──
        read_files: set[str] = set()
        blind_count = 0
        blind_files: list[str] = []
        for a in actions:
            if a.tool_name == "Read":
                path = a.metadata.get("file_path", "")
                if path:
                    read_files.add(path)
            elif a.tool_name in ("Write", "Edit"):
                path = a.metadata.get("file_path", "")
                if path and path not in read_files:
                    blind_count += 1
                    short = path.rsplit("/", 1)[-1] if "/" in path else path
                    if short not in blind_files:
                        blind_files.append(short)
        if blind_count >= 2:
            files_str = ", ".join(blind_files[:3])
            return (
                "blind_edit",
                f"{blind_count} files edited without reading first ({files_str}) — read before editing",
            )

        # ── error_cascade: 3+ errors in last 5 actions ──
        # ── budget_warning: >70% of token budget used ──
        try:
            health = self.engine._budget.health()
            if health < 0.3:
                pct = int((1.0 - health) * 100)
                return (
                    "budget_warning",
                    f"{pct}% of token budget used — prioritize remaining work",
                )
        except Exception:
            pass

        # ── error_cascade: 3+ errors in last 5 actions ──
        recent = actions[-5:] if len(actions) >= 5 else actions
        error_count = sum(1 for a in recent if a.error)
        if error_count >= 3:
            failed_tools = [a.tool_name for a in recent if a.error]
            tool_str = ", ".join(failed_tools[:3])
            return (
                "error_cascade",
                f"{error_count}/{len(recent)} recent actions failed ({tool_str}) — try a different approach",
            )

        return None

    # ------------------------------------------------------------------
    # Stats formatting
    # ------------------------------------------------------------------

    def _format_stats_oneliner(self, agent_id: str) -> str:
        """One-line stats summary for prepending to semantic output."""
        state = self.engine._agents[agent_id]
        actions = list(state.ring_buffer)
        total = len(actions)
        errors = sum(1 for a in actions if a.error)
        return f"actions: {total} | errors: {errors}/{total}"

    def _format_stats(self, agent_id: str, action: Action) -> str:
        """Format numeric vitals into a compact session context block."""
        state = self.engine._agents[agent_id]
        actions = list(state.ring_buffer)
        snap = self.engine.get_snapshot(agent_id)
        vitals = snap.get("vitals", {})

        total = len(actions)
        errors = sum(1 for a in actions if a.error)

        # Count reads-before-writes ratio
        read_files: set[str] = set()
        writes_total = 0
        writes_with_read = 0
        for a in actions:
            if a.tool_name == "Read":
                path = a.metadata.get("file_path", "")
                if path:
                    read_files.add(path)
            elif a.tool_name in ("Write", "Edit"):
                path = a.metadata.get("file_path", "")
                writes_total += 1
                if path and path in read_files:
                    writes_with_read += 1

        # Find last successful action
        last_success = None
        for i, a in enumerate(reversed(actions)):
            if not a.error:
                idx = total - i
                short = a.tool_name
                last_success = f"action #{idx} ({short})"
                break

        lines: list[str] = []
        lines.append(f"actions: {total} | errors: {errors}/{total}")

        if writes_total > 0:
            lines[0] += f" | reads_before_writes: {writes_with_read}/{writes_total}"

        # Second line: top pressure signal
        signal_parts: list[str] = []
        for key in ("error_rate", "uncertainty", "drift"):
            val = vitals.get(key, 0)
            if val > 0.1:
                signal_parts.append(f"{key}: {val:.2f}")
        if signal_parts:
            lines.append(" | ".join(signal_parts[:2]))

        # Third line: last success
        if last_success and errors > 0:
            lines.append(f"last_successful: {last_success}")

        return "\n".join(lines[:3])

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap(body: str) -> str:
        """Wrap body text in session context markers."""
        return f"--- session context ---\n{body}\n---"

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_mirror_config(self) -> None:
        """Load [mirror] config from soma.toml."""
        try:
            from soma.cli.config_loader import load_config
            config = load_config()
            mirror_cfg = config.get("mirror", {})
            self._semantic_enabled = mirror_cfg.get("semantic_enabled", True)
            self._semantic_provider = mirror_cfg.get("semantic_provider", "auto")
            self._semantic_threshold = float(
                mirror_cfg.get("semantic_threshold", SEMANTIC_THRESHOLD)
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Pattern DB persistence
    # ------------------------------------------------------------------

    def _load_pattern_db(self) -> None:
        """Load learned patterns from disk."""
        try:
            if PATTERN_DB_PATH.exists():
                raw = json.loads(PATTERN_DB_PATH.read_text())
                self.pattern_db = {}
                for key, val in raw.items():
                    if isinstance(val, dict):
                        self.pattern_db[key] = PatternRecord.from_dict(val)
                    elif isinstance(val, str):
                        self.pattern_db[key] = PatternRecord(context_text=val)
        except (json.JSONDecodeError, OSError):
            self.pattern_db = {}

    def _save_pattern_db(self) -> None:
        """Persist pattern_db to disk."""
        try:
            PATTERN_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            raw = {key: record.to_dict() for key, record in self.pattern_db.items()}
            PATTERN_DB_PATH.write_text(json.dumps(raw, indent=2))
        except OSError:
            pass

    def _load_pending(self) -> None:
        """Load pending evaluations from disk (cross-process sharing)."""
        try:
            if PENDING_DB_PATH.exists():
                raw = json.loads(PENDING_DB_PATH.read_text())
                self._pending = [
                    PendingEval(
                        agent_id=p["agent_id"],
                        pattern_key=p["pattern_key"],
                        context_text=p.get("context_text", ""),
                        pressure_at_injection=p["pressure_at_injection"],
                        actions_since=p.get("actions_since", 0),
                        timestamp=p.get("timestamp", 0),
                    )
                    for p in raw if isinstance(p, dict)
                ]
        except (json.JSONDecodeError, OSError):
            self._pending = []

    def _save_pending(self) -> None:
        """Persist pending evaluations to disk."""
        try:
            PENDING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            raw = [
                {
                    "agent_id": p.agent_id,
                    "pattern_key": p.pattern_key,
                    "context_text": p.context_text,
                    "pressure_at_injection": p.pressure_at_injection,
                    "actions_since": p.actions_since,
                    "timestamp": p.timestamp,
                }
                for p in self._pending
            ]
            PENDING_DB_PATH.write_text(json.dumps(raw))
        except OSError:
            pass
