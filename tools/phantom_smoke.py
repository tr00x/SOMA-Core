#!/usr/bin/env python3
"""
Phantom agent — end-to-end smoke test for SOMA v2026.6.1 without an LLM.

Spawns the soma-hook subprocess with isolated HOME, simulates a
sequence of Pre/PostToolUse events that fire the blind_edit pattern
(Edit without preceding Read), drives at least 3 follow-up actions
to push past h=2, then inspects the resulting analytics.db to verify:

  • at least one ab_outcomes row landed
  • every row has firing_id
  • every row has pressure_after_h1 (the v2026.6.1 dropguard)
  • pressure_after (h=2) is populated

Exits 0 on PASS, 1 on FAIL with a verdict report.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


# Resolve relative to this script: tools/phantom_smoke.py → repo root.
# Override via SOMA_REPO / SOMA_HOOK_BIN env vars if running from a wheel.
REPO = Path(os.environ.get("SOMA_REPO", Path(__file__).resolve().parent.parent))
HOOK_BIN = Path(os.environ.get("SOMA_HOOK_BIN", REPO / ".venv" / "bin" / "soma-hook"))


def _hook(home: Path, hook_type: str, payload: dict) -> tuple[int, str, str]:
    """Run soma-hook as Claude Code does: env=CLAUDE_HOOK, stdin=JSON."""
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["CLAUDE_HOOK"] = hook_type
    env["SOMA_AGENT_FAMILY"] = "phantom"  # so calibration doesn't pull "cc"
    env["SOMA_FORCE_PATTERN"] = "blind_edit"  # bypass retire/cooldown filters
    proc = subprocess.run(
        [str(HOOK_BIN)],
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _payload_pre(tool: str, file_path: str = "", session_id: str = "phantom-001") -> dict:
    return {
        "session_id": session_id,
        "transcript_path": "",
        "cwd": "/tmp",
        "tool_name": tool,
        "tool_input": {"file_path": file_path} if file_path else {},
    }


def _payload_post(tool: str, file_path: str = "", session_id: str = "phantom-001") -> dict:
    return {
        "session_id": session_id,
        "transcript_path": "",
        "cwd": "/tmp",
        "tool_name": tool,
        "tool_input": {"file_path": file_path} if file_path else {},
        "tool_response": "ok",
    }


def main() -> int:
    if not HOOK_BIN.exists():
        print(f"[FAIL] soma-hook not found at {HOOK_BIN}")
        return 1

    with tempfile.TemporaryDirectory(prefix="soma-phantom-") as tmp:
        home = Path(tmp)
        soma_dir = home / ".soma"
        soma_dir.mkdir(parents=True, exist_ok=True)
        # Touch a minimal soma.toml so SOMA finds a config
        (home / "soma.toml").write_text(
            "[budget]\ntokens = 100000\n[guidance]\nmode = \"guide\"\n"
        )
        # Pre-seed calibration to skip warmup so guidance can fire.
        # _phase_for: 0-29 warmup, 30-199 calibrated, 200+ adaptive.
        # Picking 100 → "calibrated" phase, plenty of headroom.
        import time as _time
        (soma_dir / "calibration_phantom.json").write_text(json.dumps({
            "family": "phantom",
            "action_count": 100,
            "phase": "calibrated",
            "drift_p25": 0.0, "drift_p75": 0.5,
            "entropy_p25": 0.0, "entropy_p75": 1.0,
            "typical_error_burst": 1,
            "typical_retry_burst": 1,
            "typical_success_rate": 0.9,
            "silenced_patterns": [],
            "last_silence_check_action": 0,
            "pattern_precision_cache": {},
            "refuted_patterns": [],
            "last_refuted_check_action": 0,
            "validated_patterns": [],
            "created_at": _time.time(),
            "updated_at": _time.time(),
            "schema_version": 1,
        }))
        # Pre-create a real target file so blind_edit treats Write as
        # an edit-not-create (the detector returns None on non-existing
        # paths because Write to fresh files isn't blind editing).
        target = home / "target.py"
        target.write_text("# pre-existing content\nprint('hi')\n")
        target_path = str(target)
        print(f"[phantom] HOME={home} target={target_path}")

        # --- Drive the sequence ---
        # 1-2) Write to pre-existing file with no prior Read → blind_edit fires
        # 3-10) Follow-up actions to drive actions_since up past h=2
        sequence = [
            ("PreToolUse",  _payload_pre("Write", target_path)),
            ("PostToolUse", _payload_post("Write", target_path)),
            # Now A/B is armed, drive follow-ups (no Read of target so the
            # pattern stays "active" — but firing already happened above)
            ("PreToolUse",  _payload_pre("Bash")),
            ("PostToolUse", _payload_post("Bash")),
            ("PreToolUse",  _payload_pre("Bash")),
            ("PostToolUse", _payload_post("Bash")),
            ("PreToolUse",  _payload_pre("Bash")),
            ("PostToolUse", _payload_post("Bash")),
            ("PreToolUse",  _payload_pre("Bash")),
            ("PostToolUse", _payload_post("Bash")),
        ]
        for i, (event, payload) in enumerate(sequence, 1):
            rc, out, err = _hook(home, event, payload)
            print(f"[phantom] {i:02d} {event:12} rc={rc} stdout_len={len(out)} stderr_len={len(err)}")
            if rc != 0 and event != "PreToolUse":
                # PreToolUse can rc=2 to block; PostToolUse should normally rc=0
                print(f"[warn] non-zero rc on {event}: stderr={err[:200]}")

        # --- Inspect the DB ---
        print(f"[phantom] soma_dir contents: {[p.name for p in soma_dir.iterdir()]}")
        for circuit in soma_dir.glob("circuit_*.json"):
            print(f"[phantom] {circuit.name}:")
            print(f"  {circuit.read_text()[:500]}")
        db = soma_dir / "analytics.db"
        if not db.exists():
            print(f"[FAIL] no analytics.db produced at {db}")
            print(f"  tmp dir contents: {list(soma_dir.iterdir())}")
            return 1

        conn = sqlite3.connect(str(db))
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            print(f"[phantom] tables: {tables}")
            if "ab_outcomes" not in tables:
                print("[FAIL] ab_outcomes table missing")
                return 1
            rows = conn.execute(
                "SELECT pattern, arm, firing_id, pressure_before, "
                "pressure_after, pressure_after_h1 FROM ab_outcomes"
            ).fetchall()
            counters = {p[0]: p[1] for p in conn.execute(
                "SELECT pattern, COUNT(*) FROM ab_outcomes GROUP BY pattern"
            ).fetchall()}
        finally:
            conn.close()

        print(f"[phantom] ab_outcomes rows: {len(rows)}")
        print(f"[phantom] per-pattern: {counters}")
        for r in rows:
            print(f"  pattern={r[0]} arm={r[1]} fid={r[2]!r} "
                  f"before={r[3]} after={r[4]} h1={r[5]}")

        # --- Verdict ---
        verdict_lines: list[str] = []
        ok = True
        if not rows:
            verdict_lines.append("FAIL · zero ab_outcomes rows landed")
            ok = False
        else:
            null_fid = sum(1 for r in rows if r[2] is None)
            null_h1 = sum(1 for r in rows if r[5] is None)
            if null_fid:
                verdict_lines.append(f"FAIL · {null_fid}/{len(rows)} rows have NULL firing_id")
                ok = False
            else:
                verdict_lines.append(f"PASS · all {len(rows)} rows have firing_id")
            if null_h1:
                verdict_lines.append(
                    f"FAIL · {null_h1}/{len(rows)} rows have NULL pressure_after_h1 "
                    "(v2026.6.1 dropguard violated)"
                )
                ok = False
            else:
                verdict_lines.append(f"PASS · all {len(rows)} rows have pressure_after_h1")

        print("─" * 60)
        for line in verdict_lines:
            print(line)
        print("─" * 60)
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
