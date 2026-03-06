# Fitness Agent Rules

Last updated: 2026-03-05

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

1. Biceps target range: 20-24 hard sets per week.
2. Triceps target range: 18-22 hard sets per week.
3. Keep exercise variety intentionally low during the 12-week block.
4. Prefer adding sets/reps on core arm anchors before adding new exercises.

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
2. Prefer antagonistic pairings when possible.
3. Prioritize pairings that avoid load changes and repeated setup.
4. Keep heavy antagonist pairs first (for example bench/row, close-grip press/curl).
5. Use myorep antagonist pairs later in the session for density work.

## 6.1) Myorep Matching Rules

1. Use myoreps mainly on isolation and low-skill movements.
2. Do not use myoreps for heavy compounds (bench, row, squat, deadlift).
3. Log activation and mini-sets explicitly in cluster format.
4. For matched myorep supersets, keep the same dumbbell load when practical to reduce setup churn.
5. Default arm myorep pair for O5: biceps (`hammer_curl`) + triceps (`kickbacks`).
6. Optional second arm myorep pair for O5: biceps (`incline_dumbbell_curl`) + triceps (`overhead_dumbbell_triceps_extension`) when elbows tolerate.

## 6.2) Plate-Change Minimization Rules

1. Max 2-3 load blocks per session.
2. Keep only one heavy barbell block per non-bench day whenever possible.
3. On bench days, complete all barbell work before switching to dumbbells, or keep full DB-only sessions.
4. Prefer pairings that can run with the same dumbbell bucket (`DB-H`, `DB-M`, `DB-L`).
5. Avoid introducing extra exercises that require unique one-off load setups.
6. Saturday optional session must remain no-bench (DB/bodyweight only).

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
