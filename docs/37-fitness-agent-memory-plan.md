# Fitness Agent Plan (5-Day Split + Deterministic Logging)

Last updated: 2026-03-06

## Goal

Create a dedicated `fitness_coach` agent that:

1. Knows your current program and weekly split.
2. Answers "what is my workout today" instantly.
3. Logs sets/reps/weight during workouts.
4. Correctly handles `myoreps` and `supersets`.
5. Uses low-token deterministic state first, model reasoning second.

## Why this memory pattern fits your use case

Use `hybrid_124` with a domain split:

1. Structured markdown (`1`): durable, human-editable training plan and rules.
2. Semantic embeddings (`2`): useful for qualitative recall (constraints, substitutions, recovery notes), not for raw numeric set logs.
3. SQLite structured state (`4`): best for exact schedule lookup, volume tracking, and progression checks.

This keeps costs low because the heavy repetition (daily schedule and set logging) stays deterministic in SQLite.

## Proposed source of truth hierarchy

1. `config/fitness_agent.yaml`:
   - execution policy, schedule assumptions, parser behavior, reminder hooks.
2. `fitness/PROGRAM.md`:
   - active split and exercise order.
3. `fitness/RULES.md`:
   - progression rules, myorep conventions, superset labeling rules.
4. `fitness/EXERCISE_LIBRARY.md`:
   - canonical names and substitution map.
5. `contracts/fitness/sqlite_schema.sql` + `.memory/fitness.db`:
   - deterministic operational state and logs.
6. `fitness/logs/*.md`:
   - session summaries for human review and semantic recall.

## Data model for myoreps and supersets

In `set_logs`:

1. `set_type` values:
   - `straight`
   - `myorep_activation`
   - `myorep_mini`
   - `warmup`
2. `myorep_cluster`:
   - compact representation, for example `"18|4|4|3"`.
3. `superset_label`:
   - standardized labels (`A1`, `A2`, `B1`, `B2`).

This lets the agent compute progression and weekly volume correctly without ambiguous parsing.

## Core runtime flows

1. Daily lookup flow:
   - Read last completed session from SQLite.
   - Resolve next training day index in rotating 5-day split.
   - Return planned exercises + target sets/reps.
2. Workout logging flow:
   - `start workout` -> open session row.
   - `log ...` -> parse + append set rows.
   - `finish workout` -> close session + write markdown summary.
3. Progression review flow (weekly):
   - compare performance against target ranges.
   - flag exercises for load increase, rep increase, or hold.

## Token-efficient guardrails

1. Deterministic-first parser for common commands.
2. Only call LLM when command is ambiguous.
3. No embedding generation for every numeric set line.
4. Summarize sessions into short markdown at end of workout.
5. Keep one active workout session at a time to avoid state drift.

## Suggested implementation phases

1. Phase 1: data and memory backbone
   - finalize `fitness` files and populate first program.
   - initialize `fitness.db` schema.
2. Phase 2: command parser + logger
   - support `today`, `start`, `log`, `finish` commands.
   - support explicit myorep and superset syntax.
3. Phase 3: reminders and dashboard
   - reminders for missed logging and next workout.
   - dashboard cards for today plan + weekly volume.
4. Phase 4: progression automation
   - deterministic rule engine for load/rep progression suggestions.

## Files added for this plan

1. [config/fitness_agent.yaml](/Users/palba/Projects/Personal/Clawdio/config/fitness_agent.yaml)
2. [contracts/fitness/sqlite_schema.sql](/Users/palba/Projects/Personal/Clawdio/contracts/fitness/sqlite_schema.sql)
3. [docs/38-fitness-intake-questionnaire.md](/Users/palba/Projects/Personal/Clawdio/docs/38-fitness-intake-questionnaire.md)

## Current locked decisions

1. The active queue is `M1`, `M2`, `M3`, `M4`, `O5` with Wednesday and Sunday as default rest anchors.
2. Bench setup is capped at 2 days per week.
3. The active program is maintained in [PROGRAM.md](/Users/palba/Projects/Personal/Clawdio/fitness/PROGRAM.md).
4. Command style remains short-form first (`today`, `start workout`, `log ...`, `finish workout`).
5. The remaining operational unknown is the empty barbell weight for clean `bb side` conversion.
