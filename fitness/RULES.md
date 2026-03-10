# Fitness Agent Rules

Last updated: 2026-03-10

## 1) Session Control

1. Only one active workout session at a time.
2. `start workout` opens a session row in SQLite.
3. `finish workout` closes session and writes a short markdown summary under `fitness/logs/`.

## 2) Missed Workout Policy

1. Queue is rolling: if a planned workout is missed, it is not dropped.
2. Next training day continues with the next pending queue item.
3. Default rest anchors are Wednesday and Sunday, but flexible overrides are allowed.

## 3) Progression Framework

1. Cycle shape:
   - Weeks 1-12: build phase.
   - Week 13: deload.
2. Compounds default to double progression.
3. Isolations default to rep progression and myorep density progression.
4. If load ceiling is reached, progress by reps, tempo, pause, rest reduction, or myorep density.

## 3.1) Arms-Specialization Volume Rules

1. Current trial target: `18` direct biceps sets per week.
2. Current trial target: `15` direct triceps sets per week, plus pressing carryover.
3. Keep exercise variety intentionally low during the trial block.
4. Prefer repeating the chosen arm anchors before adding new exercises.

## 4) Deload Triggers

1. Planned deload every 13th week.
2. Early deload candidate if 3 consecutive underperformance sessions occur.

## 5) Set Type Conventions

1. `straight`: normal set.
2. `myorep_activation`: initial activation set.
3. `myorep_mini`: mini-set in same cluster.
4. `warmup`: warm-up set (excluded from progression logic).

## 6) Superset Conventions

1. Use labels `A1/A2`, `B1/B2`, `C1/C2`.
2. Every programmed block is run as a superset.
3. Alternate the two block exercises instead of completing one exercise first.
4. Keep the same working load across both exercises in a block when practical.
5. Prioritize pairings that avoid load changes and repeated setup.

## 6.1) Myorep Matching Rules

1. Use myoreps mainly on isolation and low-skill movements.
2. Current trial myorep slots are:
   - `barbell_curl` / cheat-curl slot
   - `incline_dumbbell_curl`
   - `lateral_raise`
3. Do not use myoreps for heavy compounds (bench, row, floor press, deadlift).
4. Log activation and mini-sets explicitly in cluster format.
5. For this trial, each programmed myorep set is its own cluster.
6. Hammer curl and overhead triceps work stay as straight sets in this version.

## 6.2) Plate-Change Minimization Rules

1. Max 2-3 load blocks per session.
2. Keep only one heavy barbell block per non-bench day whenever possible.
3. Follow the programmed block order even if a DB block comes before a BB block.
4. Prefer pairings that can run with the same dumbbell bucket (`DB-H`, `DB-M`, `DB-L`).
5. Avoid introducing extra exercises that require unique one-off load setups.
6. Saturday is a fixed DB day, not an optional add-on.

## 7) Logging Grammar (Short Form)

1. Straight set:
   - `log <exercise> <reps> reps <weight>kg`
2. With explicit mode:
   - `log <exercise> <reps> reps <weight>kg each`
   - `log <exercise> <reps> reps <weight>kg pair`
   - `log <exercise> <reps> reps <weight>kg bb total`
   - `log <exercise> <reps> reps <weight>kg bb side`
3. Myoreps:
   - `log myoreps <exercise> <weight>kg each activation 18 then 5+4+4`
4. Superset:
   - `log superset A1 <exercise> ... and A2 <exercise> ...`

## 8) Load Interpretation

1. Dumbbell default = per dumbbell (`each`).
2. Barbell default = full system load (`bb total`).
3. If `bb side` is used, convert to total after barbell empty weight is known.
4. Keep raw input text for auditability when parser confidence is low.
