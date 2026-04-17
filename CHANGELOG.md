# Changelog

## 2026.4.0 (unreleased)

### Contextual Guidance Patterns
- feat: panic detector + followthrough for new patterns
- feat: healing transition prescriptions -- data-backed tool suggestions
- feat: bash retry intercept -- fires after 1st Bash fail before blind retry
- feat: tool entropy pattern -- detects monotool tunnel vision

### Intelligence Pipeline
- feat: trigram similarity for lesson matching -- catches same error type with different paths
- feat: contextual guidance -- pattern-based deep injection replaces abstract pressure messages
- feat: SOMA ultraplan -- self-healing context, cross-session lessons, anomaly fingerprinting, cost spiral detection

### Benchmarking
- feat: A/B benchmark framework -- 10 tasks, statistical verdict, honest results
- fix: benchmark uses public get_baseline() instead of private _agents access
- fix: benchmark feedback -- persist guidance state, cap retry spam, pass real errors

### Hooks & Integration
- fix: hook path now wires lesson_store + baseline into ContextualGuidance
- fix: wrap.py _track_action now passes error output for lesson matching
- fix: add PostToolUseFailure handler -- error detection was blind to tool failures
- feat: actionable guidance messages + budget warning pattern
- feat: guidance effectiveness tracking -- record outcomes to analytics
- feat: analytics source tagging + data cleanup

### Code Quality
- fix: code review fixes -- atomic writes, file size guard, public API, error output in action log
- fix: skip dashboard API tests when fastapi not installed (CI compatibility)
- fix: resolve CI lint failures -- unused import + F821 ignore

## 0.7.0

### Dashboard Rebuild
- feat(dashboard): Tool Usage and Action Timeline side by side
- feat(dashboard): live agent indicator -- pulsing LIVE badge when action_count changes
- feat(dashboard): compact table view for 6+ agents, cards for <=6
- fix(dashboard): settings save now persists -- reload config after PATCH
- fix(dashboard): config save actually works now -- write_text not write_bytes

### Documentation
- docs: SOMA impact validation plan -- prove it works or kill it
- docs: fresh Playwright screenshots for v0.7.0 dashboard
- docs: update README, CHANGELOG, QUICKSTART for v0.7.0 dashboard rebuild
