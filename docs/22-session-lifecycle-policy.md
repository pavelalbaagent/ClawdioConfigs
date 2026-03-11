# Session Lifecycle Policy (Context Without Bloat)

Last updated: 2026-03-02

## Control File

Session behavior is defined in [config/session_policy.yaml](/Users/palba/Projects/Personal/Clawdio/config/session_policy.yaml).

## Core Rules

1. Keep one active session per main objective and space.
2. Summarize before context exceeds threshold.
3. Restart session when auth or tool-state changes make previous context unreliable.
4. Do not spawn sub-agents in the live runtime; route to existing agent surfaces and fold results into compact summaries.
5. Treat channels as transport only; context should come from the selected space plus compact summaries.

## When to Continue the Same Session

1. Same objective and same integration/tool state.
2. Recent context still relevant and under summarize threshold.
3. No unresolved error loop.

## When to Summarize

1. Before major handoff or session end.
2. Before ending work block.
3. After major topic switch.
4. After repeated rate-limit errors.

## When to Restart/Clear

1. Integration auth changed.
2. Repeated tool failures (>3) on same flow.
3. Unresolved error loop.
4. Manual reset requested by you.

## Agent Discipline

1. Keep the runtime agent set fixed.
2. Route work into existing agent surfaces or project spaces.
3. Collapse multi-step work into compact handoff summaries instead of creating hidden workers.

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
5. Reuse the existing specialist surfaces from a project space instead of spawning new agents.

## Agent/Space defaults

1. `assistant` -> `general`
2. `researcher` -> `research`
3. `fitness_coach` -> `fitness`
4. `builder` -> `coding`
5. `ops_guard` -> `ops`

Project work should usually stay in `project:<slug>` spaces, regardless of which agent is active.

## Continuous-improvement loop

The system should improve through reviews, not through uncontrolled self-rewrite:

1. daily ops review
2. weekly architecture/process review
3. summaries and change proposals written as outputs
4. approval required for structural changes
