# Fitness Runtime

Last updated: 2026-03-09

## Goal

Make `fitness_coach` a real specialist runtime for workout selection, session control, and set logging without relying on freeform chat memory.

## Runtime

Main file:

1. [fitness_runtime.py](/Users/palba/Projects/Clawdio/scripts/fitness_runtime.py)

Core commands:

1. `workout today`
2. `start workout`
3. `log <exercise> <reps> reps <weight>kg <mode>`
4. `log myoreps <exercise> <weight>kg each activation 18 then 5+4+4`
5. `log superset A1 <exercise> ... and A2 <exercise> ...`
6. `finish workout`
7. `fitness status`
8. `set barbell empty <kg>kg`

## Storage

1. SQLite DB:
   - [contracts/fitness/sqlite_schema.sql](/Users/palba/Projects/Clawdio/contracts/fitness/sqlite_schema.sql)
   - default path: `.memory/fitness.db`
2. Runtime status snapshot:
   - `data/fitness-runtime-status.json`
3. Human-readable session logs:
   - `fitness/logs/*.md`

## Current behavior

1. Canonical program syncs from:
   - [PROGRAM.md](/Users/palba/Projects/Clawdio/fitness/PROGRAM.md)
   - [EXERCISE_LIBRARY.md](/Users/palba/Projects/Clawdio/fitness/EXERCISE_LIBRARY.md)
   - [RULES.md](/Users/palba/Projects/Clawdio/fitness/RULES.md)
2. Queue rolls forward through `M1` to `M4`.
3. `O5` is optional and can be started explicitly.
4. Dumbbells default to `each`.
5. Barbells default to `bb total`.
6. `bb side` requires cached empty barbell weight first.
7. Myoreps are stored as activation + mini-sets, not collapsed summaries.
8. Session finish writes a markdown summary and advances the next main-session pointer deterministically from completed history.

## Surfaces

Telegram:

1. `fitness: workout today`
2. `fitness: start workout`
3. `fitness: log bb curl 8 reps 20kg bb total`
4. Bare workout commands also work without the prefix.

Dashboard:

1. command box for fitness actions
2. buttons for `Today`, `Start`, `Finish`, `Status`
3. current plan view
4. active or last session summary
5. weekly volume and progression flags

## Non-goals for v1

1. no conversational coaching layer yet
2. no auto-progression writes back into the program
3. no reminder automation for workouts by default
4. no mobile-specific logging UI yet
