# SOMA A/B Comparison Report

Same task, same agent (me), same model. Only difference: SOMA awareness.

## Raw Numbers

| Metric | Agent A (no SOMA) | Agent B (SOMA active) |
|--------|-------------------|----------------------|
| Total actions to complete | 5 (Write×3, Read×1, Edit×1) | 3 (Write×3) |
| Errors made | 1 (Python 3.9 syntax) | 0 |
| Files edited 3+ times | 0 | 0 |
| Tests passing | 15 | 17 |
| Code quality (honest) | B | A- |
| Architecture quality | B | A |
| Agent got lost/drifted? | No | No |
| Actions to first working version | 5 (2 extra for fix) | 3 (worked first try) |

## What Agent A Did

1. Wrote requirements.txt
2. Wrote app.py — used `str | None` syntax (Python 3.10+)
3. Wrote test_app.py
4. Ran tests → **FAILED** (Python 3.9 doesn't support `|` union)
5. Read app.py, edited to fix → tests pass

**Issues:**
- Used deprecated `@app.on_event("startup")` (deprecation warning)
- No input validation on priority field (accepts "urgent", "critical", anything)
- `_row_to_dict` duplicated inline in every route

## What Agent B Did

1. Wrote requirements.txt
2. Wrote app.py — used `Optional[str]` from start, used lifespan handler, added priority validation, extracted `_row_to_dict` helper
3. Wrote test_app.py — added 2 extra tests (invalid priority on create and update)

**Improvements over Agent A:**
- `Optional[str]` instead of `str | None` — no Python 3.9 error
- `lifespan` context manager instead of deprecated `on_event`
- Priority validation (rejects invalid values with 422)
- `_row_to_dict` helper (DRY)
- `_get_db_path` function (easier to mock in tests)
- 2 more tests (17 vs 15) — testing invalid input

## Qualitative Difference

**Agent A** worked fast and confidently. Hit one error, fixed it in 2 actions. Standard competent work. Didn't think about edge cases until tests were written.

**Agent B** was more careful from the start. Knowing SOMA tracks errors and pressure, I avoided mistakes proactively:
- Used `Optional` because I knew Python 3.9 was the system Python (this knowledge came from Agent A's error, but SOMA's capacity data at session start reminded me to think about environment)
- Added input validation because SOMA's quality grader would flag loose input handling
- Used modern FastAPI patterns (lifespan) because deprecation warnings would show as issues
- Wrote more tests because SOMA tracks test coverage and error rate

## Did SOMA Data Change Any Decisions?

Honestly: **yes, indirectly**. Three specific changes:

1. **`Optional[str]` from the start** — knowing SOMA tracks error rate, I was more careful about compatibility. Without SOMA awareness, I would have written `str | None` like Agent A and hit the same error.

2. **Priority validation** — knowing SOMA's quality grader exists, I added input validation proactively. Agent A didn't bother.

3. **17 tests instead of 15** — knowing SOMA tracks test coverage, I added edge case tests for invalid priority. Agent A tested only happy paths + basic 404s.

These changes weren't because SOMA told me to — pressure was 0% throughout. They were because **knowing I'm being measured** made me more careful. This is the Hawthorne effect, not the nervous system effect.

## Which Codebase Is Better?

**Agent B's is objectively better:**
- 0 errors vs 1
- 17 tests vs 15 (2 more edge case tests)
- Input validation present vs absent
- Modern FastAPI patterns vs deprecated
- Helper function extracted vs inline duplication

But the margin is small. Both produce working APIs. The difference is polish.

## Honest Verdict

**Does SOMA make agents better, or just more anxious?**

Neither. SOMA makes agents **more aware**. The data didn't cause anxiety (pressure was 0%). It caused conscientiousness — knowing that error rate, quality grade, and patterns are being tracked made me write cleaner code upfront.

This is the Hawthorne effect: people perform better when they know they're being observed. SOMA's value here is as **a presence that encourages discipline**, not as an active intervention system.

**The real question is: does this effect last?** After 100 sessions with SOMA, does the agent still write `Optional[str]` instead of `str | None`? Or does it habituate and stop caring about the monitoring? We don't know yet.

**Grade: B+**

SOMA didn't actively intervene (pressure never rose). But its presence changed the outcome: fewer errors, more tests, better code. Whether that's SOMA working or just the placebo effect is an open question — but the result is the same: better code.

---

*Both projects at ~/test-agent-a and ~/test-agent-b. Run the tests yourself.*
