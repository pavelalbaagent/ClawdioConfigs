# Reminder V2 Behavior Spec

## Goal

Replace reminder-history logs with a deterministic reminder workflow.

## Required behavior

1. User sends a reminder request with message and time.
2. System creates reminder, stores state, and confirms parsed time.
3. At due time, system sends reminder message.
4. If user replies `done`, reminder closes and no further reminders are sent.
5. If user replies `defer until <time>`, reminder is rescheduled to the new time.
6. If user does not reply, system sends one follow-up after 1 hour.
7. That follow-up is treated as a one-time 1-hour deferral, not a repeating loop.

## Command grammar

1. Create: `remind me <message> at <time>`
2. Create (relative): `remind me <message> in <duration>` (examples: `in 1 hour`, `in 30 minutes`)
3. Close: `done`
4. Reschedule: `defer until <time>`
5. Reply handling should work without reminder IDs when only one open reminder matches.

## State model

1. `pending`: reminder exists and waiting for due time.
2. `awaiting_reply`: reminder was sent and waiting for user response.
3. `done`: closed by user.
4. `cancelled`: closed by operator/system.

## Reminder record (minimum)

1. `id`
2. `message`
3. `timezone`
4. `remind_at`
5. `next_followup_at`
6. `status`
7. `created_at`
8. `updated_at`

## Operational rules

1. Time parsing must be explicit and confirmed back to user.
2. Auto follow-up interval is 60 minutes.
3. Max auto follow-ups is 1.
4. Any `done` or valid `defer until` response immediately cancels pending follow-up timers.
5. Every state transition should be logged for audit/debug.

## Implementation note

A deterministic state-machine helper is provided at:

1. [ops/scripts/reminder_state_machine.py](/Users/palba/Projects/Personal/Clawdio/ops/scripts/reminder_state_machine.py)
2. Scheduler adapter guard (enforces `systemEvent` for main-session due jobs):
3. [ops/scripts/reminder_scheduler_adapter.py](/Users/palba/Projects/Personal/Clawdio/ops/scripts/reminder_scheduler_adapter.py)

## Guard usage

1. Translate state-machine output into safe scheduler jobs:
2. `python3 ops/scripts/reminder_scheduler_adapter.py translate --input reminder-actions.json --session-target main`
3. Validate a planned job before `cron add`:
4. `python3 ops/scripts/reminder_scheduler_adapter.py validate-job --input reminder-job.json`
