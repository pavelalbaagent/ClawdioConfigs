# Workout.xlsx Review and v4 Proposal

Last updated: 2026-03-05

## Source Reviewed

1. `/Users/palba/Downloads/Workout.xlsx`
2. Primary planning tab: `Currentv3`

## What is working already

1. Clear day-level structure with pair/triplet intent.
2. Good arm specialization consistency.
3. Practical use of your available equipment.
4. Default Wednesday/Sunday rest pattern is already aligned with your preference.

## Main bottlenecks found

1. Weekly volume imbalance:
   - Biceps: 24 sets
   - Back: 12 sets
   This can hurt pull progression and elbow recovery.
2. Thursday barbell day is overloaded (`Deadlift + BB Row + Squat + curls`), creating setup churn and systemic fatigue.
3. Rear-delt volume is relatively low versus front/side and arm work.
4. Leg work is present but can be disrupted if one busy day is missed.

## v4 changes proposed

1. Keep your exact style (pairs/triplets), but smooth fatigue and setup.
2. Keep 4 main workouts + optional 5th.
3. Use only one major lower barbell movement on Thursday (`Deadlift OR Squat`, alternating weekly).
4. Keep barbell/bench-heavy work concentrated on fewer days.
5. Raise back/rear-delt emphasis slightly, reduce excess arm fatigue.

## Suggested weekly set ranges

1. Biceps: 16-20
2. Back: 14-18
3. Chest: 12-16
4. Triceps: 12-16
5. Side delts: 8-12
6. Rear delts: 8-12
7. Legs: 8-12

## Historical artifact note

An original comparison workbook export was generated during this iteration with a new sheet:

1. Historical export name: `Workout_v4_proposed.xlsx`
2. Historical tab: `Proposed_v4`
3. Historical exports under `output/spreadsheet/` are no longer tracked as source-of-truth artifacts.
4. The current reference workbook is [Workout_plan_reference.xlsx](/Users/palba/Projects/Personal/Clawdio/fitness/reference/Workout_plan_reference.xlsx).

This tab includes:

1. Improved day templates preserving your exercise style.
2. Pair/triplet ordering for lower setup friction.
3. Weekly set target guidance.
4. Logging grammar for future fitness-agent integration.

## Next step to finalize

1. You send your preferred edits on the `Proposed_v4` tab (swap-in/swap-out exercises).
2. I convert that into final `fitness/PROGRAM.md` and lock your v1 12-week block + deload template.
