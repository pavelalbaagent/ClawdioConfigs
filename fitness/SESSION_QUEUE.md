# Session Queue State

Last updated: 2026-03-10

## Canonical Queue

1. `M1_mon_bench_1`
2. `M2_tue_db`
3. `M3_thu_db_bb`
4. `M4_fri_bench_2`
5. `M5_sat_db`

## Current Pointer

1. `current_next_session: M1_mon_bench_1`

## Scheduling Rules

1. Default weekly anchor:
   - Mon: `M1`
   - Tue: `M2`
   - Wed: Rest
   - Thu: `M3`
   - Fri: `M4`
   - Sat: `M5`
   - Sun: Rest
2. If a training day is missed, carry the session forward.
3. Do not auto-skip `M1-M5`.
