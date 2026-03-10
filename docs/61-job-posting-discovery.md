# Job Posting Discovery

Last updated: 2026-03-10

## Purpose

Find public job postings automatically and feed the existing job-search inbox.

This worker is intentionally narrow:

1. search the public web for LinkedIn job URLs
2. fetch public posting text when possible
3. save normalized posting files into `data/job-search/inbox`
4. keep dedupe state and a status snapshot

It is not a LinkedIn session bot.

## Safety Boundary

1. no LinkedIn login
2. no browser session reuse
3. no form submission
4. no apply automation
5. public-web discovery only

## Files

1. Runtime: [job_posting_discovery.py](/Users/palba/Projects/Clawdio/scripts/job_posting_discovery.py)
2. Config: [job_search.yaml](/Users/palba/Projects/Clawdio/config/job_search.yaml)
3. Status snapshot: `data/job-search-discovery-status.json`
4. Dedupe state: `data/job-search-discovery-state.json`
5. Inbox target: `data/job-search/inbox`

## Provider Model

Discovery uses public search APIs, not LinkedIn APIs.

Current provider priority:

1. `brave_search_api`
2. `serpapi`

Both are optional. If neither is configured, discovery is skipped cleanly and the digest can still run against whatever is already in the inbox.

## Run

Manual discovery:

```bash
python3 scripts/job_posting_discovery.py \
  --env-file secrets/openclaw.env \
  --json
```

Offline deterministic fixture run:

```bash
python3 scripts/job_posting_discovery.py \
  --fixtures-file /path/to/discovery-fixtures.json \
  --json
```

## Output Contract

For each newly discovered posting:

1. write one normalized `.txt` file into `data/job-search/inbox`
2. record the URL and saved path in the discovery state file
3. expose saved count, duplicate count, and fetch errors in the status snapshot

If the posting body cannot be fetched, the worker can fall back to a snippet-only placeholder when enabled in config.

## Integration

The normal daily job-search digest now calls discovery first when `job_search.discovery.run_before_report=true`.

That means the existing:

```bash
python3 scripts/job_search_assistant.py publish-report --apply
```

can operate as:

1. discover public postings
2. save them into the inbox
3. triage and rank them
4. send the digest to Telegram

## Current Limits

1. limited to public pages found through search
2. best-effort fetch only; JS-heavy pages may degrade to snippet-only
3. LinkedIn result coverage depends on the configured search provider
