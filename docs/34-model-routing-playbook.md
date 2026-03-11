# Model Routing Playbook (Agent + Task + Fallback)

Last updated: 2026-03-09

## Why this exists

This playbook keeps routing deterministic and cheap by default, while preserving quality for hard tasks.

## Agent Defaults

Policy source: [config/agents.yaml](/Users/palba/Projects/Personal/Clawdio/config/agents.yaml) (`routing_overrides.agent_task_matrix`).

1. `coordinator`: `L1` for triage/planning, `L2` for ambiguity, `L3` for architecture decisions.
2. `researcher`: `L1` for collection, `L2` for synthesis, `L3` only for high-impact recommendations.
3. `builder`: `L1` for tiny patches, `L2` for normal builds, `L3` for major refactors.
4. `ops_guard`: `L0` for deterministic health checks, `L1` for summaries, `L2` for RCA.

## Situation-Based Routing

Policy source: [config/models.yaml](/Users/palba/Projects/Personal/Clawdio/config/models.yaml) (`routing.decision_matrix`).

1. Deterministic workflow tasks -> `L0_no_model`.
2. Quick transformations and short summaries -> `L1_low_cost`.
3. Research synthesis and coding work -> `L2_balanced`.
4. Architecture and high ambiguity -> `L3_heavy` with approval.
5. External write-like tasks (send/post/trigger) -> low lane plus approval gate.

## Provider Preference by Lane

1. `L1_low_cost`: `google_ai_studio_free` -> `gemini-2.5-flash-lite`
2. `L1_openrouter_free_fallback`: `openrouter_free_overflow` -> `openrouter/free`
3. `L2_balanced`: `openai_subscription_session` -> `gpt-5.3-codex-spark`, then `google_ai_studio_free` -> `gemini-2.5-flash`, then `openrouter_free_overflow` -> `openrouter/free`, then `anthropic_credit_pool` -> `claude-sonnet-4-20250514`
4. `L3_heavy`: `openai_subscription_session` -> `gpt-5.4`, then `anthropic_credit_pool` -> `claude-sonnet-4-20250514`, fallback `google_ai_studio_free` -> `gemini-2.5-pro`
5. `codex` and `gemini` CLIs remain supervised tool fallbacks only, not unattended providers.
6. `openai_subscription_session` is an interactive premium lane, not a background-safe automation provider.

## Agent-Specific Chat Bias

Chat runtimes now honor per-agent provider preferences from [config/agents.yaml](/Users/palba/Projects/Personal/Clawdio/config/agents.yaml) (`agents.*.chat_routing`).

Recommended reading of the current policy:

1. `assistant`
   - default cheap/fast path for reminders, tasks, calendar, and general organization
   - stays on Google free first for most everyday conversation
   - may escalate to the OpenAI subscription lane for harder cross-app planning
2. `researcher`
   - prefers `openai_subscription_session` first on `L2/L3`
   - pins `gpt-5.1` for synthesis and `gpt-5.4` for the heaviest ambiguity
   - uses Anthropic as a strong second opinion
   - falls back to Google/OpenRouter when premium lanes are unavailable
3. `builder`
   - prefers `openai_subscription_session` first for coding/integration and hard implementation work
   - pins `gpt-5.1-codex-mini` for normal build work and `gpt-5.4` for major design/refactor work
   - keeps Anthropic as the first reserve lane
   - uses Google/OpenRouter as cost-aware fallbacks
4. `fitness_coach`
   - stays deterministic for workout control/logging
   - uses chat lanes only for coaching, progression, substitutions, and planning
   - prefers `openai_subscription_session` with `gpt-5.3-codex-spark` for reflective coaching and `gpt-5.1` for program redesign
5. `ops_guard`
   - stays cheap by default
   - uses higher lanes only for RCA or improvement analysis

## Fallback Rules

1. Retry once with smaller context.
2. Follow lane fallback list for the selected situation.
3. Do not exceed two automatic lane hops.
4. If no acceptable lane remains for high-impact work, pause and request approval.

## Anthropic Credit Discipline

Treat Anthropic as reserve capacity:

1. Use only for complex design/architecture or second-opinion passes.
2. Keep approval required.
3. Keep a daily call cap until telemetry proves stable cost behavior.
4. If credits run low, remove Anthropic from priority lists and continue with Codex + Google lanes.

## Operating Modes

Switch mode by editing `routing_overrides.active_mode` in [config/agents.yaml](/Users/palba/Projects/Personal/Clawdio/config/agents.yaml):

1. `strict_cost`: for high-volume low-risk periods.
2. `balanced_default`: daily default.
3. `quality_push`: temporarily for key deliverables.

## Minimum Viable Routing for Now

If you want the simplest stable setup:

1. Keep `balanced_default`.
2. Use Google free + OpenRouter free for `L1`.
3. Keep unattended/background work on API-safe lanes only.
4. Use the OpenAI subscription/session lane only for operator-triggered hard work with bigger limits.
5. Use Codex CLI or Gemini CLI only as explicit local tools for supervised coding/repo tasks.
6. Enable Anthropic only when explicitly needed.
7. Keep the chosen lane/provider/model visible in runtime state and operator-facing status outputs.

## Interactive Premium Lane

The `openai_subscription_session` provider is intentionally modeled separately from API-key providers.

1. It is for premium interactive work where you want bigger limits and stronger quality than the free lane.
2. It should be used for operator-triggered hard tasks, not cron, reminder delivery, or unattended workflows.
3. Its transport is a bounded non-interactive `codex exec` call backed by the logged-in ChatGPT session, so it is suitable for interactive work but not unattended cron.
4. In the current architecture it is the preferred premium lane for `researcher`, `builder`, and conversational `fitness_coach`, and the secondary premium lane for `assistant`.

## OpenAI model notes

The current OpenAI pins are the names currently configured for your authenticated Codex session lane:

1. `gpt-5.3-codex-spark` for fast premium conversational work
2. `gpt-5.1` for stronger research synthesis
3. `gpt-5.1-codex-mini` for normal coding/build work
4. `gpt-5.4` for the heaviest reasoning lane

These route targets are controlled by this repo configuration, not inferred from old OpenClaw backups.

## Inspect The Real Wiring

Use:

1. [provider_smoke_check.py](/Users/palba/Projects/Personal/Clawdio/scripts/provider_smoke_check.py)
2. [docs/51-provider-smoke-checks.md](/Users/palba/Projects/Personal/Clawdio/docs/51-provider-smoke-checks.md)
3. [model_route_decider.py](/Users/palba/Projects/Personal/Clawdio/scripts/model_route_decider.py)

Examples:

```bash
python3 scripts/model_route_decider.py --situation quick_read_write --json
python3 scripts/provider_smoke_check.py --env-file secrets/openclaw.env --json
```
