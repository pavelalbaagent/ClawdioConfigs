# Session Lifecycle Policy (Context Without Bloat)

Last updated: 2026-03-02

## Control File

Session behavior is defined in [config/session_policy.yaml](/Users/palba/Projects/Clawdio/config/session_policy.yaml).

## Core Rules

1. Keep one active coordinator session per main objective.
2. Summarize before context exceeds threshold.
3. Restart session when auth or tool-state changes make previous context unreliable.
4. Spawn sub-agents only for scoped specialist work and fold results back into compact summaries.

## When to Continue the Same Session

1. Same objective and same integration/tool state.
2. Recent context still relevant and under summarize threshold.
3. No unresolved error loop.

## When to Summarize

1. Before sub-agent spawn.
2. Before ending work block.
3. After major topic switch.
4. After repeated rate-limit errors.

## When to Restart/Clear

1. Integration auth changed.
2. Repeated tool failures (>3) on same flow.
3. Unresolved error loop.
4. Manual reset requested by you.

## Spawn Discipline

1. Require objective, allowed tools, lane, output schema, stop condition, and TTL.
2. Default TTL 45 minutes, max 180 minutes.
3. Max parallel sub-agents kept low to avoid cost fan-out.
4. Collapse all sub-agent output into compact handoff summary.

## Practical Daily Pattern

1. Morning: start one planning session and generate checkpoint.
2. During day: use focused task sessions; summarize at each milestone.
3. End of day: write one compact state checkpoint so next session can cold-start quickly.

## Project Space Rules

1. Ongoing projects should use separate project spaces.
2. A project space normally maps to a dedicated session thread, not a dedicated always-on agent.
3. Continue the same project session while objective, tool state, and milestone remain stable.
4. Start a new session in the same project space when:
   - milestone changes
   - toolchain/integration state changes materially
   - the existing session has been compacted enough that a fresh checkpoint is cheaper than replay
5. Spawn a dedicated agent from a project space only when the same specialist role is needed across repeated sessions or background loops.
