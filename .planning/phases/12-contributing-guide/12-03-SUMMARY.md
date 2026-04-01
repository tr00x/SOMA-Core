---
plan: 12-03
phase: 12-contributing-guide
status: complete
started: 2026-03-31T21:30:00
completed: 2026-03-31T21:41:00
---

## Summary

Created VHS demo tape and helper script that runs a real SOMA engine session demonstrating behavioral monitoring of a degrading AI agent. 20 actions flow through the engine with pressure escalating from 0% (OBSERVE) through 40% (GUIDE) to 56% (WARN). Rich terminal output with pressure bars and vitals table. README updated with demo section.

## Key Files

### Created
- `demo.tape` — VHS tape script for terminal recording
- `demo_session.py` — Real SOMA engine demo with 20-action degrading agent scenario
- `demo.gif` — Generated terminal recording (867KB)

### Modified
- `README.md` — Added Demo section with GIF reference and VHS generation instructions

## Decisions
- Used `uv run` instead of `pip install` in tape — system Python is 3.9, SOMA requires 3.11+
- Moved inline Python to separate script — VHS parser doesn't support escaped quotes in Type commands
- Show pressure bar on every action for visual impact in GIF

## Self-Check: PASSED
- [x] demo.tape exists with valid VHS syntax
- [x] demo_session.py runs without errors
- [x] demo.gif generated successfully (867KB)
- [x] README.md references demo.gif
- [x] All data flows through real SOMA engine
