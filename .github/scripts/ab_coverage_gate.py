"""A/B coverage release gate (P2.2).

The gate's job is to catch *asymmetric A/B bias* in the analytics
DB before it reaches PyPI — the failure mode that bit `2026-04-19 onward`
where one arm got rows and the other didn't, so any "X% helped"
claim was structurally distorted. It does **not** require that
every pattern has accumulated coverage: a brand-new pattern with
zero rows in both arms is "still bootstrapping" and is allowed
through, because the public README is explicitly status
``collecting`` until pairs cross the threshold.

A pattern PASSES iff **both arms cross MIN_PAIRS** (sufficient
matched evidence) **or both arms are below MIN_PAIRS** (no claim
being made). It FAILS only when one arm has crossed and the other
hasn't — that is the asymmetric bias the gate exists to catch.

**Known limitation**: a sub-MIN_PAIRS split such as ``14T/0C`` is
treated as ``collecting`` (passes), even though the ratio is
clearly skewed. The rule deliberately trades early-warning
sensitivity for the "ship while collecting" posture: as long as
``validate-patterns`` and the public README both gate effectiveness
claims on ``>=MIN_PAIRS``, an under-threshold imbalance is invisible
to consumers and not actually risky to ship. The first time it
flips to ``(15, 0)`` the gate trips. If you want earlier warning,
extend the rule to flag low-N skew separately.

Retired patterns (``soma.contextual_guidance.RETIRED_PATTERN_KEYS``)
are excluded from the top-N selection — they can never accumulate
new rows and would otherwise pin the gate to FAIL forever.

Usage::

    python .github/scripts/ab_coverage_gate.py check [--db PATH] [--json]
    python .github/scripts/ab_coverage_gate.py snapshot OUTPUT [--db PATH]
    python .github/scripts/ab_coverage_gate.py verify SNAPSHOT_PATH

* ``check`` reads the analytics DB directly and prints a coverage
  report; exits 0 iff every top-N active pattern is unbiased per
  the rule above.
* ``snapshot`` runs ``check`` and writes the result as JSON so the
  maintainer can commit a frozen audit trail alongside the release tag.
* ``verify`` re-validates the rule from that committed JSON. This
  is the subcommand CI runs in ``publish.yml`` — it doesn't need
  access to the live database, only to the committed snapshot.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

MIN_PAIRS = 15
TOP_N = 5
DEFAULT_DB = Path.home() / ".soma" / "analytics.db"

# Must stay in sync with ``soma.contextual_guidance.RETIRED_PATTERN_KEYS``.
# Hardcoded here because the gate runs as a standalone script in CI
# without the soma package installed.
RETIRED_PATTERN_KEYS: frozenset[str] = frozenset(
    {"_stats", "drift", "entropy_drop", "context"}
)


@dataclass
class PatternCoverage:
    pattern: str
    fires: int
    treatment: int
    control: int

    @property
    def passes(self) -> bool:
        # Asymmetric-bias rule: pass if both arms have crossed
        # MIN_PAIRS, or both arms are still below it. Fail only when
        # one arm has the evidence to make a claim and the other
        # doesn't — that's the structural bias the gate exists to
        # catch.
        both_above = self.treatment >= MIN_PAIRS and self.control >= MIN_PAIRS
        both_below = self.treatment < MIN_PAIRS and self.control < MIN_PAIRS
        return both_above or both_below

    @property
    def status(self) -> str:
        if self.treatment >= MIN_PAIRS and self.control >= MIN_PAIRS:
            return "ready"
        if self.treatment < MIN_PAIRS and self.control < MIN_PAIRS:
            return "collecting"
        return "biased"


@dataclass
class GateReport:
    db_path: str
    reset_ts: float
    min_pairs: int
    top_n: int
    patterns: list[PatternCoverage] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        # Empty top-N (no fires post-reset) is a pass — there's no
        # bias risk in shipping a release that hasn't recorded any
        # pairs yet. Bootstrapping is explicit in the README.
        return all(p.passes for p in self.patterns)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Inject derived fields per pattern so consumers (snapshots,
        # CI logs) don't have to recompute the rule.
        for entry, p in zip(d["patterns"], self.patterns):
            entry["status"] = p.status
            entry["passes"] = p.passes
        d["passes"] = self.passes
        return d


def _read_reset_ts(db_path: Path) -> float:
    """Return the timestamp of the most recent ab_reset.log entry, or 0.0.

    ab_reset.log lives next to the analytics DB. Missing / malformed
    lines are tolerated — the gate degrades to "count since the dawn
    of time" rather than erroring out.
    """
    log = db_path.parent / "ab_reset.log"
    if not log.exists():
        return 0.0
    latest = 0.0
    try:
        with log.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("ts")
                if isinstance(ts, (int, float)) and ts > latest:
                    latest = float(ts)
    except OSError:
        return 0.0
    return latest


def _top_patterns(conn: sqlite3.Connection, reset_ts: float, limit: int) -> list[tuple[str, int]]:
    # Exclude retired patterns: they can never accumulate new rows so
    # leaving them in top-N would pin the gate to FAIL forever.
    placeholders = ",".join("?" * len(RETIRED_PATTERN_KEYS))
    rows = conn.execute(
        f"SELECT pattern_key, COUNT(*) AS fires "
        f"FROM guidance_outcomes "
        f"WHERE timestamp >= ? "
        f"AND pattern_key NOT IN ({placeholders}) "
        f"GROUP BY pattern_key "
        f"ORDER BY fires DESC, pattern_key ASC "
        f"LIMIT ?",
        (reset_ts, *sorted(RETIRED_PATTERN_KEYS), limit),
    ).fetchall()
    return [(r[0], int(r[1])) for r in rows]


def _arm_counts(conn: sqlite3.Connection, pattern: str) -> tuple[int, int]:
    # Keep gate aligned with validate-patterns: only count rows that
    # carry a firing_id. Rows without one are bias-class legacy
    # (pre-2026-04-27) or future bugs leaking through unsanctioned
    # call paths — neither should inflate the release gate.
    rows = conn.execute(
        "SELECT arm, COUNT(*) FROM ab_outcomes "
        "WHERE pattern = ? AND firing_id IS NOT NULL "
        "GROUP BY arm",
        (pattern,),
    ).fetchall()
    counts = {arm: int(n) for arm, n in rows}
    return counts.get("treatment", 0), counts.get("control", 0)


def build_report(db_path: Path) -> GateReport:
    reset_ts = _read_reset_ts(db_path)
    report = GateReport(
        db_path=str(db_path), reset_ts=reset_ts,
        min_pairs=MIN_PAIRS, top_n=TOP_N,
    )
    if not db_path.exists():
        return report
    conn = sqlite3.connect(str(db_path))
    try:
        for pattern, fires in _top_patterns(conn, reset_ts, TOP_N):
            t, c = _arm_counts(conn, pattern)
            report.patterns.append(PatternCoverage(
                pattern=pattern, fires=fires, treatment=t, control=c,
            ))
    finally:
        conn.close()
    return report


def _format_human(report: GateReport) -> str:
    if not report.patterns:
        return (
            f"A/B coverage gate (db={report.db_path})\n"
            f"  top-{report.top_n} guidance_outcomes post-reset is empty — "
            f"no bias risk, gate PASSES."
        )
    lines = [
        f"A/B coverage gate (threshold: {report.min_pairs}T / {report.min_pairs}C; rule: no asymmetric bias)",
        f"  db:       {report.db_path}",
        f"  reset_ts: {report.reset_ts}",
        "",
        f"  {'pattern':<20}{'fires':>7}{'treatment':>12}{'control':>10}  status      verdict",
    ]
    for p in report.patterns:
        verdict = "PASS" if p.passes else "FAIL"
        lines.append(
            f"  {p.pattern:<20}{p.fires:>7}{p.treatment:>12}{p.control:>10}  {p.status:<11} {verdict}"
        )
    lines.append("")
    lines.append("  OVERALL: " + ("PASS" if report.passes else "FAIL"))
    return "\n".join(lines)


def _cmd_check(args) -> int:
    report = build_report(Path(args.db))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(_format_human(report))
    return 0 if report.passes else 1


def _cmd_snapshot(args) -> int:
    report = build_report(Path(args.db))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Scrub the maintainer's home path from the committed snapshot —
    # the audit trail only needs that the gate ran against the
    # canonical SOMA analytics location, not whose machine.
    payload = report.to_dict()
    payload["db_path"] = "~/.soma/analytics.db"
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(_format_human(report))
    print(f"\nSnapshot written to {output}")
    return 0 if report.passes else 1


def _cmd_verify(args) -> int:
    path = Path(args.snapshot)
    if not path.exists():
        print(f"Coverage snapshot missing: {path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"Coverage snapshot is not valid JSON: {e}", file=sys.stderr)
        return 2
    # Re-validate rather than trusting the committed 'passes' field —
    # future threshold changes must be applied retroactively.
    patterns_raw = data.get("patterns") or []
    patterns = [
        PatternCoverage(
            pattern=p.get("pattern", ""),
            fires=int(p.get("fires", 0)),
            treatment=int(p.get("treatment", 0)),
            control=int(p.get("control", 0)),
        )
        for p in patterns_raw
    ]
    report = GateReport(
        db_path=str(data.get("db_path", "")),
        reset_ts=float(data.get("reset_ts", 0.0)),
        min_pairs=MIN_PAIRS, top_n=TOP_N, patterns=patterns,
    )
    print(_format_human(report))
    return 0 if report.passes else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Read analytics DB and report coverage.")
    p_check.add_argument("--db", default=str(DEFAULT_DB))
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=_cmd_check)

    p_snap = sub.add_parser("snapshot", help="Write a coverage snapshot JSON file.")
    p_snap.add_argument("output")
    p_snap.add_argument("--db", default=str(DEFAULT_DB))
    p_snap.set_defaults(func=_cmd_snapshot)

    p_verify = sub.add_parser("verify", help="Re-validate a committed snapshot.")
    p_verify.add_argument("snapshot")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
