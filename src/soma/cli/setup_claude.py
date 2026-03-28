"""soma setup-claude — one command to integrate SOMA into Claude Code."""

from __future__ import annotations

import json
from pathlib import Path


CLAUDE_MD_BLOCK = """
## SOMA Monitoring

This project uses SOMA Core for AI agent monitoring.
When running agents or subagents, wrap API clients with SOMA:

```python
import soma
client = soma.wrap(your_client, budget={"tokens": 50000})
```

Run `soma` in a separate terminal to see the live dashboard.
Run `soma status` for a quick text summary.
"""

HOOK_COMMAND = 'python3 -c "import soma; print(\'SOMA active\')" 2>/dev/null || true'


def run_setup_claude() -> None:
    """Set up SOMA for Claude Code projects."""
    print()
    print("  SOMA Setup for Claude Code")
    print("  ─────────────────────────")
    print()

    changes = []

    # 1. Add to CLAUDE.md
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        content = claude_md.read_text()
        if "SOMA" not in content:
            claude_md.write_text(content + "\n" + CLAUDE_MD_BLOCK)
            changes.append("Added SOMA section to CLAUDE.md")
        else:
            print("  CLAUDE.md already has SOMA section. Skipping.")
    else:
        claude_md.write_text("# Project Instructions\n" + CLAUDE_MD_BLOCK)
        changes.append("Created CLAUDE.md with SOMA instructions")

    # 2. Create soma.toml if missing
    soma_toml = Path("soma.toml")
    if not soma_toml.exists():
        from soma.cli.config_loader import save_config, DEFAULT_CONFIG
        save_config(DEFAULT_CONFIG, str(soma_toml))
        changes.append("Created soma.toml with default config")
    else:
        print("  soma.toml already exists. Skipping.")

    # 3. Create ~/.soma directory
    soma_dir = Path.home() / ".soma"
    soma_dir.mkdir(parents=True, exist_ok=True)
    changes.append(f"Created {soma_dir}")

    # 4. Create a slash command for Claude Code
    commands_dir = Path(".claude") / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    soma_cmd = commands_dir / "soma-status.md"
    if not soma_cmd.exists():
        soma_cmd.write_text(
            "# SOMA Status\n\n"
            "Check SOMA monitoring status for this project.\n\n"
            "Run this command:\n"
            "```bash\n"
            "soma status\n"
            "```\n\n"
            "To open the full dashboard:\n"
            "```bash\n"
            "soma\n"
            "```\n"
        )
        changes.append("Created /soma-status Claude Code command")

    # Print results
    print()
    if changes:
        print("  Done! Changes made:")
        for c in changes:
            print(f"    + {c}")
    else:
        print("  Everything already set up.")

    print()
    print("  Next steps:")
    print("    1. Open a new terminal and run: soma")
    print("    2. In Claude Code, use: /soma-status")
    print("    3. In your code, add: client = soma.wrap(your_client)")
    print()
