# YTIngest Improvement Plan (Hybrid with n8n)

## Decision

Use a hybrid model:

1. Keep ingestion logic in code (`YTIngest`) for reliability and version control.
2. Use n8n for orchestration, scheduling, fan-out, and notifications.

Reason:

1. OAuth + API quota/error handling is easier to test and maintain in code.
2. n8n is strong for trigger chains, approvals, and multi-destination delivery.
3. This split reduces model token usage by keeping deterministic transforms outside LLM calls.

## Proposed architecture

```text
n8n Cron/Webhook
   -> YTIngest CLI/API (deterministic fetch + normalize + dedupe)
      -> canonical data store (latest + history + run log)
         -> optional brief generator (LLM lane-aware)
            -> delivery adapters (Telegram/Gmail/Slack/dashboard)
```

## What to move into n8n

1. Scheduling (hourly/daily windows).
2. Retry policies and backoff orchestration.
3. Approval steps before posting or broadcasting.
4. Delivery routing to channels.
5. Incident alerts when ingest fails or quotas are exhausted.

## What should remain in YTIngest code

1. API access and OAuth token handling.
2. Incremental ingest logic (`since` watermark).
3. Deduplication by `videoId`.
4. Canonical schema generation.
5. Coverage metrics and failure classification.

## v1 implementation backlog (practical)

1. Add `watchlist.yaml` input.
2. Add `state.json` watermark per source.
3. Add canonical output file (`data/latest.json`) with dedup.
4. Add structured run report (`data/runs/<timestamp>.json`).
5. Add exit codes by class (`auth`, `quota`, `network`, `parse`).
6. Add optional `--dryRun`.
7. Add adapter output file for n8n ingestion.

## n8n workflow backlog

1. Workflow `yt_ingest_hourly`:
2. trigger -> execute YTIngest -> parse result -> branch success/failure.
3. Workflow `yt_brief_daily`:
4. consume canonical dataset -> optional LLM brief -> deliver digest.
5. Workflow `yt_quota_guard`:
6. detect quota failures -> downgrade frequency -> alert owner.

## Cost control hooks

1. Run YTIngest ingestion without LLM by default.
2. Only invoke LLM for summary/brief tasks.
3. Route summaries through low-cost lane unless confidence or complexity threshold is hit.

