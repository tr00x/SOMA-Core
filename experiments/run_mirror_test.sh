#!/usr/bin/env bash
set -euo pipefail

# ── Mirror Live Test Runner ──
# Runs a Claude Code session against the test project and captures
# Mirror's session context injections for analysis.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/test_project"
SOMA_DIR="$HOME/.soma"

echo "=== Mirror Live Test ==="
echo ""

# 1. Check SOMA hooks are installed
if ! command -v soma-hook &>/dev/null; then
    echo "ERROR: soma-hook not found in PATH."
    echo "Run: pip install -e . (from SOMA2 root)"
    exit 1
fi

# Check Claude Code has hooks configured
SETTINGS_FILE="$HOME/.claude/settings.json"
if [ -f "$SETTINGS_FILE" ]; then
    if grep -q "soma-hook" "$SETTINGS_FILE" 2>/dev/null; then
        echo "[OK] SOMA hooks found in Claude Code settings"
    else
        echo "WARNING: soma-hook not found in $SETTINGS_FILE"
        echo "Run: soma setup-claude"
    fi
else
    echo "WARNING: Claude Code settings not found at $SETTINGS_FILE"
    echo "Run: soma setup-claude"
fi

# 2. Set up test project
echo ""
echo "Setting up test project..."
python3 "$SCRIPT_DIR/mirror_test_setup.py"

# 3. Clear session state for clean experiment
echo ""
echo "Clearing SOMA session state..."
rm -rf "$SOMA_DIR/sessions/"
rm -f "$SOMA_DIR/engine_state.json"
rm -f "$SOMA_DIR/state.json"
rm -f "$SOMA_DIR/patterns.json"
echo "[OK] Clean slate"

# 4. Show instructions
echo ""
echo "════════════════════════════════════════════════"
echo "  Ready. Run this command in another terminal:"
echo ""
echo "  cd $PROJECT_DIR"
echo "  claude 'Fix the failing tests in test_main.py. Run the tests first to see the errors.'"
echo ""
echo "  Then come back here and press Enter to analyze."
echo "════════════════════════════════════════════════"
echo ""
read -r -p "Press Enter after Claude Code session completes..."

# 5. Analyze results
echo ""
echo "=== Session Results ==="
echo ""

# Find the most recent session directory
LATEST_SESSION=$(ls -td "$SOMA_DIR/sessions"/cc-* 2>/dev/null | head -1)

if [ -z "$LATEST_SESSION" ]; then
    echo "No session data found in $SOMA_DIR/sessions/"
    echo "Make sure SOMA hooks are configured and the Claude Code session ran."
    exit 1
fi

echo "Session: $(basename "$LATEST_SESSION")"
echo ""

# Action log
if [ -f "$LATEST_SESSION/action_log.json" ]; then
    echo "── Action Log ──"
    python3 -c "
import json
log = json.loads(open('$LATEST_SESSION/action_log.json').read())
for i, entry in enumerate(log, 1):
    err = ' ERROR' if entry.get('error') else ''
    tool = entry.get('tool', '?')
    f = entry.get('file', '')
    short_f = f.rsplit('/', 1)[-1] if f else ''
    print(f'  #{i:2d} {tool:<12s} {short_f:<30s}{err}')
print(f'  Total: {len(log)} actions, {sum(1 for e in log if e.get("error"))} errors')
"
    echo ""
fi

# Pressure trajectory
if [ -f "$LATEST_SESSION/trajectory.json" ]; then
    echo "── Pressure Trajectory ──"
    python3 -c "
import json
traj = json.loads(open('$LATEST_SESSION/trajectory.json').read())
for i, p in enumerate(traj, 1):
    bar = '█' * int(p * 20) + '░' * (20 - int(p * 20))
    print(f'  #{i:2d} {bar} {p:.1%}')
if traj:
    print(f'  Peak: {max(traj):.1%} at action #{traj.index(max(traj))+1}')
    print(f'  Final: {traj[-1]:.1%}')
"
    echo ""
fi

# Pattern DB
if [ -f "$SOMA_DIR/patterns.json" ]; then
    echo "── Learned Patterns ──"
    python3 -c "
import json
db = json.loads(open('$SOMA_DIR/patterns.json').read())
if not db:
    print('  (empty — no patterns learned yet)')
else:
    for key, val in db.items():
        if isinstance(val, dict):
            s = val.get('success_count', 0)
            f = val.get('fail_count', 0)
            rate = s / (s + f) if (s + f) > 0 else 0
            print(f'  {key}: {s}s/{f}f ({rate:.0%}) — {val.get("context_text", "")[:60]}')
        else:
            print(f'  {key}: {val[:60]}')
"
    echo ""
fi

# Quality
if [ -f "$LATEST_SESSION/quality.json" ]; then
    echo "── Quality ──"
    python3 -c "
import json
q = json.loads(open('$LATEST_SESSION/quality.json').read())
print(f'  Writes: {q.get("total_writes", 0)}, Syntax errors: {q.get("syntax_errors", 0)}, Lint: {q.get("lint_issues", 0)}')
"
    echo ""
fi

echo "── Full Analysis ──"
echo "Run: python3 experiments/analyze_mirror_test.py"
