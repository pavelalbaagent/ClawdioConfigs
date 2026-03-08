# Gmail Inbox Processing Plan

Last updated: 2026-03-07

## Goal

Make the agent's Gmail inbox a real operational inbox that can process every incoming message in scheduled batches.

## Recommended model

1. Use a dedicated Gmail account owned by the agent.
2. Process mail on a schedule, not continuously one-message-at-a-time.
3. Store message metadata and short excerpts in SQLite first.
4. Escalate to model use only when classification or action choice is ambiguous.

## Why this is better than ad-hoc message handling

1. Predictable cost
2. Easier auditing
3. Safer automation boundaries
4. Easier future promotion into tasks, calendar items, or Drive artifacts

## Processing loop

1. Pull unread or unprocessed inbox messages every 15 minutes.
2. Classify each message by sender type and intent.
3. Store metadata in SQLite.
4. Choose one action:
   - archive
   - trash
   - keep in inbox
   - draft reply
   - task candidate
   - calendar candidate
   - manual review
5. Log the decision and resulting state.

## Scope choice

The Gmail integration now assumes `gmail.modify` rather than read-only plus send.

Why:

1. `gmail.modify` supports read and mailbox changes without requiring permanent delete scope.
2. Scheduled triage needs archive/label/trash behavior, not just reading.

Official source:

1. [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)

## Guardrails

1. Never send without approval.
2. Never permanently delete.
3. Prefer archive over trash by default.
4. Require manual review for unknown senders with links or attachments.

## Contract source

1. [contracts/gmail/inbox-processing-rules.yaml](/Users/palba/Projects/Clawdio/contracts/gmail/inbox-processing-rules.yaml)

## Current runtime

The current runtime exists and is intentionally deterministic-first:

1. [scripts/gmail_inbox_processor.py](/Users/palba/Projects/Clawdio/scripts/gmail_inbox_processor.py)
2. [contracts/gmail/sqlite_schema.sql](/Users/palba/Projects/Clawdio/contracts/gmail/sqlite_schema.sql)

Behavior:

1. fetches inbox message refs
2. skips already-processed messages by SQLite state unless `--reprocess` is used
3. classifies messages with deterministic heuristics
4. stores metadata, excerpts, attachments metadata, and decisions in SQLite
5. applies only safe primary actions when `--apply` is explicitly passed

## Run commands

Dry-run against the live Gmail account:

```bash
python3 scripts/gmail_inbox_processor.py --env-file /etc/openclaw/openclaw.env
```

Dry-run JSON output:

```bash
python3 scripts/gmail_inbox_processor.py --env-file /etc/openclaw/openclaw.env --json
```

Apply safe mailbox actions:

```bash
python3 scripts/gmail_inbox_processor.py --env-file /etc/openclaw/openclaw.env --apply
```

Apply actions and promote candidates into the local operator queues:

```bash
python3 scripts/gmail_inbox_processor.py --env-file /etc/openclaw/openclaw.env --apply --promote-task-candidates --promote-calendar-candidates
```

Optional deterministic placeholder drafts for reply candidates:

```bash
python3 scripts/gmail_inbox_processor.py --env-file /etc/openclaw/openclaw.env --apply --create-placeholder-drafts
```

SQLite state location defaults to:

1. `.memory/inbox_processing.db` relative to the repo root, unless overridden with `--state-db`

## Current limits

1. No model-based classification path yet.
2. Task promotion is local dashboard-workspace promotion, not remote Todoist/Asana write-through yet.
3. Calendar promotion is local candidate-queue promotion, not remote Google Calendar write-through yet.
4. Attachment handling is metadata-first for now.

## VPS timer

User-mode systemd templates now exist for scheduled batch runs:

1. [openclaw-gmail-processor.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-gmail-processor.service)
2. [openclaw-gmail-processor.timer](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-gmail-processor.timer)
