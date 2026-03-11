# Fitness Canonical Layout

## Purpose

Define which fitness files are canonical, which are reference-only, and which are historical planning artifacts.

## Canonical Files

1. [PROGRAM.md](/Users/palba/Projects/Personal/Clawdio/fitness/PROGRAM.md)
2. [RULES.md](/Users/palba/Projects/Personal/Clawdio/fitness/RULES.md)
3. [ATHLETE_PROFILE.md](/Users/palba/Projects/Personal/Clawdio/fitness/ATHLETE_PROFILE.md)
4. [EXERCISE_LIBRARY.md](/Users/palba/Projects/Personal/Clawdio/fitness/EXERCISE_LIBRARY.md)
5. [SESSION_QUEUE.md](/Users/palba/Projects/Personal/Clawdio/fitness/SESSION_QUEUE.md)
6. [fitness/README.md](/Users/palba/Projects/Personal/Clawdio/fitness/README.md)

## Reference Workbook

1. Keep one readable workbook reference:
   - [Workout_plan_reference.xlsx](/Users/palba/Projects/Personal/Clawdio/fitness/reference/Workout_plan_reference.xlsx)
2. This workbook is reference-only.
3. The markdown files in `fitness/` remain the source of truth.

## Generated Or Historical Files

1. `fitness/logs/` contains generated session summaries.
2. `output/spreadsheet/` is treated as export/history space.
3. Prior workout-planning docs were moved to:
   - `docs/archive/fitness-planning/`

## Cleanup Rule

1. Update the canonical markdown files when the program changes.
2. Do not create new `v4/v5/v6/...` workbook chains in the main repo flow.
3. If a new workbook is useful, replace the single reference workbook instead of creating a new sprawl of variants.
