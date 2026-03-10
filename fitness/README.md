# Fitness Canon

## Canonical Files

1. [PROGRAM.md](/Users/palba/Projects/Clawdio/fitness/PROGRAM.md)
2. [RULES.md](/Users/palba/Projects/Clawdio/fitness/RULES.md)
3. [ATHLETE_PROFILE.md](/Users/palba/Projects/Clawdio/fitness/ATHLETE_PROFILE.md)
4. [EXERCISE_LIBRARY.md](/Users/palba/Projects/Clawdio/fitness/EXERCISE_LIBRARY.md)
5. [SESSION_QUEUE.md](/Users/palba/Projects/Clawdio/fitness/SESSION_QUEUE.md)

## Reference Workbook

1. Keep exactly one readable workbook reference:
   - [Workout_plan_reference.xlsx](/Users/palba/Projects/Clawdio/fitness/reference/Workout_plan_reference.xlsx)

## Non-Canonical Output

1. `output/spreadsheet/` is treated as export/history space, not source of truth.
2. `fitness/logs/` contains generated session summaries, not program definition files.

## Read-Only Grounding

1. `fitness/knowledge/` is a conversational grounding corpus for `fitness_coach`.
2. It is advisory context only and must not override deterministic workout control.
3. If coaching guidance changes, update the canonical files in `fitness/` when the program itself changes.
