# Google Calendar Runtime

Last updated: 2026-03-08

## Purpose

Make Google Calendar a real MVP runtime, not just a planning target.

This runtime now covers:

1. snapshot upcoming events from one canonical Google calendar
2. create events with explicit `--apply`
3. update events with explicit `--apply`
4. apply ready calendar candidates into Google Calendar
5. publish a dashboard-readable status snapshot
6. edit candidate schedule fields from the dashboard and promote candidates to `ready` or `approved`

## Files

1. Runtime script: [google_calendar_runtime.py](/Users/palba/Projects/Clawdio/scripts/google_calendar_runtime.py)
2. Candidate queue: `data/calendar-candidates.json`
3. Runtime status snapshot: `data/calendar-runtime-status.json`

## Safety Model

1. Default behavior is preview-only for write commands.
2. Real Google Calendar writes only happen when `--apply` is present.
3. Candidate application only acts on candidates with status:
   - `ready`
   - `approved`
4. Outlook stays out of the write path.

## Supported Candidate Fields

Timed event:

1. `title`
2. `status`
3. `start_at`
4. `end_at`
5. optional: `timezone`, `description`, `location`, `attendees`, `event_id`

All-day event:

1. `title`
2. `status`
3. `start_date`
4. optional: `end_date`

Notes:

1. If `event_id` exists, candidate application updates that event.
2. If `event_id` is absent, candidate application creates a new event.
3. Gmail-promoted candidates usually still need scheduling details before they are ready to apply.

## Commands

Refresh upcoming events snapshot:

```bash
python3 scripts/google_calendar_runtime.py --env-file secrets/openclaw.env snapshot --json
```

Preview creating an event:

```bash
python3 scripts/google_calendar_runtime.py --env-file secrets/openclaw.env create \
  --title "Parent teacher meeting" \
  --start-at "2026-03-10T18:00:00-05:00" \
  --end-at "2026-03-10T18:30:00-05:00" \
  --json
```

Apply creating an event:

```bash
python3 scripts/google_calendar_runtime.py --env-file secrets/openclaw.env create \
  --title "Parent teacher meeting" \
  --start-at "2026-03-10T18:00:00-05:00" \
  --end-at "2026-03-10T18:30:00-05:00" \
  --apply --json
```

Apply ready candidates:

```bash
python3 scripts/google_calendar_runtime.py --env-file secrets/openclaw.env apply-candidates --apply --json
```

## Dashboard Surface

The dashboard now reads the status snapshot and exposes:

1. last calendar action
2. dry-run vs applied mode
3. create/update/skip/error counts
4. pending candidate count
5. upcoming events table
6. candidate editing and approval helpers in the `Calendar Candidates` table
7. direct `Apply Approved Candidates` action from the Google Calendar card

## Current Limits

1. Approval is still operator-driven around candidate state and command invocation, not a separate calendar-specific workflow.
2. Candidate editing currently uses prompt-based dashboard inputs, not a richer form.
3. Outlook mirroring is still out of scope for MVP.

## Next Gate

1. Replace the prompt-based candidate editor with a structured dashboard form.
2. Optionally add a timer/unit to refresh calendar snapshots automatically on the VPS.
