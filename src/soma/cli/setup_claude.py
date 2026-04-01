"""soma setup-claude — give your Claude Code a nervous system.

One command to install SOMA monitoring into Claude Code:
    1. Installs hooks (PreToolUse, PostToolUse, Stop) into ~/.claude/settings.json
    2. Adds SOMA status line to Claude Code UI
    3. Creates ~/.soma/ directory with clean engine state
    4. Creates soma.toml config if missing
    5. Optionally adds SOMA section to CLAUDE.md
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _find_soma_hook_command() -> str:
    """Find the best way to invoke soma-hook.

    Priority:
        1. soma-hook console script (if installed via pip)
        2. python -m soma.hooks.claude_code (fallback)
    """
    # Check if soma-hook is on PATH (installed via pip/pipx)
    soma_hook = shutil.which("soma-hook")
    if soma_hook:
        return "soma-hook"

    # Check if current python has soma installed
    python = sys.executable
    return f"{python} -m soma.hooks.claude_code"


def _find_statusline_command() -> str:
    """Find the best way to invoke soma-statusline."""
    soma_sl = shutil.which("soma-statusline")
    if soma_sl:
        return "soma-statusline"

    python = sys.executable
    return f"{python} -m soma.hooks.statusline"


def _install_hooks(settings_path: Path, hook_cmd: str) -> bool:
    """Install SOMA hooks into Claude Code settings.json. Returns True if changed."""
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, IOError):
            settings = {}

    hooks = settings.get("hooks", {})
    changed = False

    hook_configs = {
        "PreToolUse": {"timeout": 5},
        "PostToolUse": {"timeout": 5},
        "Stop": {"timeout": 10},
        "UserPromptSubmit": {"timeout": 3},
    }

    for hook_type, opts in hook_configs.items():
        hook_list = hooks.get(hook_type, [])

        # Check if SOMA hook already installed
        soma_installed = any(
            "soma" in str(h.get("command", ""))
            for entry in hook_list
            for h in entry.get("hooks", [])
        )

        if not soma_installed:
            entry = {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"CLAUDE_HOOK={hook_type} {hook_cmd}",
                        "timeout": opts["timeout"],
                    }
                ]
            }
            hook_list.append(entry)
            hooks[hook_type] = hook_list
            changed = True

    if changed:
        settings["hooks"] = hooks
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2))

    return changed


def _install_statusline(settings_path: Path, sl_cmd: str) -> bool:
    """Add SOMA status line to Claude Code. Returns True if changed."""
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, IOError):
            settings = {}

    if "statusLine" in settings:
        existing = settings["statusLine"]
        if isinstance(existing, dict):
            cmd = existing.get("command", "")
            if "soma" in cmd:
                return False
        # Overwrite non-SOMA statusLine (user will see the change in output)

    settings["statusLine"] = {
        "type": "command",
        "command": sl_cmd,
    }

    settings_path.write_text(json.dumps(settings, indent=2))
    return True


def _install_skills() -> bool:
    """Copy SOMA skill files to ~/.claude/skills/. Returns True if any were installed."""
    skills_target = Path.home() / ".claude" / "skills"
    skills_target.mkdir(parents=True, exist_ok=True)

    # Find skills — check bundled package location, then dev repo
    import soma
    soma_pkg = Path(soma.__file__).parent

    skills_source = None
    for candidate in [
        soma_pkg / "_skills",                                    # pip install (bundled)
        Path(__file__).parent.parent.parent.parent / "skills",   # dev repo
    ]:
        if candidate.is_dir() and any(candidate.glob("soma-*/SKILL.md")):
            skills_source = candidate
            break

    if skills_source is None:
        return False

    changed = False
    for skill_dir in skills_source.iterdir():
        if not skill_dir.is_dir() or not skill_dir.name.startswith("soma-"):
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        target_dir = skills_target / skill_dir.name
        target_file = target_dir / "SKILL.md"

        # Install or update
        if not target_file.exists() or target_file.read_text() != skill_file.read_text():
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file.write_text(skill_file.read_text())
            changed = True

    return changed


def _init_engine() -> bool:
    """Create clean SOMA engine state with Claude Code config. Returns True if created."""
    soma_dir = Path.home() / ".soma"
    soma_dir.mkdir(parents=True, exist_ok=True)
    engine_path = soma_dir / "engine_state.json"

    if engine_path.exists():
        return False

    try:
        from soma.engine import SOMAEngine
        from soma.persistence import save_engine_state
        from soma.hooks.common import CLAUDE_TOOLS
        from soma.cli.config_loader import CLAUDE_CODE_CONFIG

        engine = SOMAEngine(
            budget=CLAUDE_CODE_CONFIG["budget"],
            custom_weights=CLAUDE_CODE_CONFIG["weights"],
            custom_thresholds=CLAUDE_CODE_CONFIG["thresholds"],
        )
        engine.register_agent("claude-code", tools=CLAUDE_TOOLS)
        save_engine_state(engine, str(engine_path))
        engine.export_state(str(soma_dir / "state.json"))
        return True
    except Exception:
        return False


def run_setup_claude() -> None:
    """Set up SOMA for Claude Code."""
    print()
    print("  SOMA Setup for Claude Code")
    print("  ─────────────────────────")
    print("  Giving your Claude Code a nervous system...")
    print()

    changes = []
    warnings = []

    # 1. Find hook commands
    hook_cmd = _find_soma_hook_command()
    sl_cmd = _find_statusline_command()

    # 2. Install hooks
    settings_path = Path.home() / ".claude" / "settings.json"
    if _install_hooks(settings_path, hook_cmd):
        changes.append("Installed SOMA hooks (PreToolUse, PostToolUse, UserPromptSubmit, Stop)")
    else:
        print("  Hooks already installed. Skipping.")

    # 3. Install status line
    if _install_statusline(settings_path, sl_cmd):
        changes.append("Added SOMA status line to Claude Code UI")
    else:
        print("  Status line already configured. Skipping.")

    # 4. Init engine state
    if _init_engine():
        changes.append("Created ~/.soma/ with clean engine state")
    else:
        print("  Engine state exists. Skipping.")

    # 5. Create soma.toml with Claude Code optimized config
    soma_toml = Path("soma.toml")
    if not soma_toml.exists():
        try:
            from soma.cli.config_loader import save_config, CLAUDE_CODE_CONFIG
            save_config(CLAUDE_CODE_CONFIG, str(soma_toml))
            changes.append("Created soma.toml with Claude Code optimized config")
        except Exception:
            warnings.append("Could not create soma.toml")
    else:
        print("  soma.toml exists. Skipping.")

    # 6. Install slash command skills to ~/.claude/skills/
    if _install_skills():
        changes.append("Installed slash commands (/soma:status, /soma:config, /soma:control, /soma:help)")
    else:
        print("  Slash commands already installed. Skipping.")

    # 7. Add to CLAUDE.md (optional, non-destructive)
    claude_md = Path("CLAUDE.md")
    soma_block = (
        "\n## SOMA Monitoring\n\n"
        "This project uses SOMA Core for AI agent behavioral monitoring.\n"
        "Run `soma status` for a quick summary or `soma` for the live dashboard.\n"
    )
    if claude_md.exists():
        content = claude_md.read_text()
        if "SOMA" not in content:
            claude_md.write_text(content + soma_block)
            changes.append("Added SOMA section to CLAUDE.md")
    else:
        print("  No CLAUDE.md found. Skipping.")

    # Print results
    print()
    if changes:
        print("  Done! Your Claude Code now has a nervous system:")
        for c in changes:
            print(f"    + {c}")
    else:
        print("  Everything already set up. SOMA is active.")

    if warnings:
        print()
        for w in warnings:
            print(f"    ! {w}")

    print()
    print("  How it works:")
    print("    PreToolUse        — checks pressure, guides with suggestions, blocks only destructive ops")
    print("    PostToolUse       — records action, validates code, computes vitals")
    print("    UserPromptSubmit  — injects actionable tips into agent context")
    print("    Stop              — saves final state, cleans up session")
    print("    Status line       — shows live SOMA level in Claude Code UI")
    print()
    print("  Commands:")
    print("    soma status    — quick text summary")
    print("    soma mode      — switch operating mode (strict/relaxed/autonomous)")
    print("    soma           — live TUI dashboard")
    print()
    print("  Slash commands (inside Claude Code):")
    print("    /soma:status   — live monitoring status with tips")
    print("    /soma:config   — settings, modes, thresholds")
    print("    /soma:control  — quarantine, release, reset")
    print("    /soma:help     — full command reference")
    print()
    print("  Plugin install (alternative):")
    print("    /install tr00x/SOMA-Core")
    print()
    print("  To uninstall:")
    print("    soma uninstall-claude")
    print()


def run_setup_cursor() -> None:
    """Set up SOMA for Cursor AI coding tool."""
    import json as _json
    from soma.hooks.cursor import generate_cursor_config

    print()
    print("  SOMA Setup for Cursor")
    print("  ─────────────────────")
    print()

    config = generate_cursor_config()
    hooks_path = Path(".cursor") / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    if hooks_path.exists():
        try:
            existing = _json.loads(hooks_path.read_text())
            # Check if SOMA hooks already installed
            for entries in existing.get("hooks", {}).values():
                for entry in entries:
                    if "soma" in entry.get("command", ""):
                        print("  SOMA hooks already installed in .cursor/hooks.json")
                        print()
                        return
        except (_json.JSONDecodeError, IOError):
            pass

    hooks_path.write_text(_json.dumps(config, indent=2))
    print("  + Created .cursor/hooks.json with SOMA hooks")
    print()
    print("  Events monitored:")
    print("    preToolUse   — checks pressure, guides with suggestions")
    print("    postToolUse  — records action, validates code, computes vitals")
    print("    stop         — saves final state, cleans up session")
    print()


def run_setup_windsurf() -> None:
    """Set up SOMA for Windsurf (Codeium) AI coding tool."""
    import json as _json
    from soma.hooks.windsurf import generate_windsurf_config

    print()
    print("  SOMA Setup for Windsurf")
    print("  ───────────────────────")
    print()

    config = generate_windsurf_config()
    hooks_path = Path(".windsurf") / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    if hooks_path.exists():
        try:
            existing = _json.loads(hooks_path.read_text())
            for entries in existing.get("hooks", {}).values():
                for entry in entries:
                    if "soma" in entry.get("command", ""):
                        print("  SOMA hooks already installed in .windsurf/hooks.json")
                        print()
                        return
        except (_json.JSONDecodeError, IOError):
            pass

    hooks_path.write_text(_json.dumps(config, indent=2))
    print("  + Created .windsurf/hooks.json with SOMA hooks")
    print()
    print("  Events monitored:")
    print("    pre_run_command     — Bash command guidance")
    print("    pre_write_code      — file write guidance")
    print("    pre_read_code       — file read tracking")
    print("    post_run_command    — records Bash actions")
    print("    post_write_code     — validates written code")
    print("    post_read_code      — records file reads")
    print("    post_cascade_response — session end cleanup")
    print()
