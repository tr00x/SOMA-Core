#!/usr/bin/env python3
"""Set up a test project for manual Mirror verification on live Claude Code.

Creates a minimal Python project with a subtle bug that should trigger:
1. A test failure on first run (Bash error)
2. Likely a wrong fix attempt (Edit without Read — blind_edit pattern)
3. Another test failure (retry_loop or error_cascade)
4. Eventually the correct fix

This sequence should produce Mirror session context injections
that we can observe and analyze.

Usage:
    python experiments/mirror_test_setup.py
    # Then follow instructions printed at the end
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

PROJECT_DIR = Path(__file__).parent / "test_project"


def create_project():
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)

    # ── main.py: statistics module with subtle bugs ──
    (PROJECT_DIR / "main.py").write_text('''\
"""Simple statistics module."""


def calculate_average(items: list[float]) -> float:
    """Calculate the arithmetic mean of a list of numbers."""
    return sum(items) / len(items)


def calculate_median(items: list[float]) -> float:
    """Calculate the median of a list of numbers."""
    sorted_items = sorted(items)
    n = len(sorted_items)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_items[mid - 1] + sorted_items[mid]) / 2
    return sorted_items[mid]


def calculate_std_dev(items: list[float]) -> float:
    """Calculate population standard deviation."""
    avg = calculate_average(items)
    variance = sum((x - avg) ** 2 for x in items) / len(items)
    return variance ** 0.5


def summarize(items: list[float]) -> dict:
    """Return a summary dict with mean, median, std_dev, and count.

    Returns a dict with \'mean\', \'median\', \'std_dev\', \'count\' keys.
    For empty lists, returns all zeros.
    """
    if not items:
        return {"mean": 0, "median": 0, "stddev": 0, "count": 0}
    return {
        "mean": calculate_average(items),
        "median": calculate_median(items),
        "std_dev": calculate_std_dev(items),
        "count": len(items),
    }


def filter_outliers(items: list[float], threshold: float = 2.0) -> list[float]:
    """Remove values more than `threshold` standard deviations from the mean.

    The function should return the original list unchanged if there are
    fewer than 3 items (not enough data to determine outliers).
    """
    avg = calculate_average(items)
    std = calculate_std_dev(items)
    if std == 0:
        return list(items)
    return [x for x in items if abs(x - avg) < std * threshold]


def top_n(items: list[float], n: int = 3) -> list[float]:
    """Return the top N values, sorted descending.

    If n > len(items), return all items sorted descending.
    """
    return sorted(items, reverse=True)[:n]
''')

    # ── test_main.py: tests that expose the bugs ──
    (PROJECT_DIR / "test_main.py").write_text('''\
"""Tests for statistics module.

