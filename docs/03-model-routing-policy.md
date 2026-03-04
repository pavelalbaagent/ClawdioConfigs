# Model Routing Policy (Rules + Fallbacks)

## Goal

Use deterministic routing so cost stays controlled and quality only scales up when needed.

## Provider Strategy (Current Access)

1. `Google AI Studio free` is the default throughput lane.
2. `OpenRouter free` is overflow only when Google free is limited.
3. `Codex subscription (CLI)` is the primary heavy supervised lane for coding/planning.
4. `Anthropic credits` are a reserve lane for complex design or second-opinion runs.

## Routing Priority

1. Prefer deterministic path (`L0_no_model`) whenever logic can run without an LLM.
2. For LLM work, start from the lowest sufficient lane by task class.
3. Retry once with reduced context on rate-limit/timeouts.
4. Fallback across configured lanes only.
5. If high-impact output has no healthy lane, pause and request approval.

## Task/Situation Matrix

Policy source of truth: [config/models.yaml](/Users/palba/Projects/Clawdio/config/models.yaml) (`routing.decision_matrix`).

| Situation | Preferred lane | Provider preference | Fallbacks | Approval |
|---|---|---|---|---|
| Deterministic workflow (cron, reminders, parsing) | `L0_no_model` | none | none | No |
| Quick read/write (summary, rewrite, extract) | `L1_low_cost` | Google free | `L1_openrouter_free_fallback` -> `L2_balanced` | No |
| Inbox triage + digest | `L1_low_cost` | Google free | `L1_openrouter_free_fallback` -> `L2_balanced` | No |
| Research synthesis | `L2_balanced` | Google free -> Codex | `L1_low_cost` -> `L3_heavy` | No |
| Coding/integration work | `L2_balanced` | Codex -> Google free | `L1_low_cost` -> `L3_heavy` | No |
| Architecture/high ambiguity | `L3_heavy` | Codex -> Anthropic credits | `L2_balanced` | Yes |
| External write actions | `L1_low_cost` | Google free | `L1_openrouter_free_fallback` -> `L2_balanced` | Yes |
| Quota spike preservation mode | `L1_openrouter_free_fallback` | OpenRouter free | `L1_low_cost` -> `L2_balanced` | No |

## Usage Modes

Configured under `routing.usage_modes`:

1. `strict_cost`: default to `L1`, auto-escalate only up to `L2`.
2. `balanced_default`: default day mode, `L3` only for explicit heavy cases.
3. `quality_push`: starts at `L2`, allows `L3` with approval.

## Cost Guardrails

1. Keep lane mix target near `L1 70% / L2 25% / L3 5%`.
2. Keep `block_auto_escalation_to_L3=true`.
3. Keep `max_auto_fallback_hops=2`.
4. Keep Anthropic on manual approval and low daily cap until spend telemetry stabilizes.

## Related Config

1. Agent-level overrides: [config/agents.yaml](/Users/palba/Projects/Clawdio/config/agents.yaml) (`routing_overrides`).
2. Environment keys: [.env.example](/Users/palba/Projects/Clawdio/.env.example).
3. Telemetry reporting: [docs/16-model-telemetry.md](/Users/palba/Projects/Clawdio/docs/16-model-telemetry.md).

## Quick Resolver CLI

Use [model_route_decider.py](/Users/palba/Projects/Clawdio/scripts/model_route_decider.py) to resolve lane/provider/fallback decisions from config:

```bash
python3 scripts/model_route_decider.py --situation coding_and_integration --json
python3 scripts/model_route_decider.py --mode strict_cost --intent-tag architecture
```
