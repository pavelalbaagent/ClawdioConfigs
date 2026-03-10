# Job Search Assistant

Last updated: 2026-03-09

## Purpose

Provide a manual-review-first job-search lane for saved LinkedIn or public job postings.

This module is for:

1. generating reusable search guidance
2. triaging one saved posting at a time
3. producing a daily ranked summary of saved postings

This module is not for:

1. logging into LinkedIn
2. auto-applying
3. automating browser sessions or form submission

## Files

1. Runtime script: [job_search_assistant.py](/Users/palba/Projects/Clawdio/scripts/job_search_assistant.py)
2. Module config: [job_search.yaml](/Users/palba/Projects/Clawdio/config/job_search.yaml)
3. Latest daily status snapshot: `data/job-search-daily-summary.json`
4. ResearchFlow orchestrator: [research_flow_runtime.py](/Users/palba/Projects/Clawdio/scripts/research_flow_runtime.py)
5. VPS report service: [openclaw-job-search-report.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-job-search-report.service)
6. VPS report timer: [openclaw-job-search-report.timer](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-job-search-report.timer)

## Safety Model

1. Keep LinkedIn in manual-review-only mode.
2. Use copied text, saved text files, or public URL fetches only when the page is accessible without login.
3. Treat `remote` alone as insufficient evidence for Ecuador eligibility.
4. Surface recommendations for operator review; do not submit applications automatically.

## Commands

Generate reusable search guidance:

```bash
python3 scripts/job_search_assistant.py generate-search-pack \
  --output output/jobs/search_pack.md
```

Triage one saved posting:

```bash
python3 scripts/job_search_assistant.py triage \
  --input-file /path/to/posting.txt
```

Triage pasted text:

```bash
pbpaste | python3 scripts/job_search_assistant.py triage --stdin
```

Generate the daily ranked summary from a folder of saved postings:

```bash
python3 scripts/job_search_assistant.py daily-summary \
  --input-dir /path/to/linkedin_saved_postings \
  --day-label 2026-03-09
```

Preview the daily digest that would be sent to Telegram:

```bash
python3 scripts/job_search_assistant.py publish-report
```

Send the digest to the configured Telegram chat:

```bash
python3 scripts/job_search_assistant.py publish-report \
  --env-file secrets/openclaw.env \
  --apply
```

Run it through the researcher-owned ResearchFlow wrapper:

```bash
python3 scripts/research_flow_runtime.py \
  --env-file secrets/openclaw.env \
  run --workflow job_search_digest --apply --json
```

## Outputs

Single-posting triage writes:

1. `output/jobs/triage/*.json`
2. `output/jobs/triage/*.md`

Daily summary writes:

1. `output/jobs/daily/<day>.json`
2. `output/jobs/daily/<day>.md`
3. `data/job-search-daily-summary.json`

## Recurrence Contract

Default contract in config:

1. input inbox: `data/job-search/inbox`
2. schedule: every day at `18:30` in `America/Guayaquil`
3. empty-day behavior: still produce and send a report
4. delivery channel: Telegram private operator chat

Live default:

1. deliver to the `researcher` surface via `TELEGRAM_RESEARCH_CHAT_ID`
2. do not send the scheduled digest to the assistant main chat
3. the VPS timer now calls the ResearchFlow wrapper, not the raw script directly

## Report Presentation

Telegram digest shape:

1. one-line counts header
2. `Apply Today`
3. `Manual Checks Before Applying`
4. `Stretch Roles`
5. optional file paths to the full markdown and JSON reports

Full detail stays in the file artifacts. Telegram is the concise operator digest, not the only record.

## Daily Summary Rules

The summary is ranked by:

1. recommendation priority: `apply`, `manual_review`, `stretch_apply`, `pass`
2. eligibility strength
3. fit score

The output groups postings into:

1. `apply`
2. `manual_review`
3. `stretch_apply`
4. `pass`

## Current Limits

1. This is still a saved-posting workflow, not a live LinkedIn browser runtime.
2. URL fetching is best effort only and will be unreliable on JS-heavy job pages.
3. Resume tailoring and application queue state are not included yet.

## Next Gate

1. Decide whether the Telegram digest is enough or whether the dashboard should also expose the latest job-search summary.
2. Add a small application-queue state layer only if daily manual use justifies it.
