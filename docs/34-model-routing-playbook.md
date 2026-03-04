# Model Routing Playbook (Agent + Task + Fallback)

Last updated: 2026-03-03

## Why this exists

This playbook keeps routing deterministic and cheap by default, while preserving quality for hard tasks.

## Agent Defaults

Policy source: [config/agents.yaml](/Users/palba/Projects/Clawdio/config/agents.yaml) (`routing_overrides.agent_task_matrix`).

1. `coordinator`: `L1` for triage/planning, `L2` for ambiguity, `L3` for architecture decisions.
2. `researcher`: `L1` for collection, `L2` for synthesis, `L3` only for high-impact recommendations.
3. `builder`: `L1` for tiny patches, `L2` for normal builds, `L3` for major refactors.
4. `ops_guard`: `L0` for deterministic health checks, `L1` for summaries, `L2` for RCA.

## Situation-Based Routing

Policy source: [config/models.yaml](/Users/palba/Projects/Clawdio/config/models.yaml) (`routing.decision_matrix`).

1. Deterministic workflow tasks -> `L0_no_model`.
2. Quick transformations and short summaries -> `L1_low_cost`.
3. Research synthesis and coding work -> `L2_balanced`.
4. Architecture and high ambiguity -> `L3_heavy` with approval.
5. External write-like tasks (send/post/trigger) -> low lane plus approval gate.

## Provider Preference by Lane

1. `L1_low_cost`: Google free first.
2. `L1_openrouter_free_fallback`: OpenRouter free overflow.
3. `L2_balanced`: Google free then Codex supervised when quality needs increase.
4. `L3_heavy`: Codex supervised first, Anthropic credits second.

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

Switch mode by editing `routing_overrides.active_mode` in [config/agents.yaml](/Users/palba/Projects/Clawdio/config/agents.yaml):

1. `strict_cost`: for high-volume low-risk periods.
2. `balanced_default`: daily default.
3. `quality_push`: temporarily for key deliverables.

## Minimum Viable Routing for Now

If you want the simplest stable setup:

1. Keep `balanced_default`.
2. Use Google free + OpenRouter free for `L1`.
3. Use Codex subscription for `L2/L3` supervised tasks.
4. Enable Anthropic only when explicitly needed.
