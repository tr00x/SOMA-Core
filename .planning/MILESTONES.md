# Milestones

## v0.5.0 Production Ready (Shipped: 2026-03-31)

**Phases completed:** 11 phases, 11 plans, 4 tasks

**Key accomplishments:**

- Async-aware soma.wrap() using inspect.iscoroutinefunction to detect and wrap async Anthropic/OpenAI clients with full SOMA pipeline
- Streaming interception for Anthropic (sync/async context manager) and OpenAI (stream=True iterator) with chunk accumulation and single-Action recording
- VitalsSnapshot.context_usage tracks cumulative tokens as fraction of context window; AuditLogger writes JSON Lines per action to ~/.soma/audit.jsonl with rotation

---
