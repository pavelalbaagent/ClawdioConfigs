# Reminder Failure Analysis (Why Digests Worked but Ad-Hoc Reminders Failed)

Last updated: 2026-03-03

## Question

Why did scheduled WhatsApp reports/digests work while one-shot reminders like "remind me in 1 hour" often failed?

## Findings from salvaged runtime data

1. **Grammar mismatch on relative time input**
2. The reminder parser only accepted `remind me <message> at <time>` and did not accept `in <duration>`.
3. Example reproduction from local deterministic helper:
4. `create-from-text "remind me pay bill in 1 hour"` returned `invalid_create_text`.

5. **One-shot job payload mismatch (main-session reminder skipped)**
6. In recovered cron runs, job `reminder-1805` was skipped with:
7. `main job requires payload.kind="systemEvent"`
8. That means the reminder was created as an `agentTurn` for `sessionTarget=main`, but the scheduler expected a `systemEvent` payload for this path.

9. **Backup reminder path depended on a capability blocked by policy**
10. In the corresponding backup run (`c4a653d4-...`), the summary reported:
11. it could not message external contacts directly and asked for manual sending.
12. So the main reminder path was skipped, and backup path did not actually deliver the WhatsApp message.

13. **Digest/report jobs used a more stable path**
14. Digest/report jobs were recurring cron jobs with tested delivery configuration and had successful run history (`status=ok`) in cron run logs.
15. These jobs did not rely on fragile ad-hoc NL parsing + dynamic one-shot payload conversion.

## Root-cause summary

1. Ad-hoc reminder flow had more moving parts than digest flow.
2. The failures were not from one single bug; they were a stack:
3. relative-time parse gap,
4. wrong payload kind for main-session one-shot reminders,
5. backup path relying on a delivery action not permitted in policy.

## Hardening changes now in this repo

1. Reminder state machine now supports relative create commands:
2. `remind me <message> in <duration>` (for example `in 1 hour`, `in 30 minutes`).
3. Invalid time inputs now return structured `invalid_time` errors instead of tracebacks.
4. Tests added for relative create and invalid-time error handling.
5. Added scheduler adapter guard:
6. [ops/scripts/reminder_scheduler_adapter.py](/Users/palba/Projects/Clawdio/ops/scripts/reminder_scheduler_adapter.py)
7. Main-session due jobs are rejected if payload kind is not `systemEvent`.

## Prevention checklist for the new architecture

1. Keep one canonical reminder path (deterministic state machine + orchestrator).
2. Normalize one-shot reminders to explicit UTC timestamps before scheduling.
3. For main-session due events, enforce `payload.kind=systemEvent`.
4. Avoid backup paths that require tools blocked by policy, or explicitly allow that capability.
5. Add a daily health check: list open reminders + verify each has a valid due/follow-up schedule.
