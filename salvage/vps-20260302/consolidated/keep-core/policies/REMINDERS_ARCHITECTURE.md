# WhatsApp Reminder Architecture (499 window aware)

## Goals
- Keep every reminder inside WhatsApp so Pavel has a single trusted surface.
- Survive the 499 disconnect window by giving each reminder two chances to land (a lightweight system event plus a deep-lane, manual send that can reason/retry).  
- Keep the schedule discoverable via `REMINDERS.md` so “list”, “done”, and “defer” workflows always read a single source of truth.

## Flow per reminder
1. **Main cron job** – `clawdio-main` delivers a `systemEvent` to the `main` session at the requested time (`America/Guayaquil` by default). It simply states the reminder text + the local timestamp so the main WhatsApp session logs it in the conversation history.  
2. **Backup cron job** – runs at the same instant but targets an `isolated` session. It is powered by `openai-codex/gpt-5.3-codex` (`coding-deep`) so it can reason about HTTP 499’s, decide when a send failed, pause briefly, and retry. The backup job always uses the `message` tool to push the reminder text to `<PRIVATE_PHONE>`, waits ~20s if the first attempt hits a 499, and then reports the final outcome by replying in its session.  
3. **Logging** – once both jobs exist, we append a compact entry to the `## Current dynamic reminders log` section in `REMINDERS.md`. The entry records the local fire time, reminder message, and both job IDs (main + backup) so the log stays authoritative for “list/done/defer” commands.

## Scheduling recipe
Use the helper at `scripts/reminder_pair.py` (executable) to keep the pairing consistent:

```bash
python3 scripts/reminder_pair.py \
  --time 2026-03-02T19:10 \
  --message "Check the 499-window reminder flow" \
  --name reliability-check    # optional
```

- `--time` is interpreted in the `--tz` zone (`America/Guayaquil` by default) and sent as an `--at` ISO timestamp in UTC.  
- `--message` supplies the WhatsApp text. The same prose is echoed in the log and both jobs.  
- `--name` controls how the `reminder-YYYYMMDDTHHMM` slug is built; omit it to let the script use the timestamp alone.
- The helper creates the main system event and the `coding-deep` backup, then inserts one new bullet into `REMINDERS.md`.  

## Failure handling
- Backup sends begin with the same reminder text, explicitly target WhatsApp, and mention the 499 status so `coding-deep` can detect, wait 20 seconds, and retry once before replying.  
- Because both jobs delete themselves after running, the helper keeps the log entry fresh for the next “list”/“done”.  
- If the backup reports a failure in its session, scan that session log for the error before deciding whether to manually reissue the reminder; the helper can be rerun to create a new pair.

## Observability and housekeeping
- Read the `## Current dynamic reminders log` in `REMINDERS.md` to see what’s scheduled and what IDs you need to cancel.  
- Use `openclaw cron list --json` to inspect the job payloads if you need delivery details.  
- When a reminder fires, respond “done” (with the name if needed) to remove the remaining job(s) and archive the entry.

## Helper logic location
- `scripts/reminder_pair.py` packages the recipe: it parses the desired time, calls `openclaw cron add --json` for the main + backup jobs (with `coding-deep` for retries), and appends a bullet to `REMINDERS.md`.  
- The script is executable (`chmod +x`) and prints the newly created job IDs, so you can copy them straight into the log or follow-up commands.
