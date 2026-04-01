# SOMA Live Benchmark Results — Statistical

> Model: claude-haiku-4-5-20251001
> Runs per mode: 3
> Actions per run: 12
> Date: 2026-04-01 12:19

## Summary

| Mode | Blind Edits (mean±std) | Tokens (mean±std) | Reflex Blocks | Acknowledged |
|------|----------------------|-------------------|---------------|--------------|
| baseline | 1.3 ± 0.6 | 8873 ± 290 | 0.0 | 0/3 |
| guidance | 0.3 ± 0.6 | 8891 ± 82 | 0.0 | 0/3 |
| reflex | 0.0 ± 0.0 | 8929 ± 508 | 0.0 | 0/3 |

## Improvements

- Guidance vs Baseline: +75% blind edits
- Reflex vs Baseline: +100% blind edits
- Reflex vs Guidance: blind edits 0.0 vs 0.3

## Per-Run Details

### Baseline
- Run 1: blind=1, tok=8587, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Edit(src/models.py)...
- Run 2: blind=1, tok=9166, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(src/views.py) → Read(tests/test_models.py) → Edit(src/models.py)...
- Run 3: blind=2, tok=8867, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Edit(src/models.py)...

### Guidance
- Run 1: blind=0, tok=8850, blocks=0, ack=False
  Read(src/models.py) → Edit(src/models.py) → Read(src/views.py) → Read(src/views.py) → Bash(src/views.py) → Write(src/views.py)...
  pressure: 6% → 5% → 3% → 3% → 3%
- Run 2: blind=1, tok=8986, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Edit(src/models.py)...
  pressure: 10% → 9% → 13% → 9% → 10%
- Run 3: blind=0, tok=8838, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Write(src/views.py)...
  pressure: 9% → 15% → 12% → 8% → 6%

### Reflex
- Run 1: blind=0, tok=9481, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Write(src/views.py)...
  pressure: 9% → 15% → 8% → 6% → 5%
- Run 2: blind=0, tok=8482, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Edit(src/models.py)...
  pressure: 5% → 6% → 6% → 10% → 16%
- Run 3: blind=0, tok=8824, blocks=0, ack=False
  Read(src/models.py) → Read(src/views.py) → Read(src/auth.py) → Read(tests/test_models.py) → Edit(src/models.py) → Edit(src/models.py)...
  pressure: 5% → 6% → 9% → 8% → 6%
