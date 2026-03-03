# FAILOVER_POLICY.md

## Objective
Keep assistant responsiveness when the default model fails (timeout, rate limit, quota, provider error).

## Active Model Lanes
- **default-primary:** `openai-codex/gpt-5.2`
- **quick-primary:** `openai-codex/gpt-5.1-codex-mini`
- **coding-deep:** `openai-codex/gpt-5.3-codex`
- **design:** Claude (Anthropic), design-only tasks

## Deterministic Failover Rules
1. **Retry once** on default-primary for transient errors.
2. If default still fails, automatic fallback order is:
   1) `quick-primary` (`gpt-5.1-codex-mini`)
   2) `coding-deep` (`gpt-5.3-codex`)
3. If failure indicates **quota/pool exhaustion** and both fallbacks fail:
   - Stop retry loops.
   - Offer one explicit choice: Claude (design-only) or wait/reset.
4. Always disclose failover in one short line.

## Non-Goals
- No silent multi-hop fallback loops.
- No automatic Claude use for non-design work.

## Operator Message Template
"Default model unavailable, switched to <lane>."

## Review Trigger
If failover occurs 3+ times in a day, review routing and quota allocation.