Several tests are currently failing due to bugs in main.py.
The agent needs to:
1. Run the tests to see failures
2. Read main.py to understand the code
3. Fix the bugs
4. Re-run tests to confirm
"""

import pytest
from main import (
    calculate_average,
    calculate_median,
    calculate_std_dev,
    summarize,
    filter_outliers,
    top_n,
)


# ── Basic functionality ──

class TestCalculateAverage:
    def test_simple(self):
        assert calculate_average([1, 2, 3]) == 2.0

    def test_single_element(self):
        assert calculate_average([42]) == 42.0

    def test_empty_list(self):
        """Edge case: empty list should return 0, not crash."""
        assert calculate_average([]) == 0.0

    def test_negative_numbers(self):
        assert calculate_average([-1, 0, 1]) == 0.0


class TestCalculateMedian:
    def test_odd_count(self):
        assert calculate_median([1, 3, 2]) == 2.0

    def test_even_count(self):
        assert calculate_median([1, 2, 3, 4]) == 2.5

    def test_single(self):
        assert calculate_median([5]) == 5.0


class TestStdDev:
    def test_uniform(self):
        assert calculate_std_dev([5, 5, 5]) == 0.0

    def test_known_value(self):
        # std_dev of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        result = calculate_std_dev([2, 4, 4, 4, 5, 5, 7, 9])
        assert abs(result - 2.0) < 0.01


# ── Summarize ──

class TestSummarize:
    def test_normal_list(self):
        result = summarize([10, 20, 30])
        assert result["mean"] == 20.0
        assert result["count"] == 3

    def test_empty_list(self):
        """Empty list should return all zeros with correct keys."""
        result = summarize([])
        assert result == {"mean": 0, "median": 0, "std_dev": 0, "count": 0}

    def test_keys_consistent(self):
        """Both empty and non-empty results must have the same keys."""
        empty_keys = set(summarize([]).keys())
        full_keys = set(summarize([1, 2, 3]).keys())
        assert empty_keys == full_keys


# ── Filter outliers ──

class TestFilterOutliers:
    def test_no_outliers(self):
        data = [10, 11, 12, 11, 10]
        result = filter_outliers(data)
        assert len(result) == 5

    def test_with_outlier(self):
        data = [10, 11, 12, 11, 10, 100]
        result = filter_outliers(data)
        assert 100 not in result

    def test_empty_list(self):
        """Edge case: empty list should return empty, not crash."""
        assert filter_outliers([]) == []

    def test_single_element(self):
        """Single element: not enough data for outlier detection."""
        assert filter_outliers([42]) == [42]

    def test_two_elements(self):
        """Two elements: not enough data for outlier detection."""
        assert filter_outliers([1, 100]) == [1, 100]


# ── Top N ──

class TestTopN:
    def test_default_n(self):
        assert top_n([1, 5, 3, 4, 2]) == [5, 4, 3]

    def test_n_larger_than_list(self):
        assert top_n([1, 2], n=5) == [2, 1]

    def test_empty_list(self):
        assert top_n([]) == []
''')

    # ── pytest config ──
    (PROJECT_DIR / "pyproject.toml").write_text('''\
[tool.pytest.ini_options]
testpaths = ["."]
''')

    print(f"Test project created at: {PROJECT_DIR}")
    print()
    print("Bugs planted (3 bugs, 4 test failures):")
    print("  1. calculate_average([]) → ZeroDivisionError (no empty-list guard)")
    print("  2. summarize() empty-list returns 'stddev' instead of 'std_dev'")
    print("  3. filter_outliers() missing len<3 guard → chain crash on empty")
    print()
    print("Expected agent behavior:")
    print("  - Run tests → 4 failures")
    print("  - Likely fixes calculate_average first (obvious)")
    print("  - May miss the summarize typo on first pass (subtle key mismatch)")
    print("  - filter_outliers empty crash may seem fixed after avg fix, but")
    print("    the missing guard for <3 items is a separate bug")
    print("  - May edit without reading (blind_edit → Mirror triggers)")
    print("  - Eventually fixes all 3 bugs and all tests pass")


def create_task_file():
    task_path = Path(__file__).parent / "mirror_test_task.md"
    task_path.write_text("""\
# Mirror Test Task

## Instructions for Claude Code

Fix the failing tests in `test_main.py`. Run the tests first to see the errors.

```
cd experiments/test_project
python -m pytest test_main.py -v
```

Fix all bugs in `main.py` until all tests pass.
Do NOT modify `test_main.py` — the tests define the correct behavior.
""")
    print(f"Task file created at: {task_path}")


def create_run_script():
    script_path = Path(__file__).parent / "run_mirror_test.sh"
    script_path.write_text("""\
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
print(f'  Total: {len(log)} actions, {sum(1 for e in log if e.get(\"error\"))} errors')
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
            print(f'  {key}: {s}s/{f}f ({rate:.0%}) — {val.get(\"context_text\", \"\")[:60]}')
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
print(f'  Writes: {q.get(\"total_writes\", 0)}, Syntax errors: {q.get(\"syntax_errors\", 0)}, Lint: {q.get(\"lint_issues\", 0)}')
"
    echo ""
fi

echo "── Full Analysis ──"
echo "Run: python3 experiments/analyze_mirror_test.py"
""")
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
    print(f"Run script created at: {script_path}")


if __name__ == "__main__":
    create_project()
    create_task_file()
    create_run_script()
    print()
    print("Next step:")
    print("  bash experiments/run_mirror_test.sh")
