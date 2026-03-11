# ResearchFlow Orchestration

Last updated: 2026-03-10

## Goal

Give the `researcher` surface one owned automation layer for:

1. daily job-search digests
2. daily AI-tools research digests sourced from `AIToolsDB`

This avoids treating those as unrelated timers. The researcher now has one orchestration runtime, one config file, one status snapshot, and one dashboard surface.

## Core Files

1. Config: [research_flow.yaml](/Users/palba/Projects/Personal/Clawdio/config/research_flow.yaml)
2. Runtime: [research_flow_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/research_flow_runtime.py)
3. Dashboard state: `data/research-flow-status.json`
4. Shared latest-record dropzones:
   - `data/researchflow/inbox`
   - `data/researchflow/notes`
5. Wrapped workflows:
   - [job_search_assistant.py](/Users/palba/Projects/Personal/Clawdio/scripts/job_search_assistant.py)
   - [ai_tools_digest.py](/Users/palba/Projects/Personal/Clawdio/scripts/ai_tools_digest.py)

## Ownership

1. owner agent: `researcher`
2. default space: `research`
3. delivery chat env: `TELEGRAM_RESEARCH_CHAT_ID`

The main assistant does not own this automation lane. It can report status, but the workflow itself belongs to the researcher surface.

## Current Workflows

### Job Search Digest

1. wraps `publish-report` from the job-search assistant
2. can run public job-posting discovery first when enabled in the job-search config
3. uses the saved-postings inbox and manual-review-first ranking logic
4. default delivery time: `18:30` `America/Guayaquil`

### AI Tools Watch

1. wraps the deterministic `AIToolsDB` digest
2. scans the local corpus for recent changes
3. default delivery time: `20:00` `America/Guayaquil`

## Runtime Commands

Status only:

```bash
python3 scripts/research_flow_runtime.py \
  --env-file secrets/openclaw.env \
  status --json
```

Run one workflow:

```bash
python3 scripts/research_flow_runtime.py \
  --env-file secrets/openclaw.env \
  run --workflow job_search_digest --apply --json
```

Run both:

```bash
python3 scripts/research_flow_runtime.py \
  --env-file secrets/openclaw.env \
  run --workflow all --apply --json
```

Research Telegram surface:

1. `research flow status`
2. `run job search digest`
3. `run tech digest`
4. `run both digests`

## VPS Contract

The systemd timers remain separate, but both now call the same ResearchFlow wrapper:

1. [openclaw-job-search-report.service](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-job-search-report.service)
2. [openclaw-ai-tools-digest.service](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-ai-tools-digest.service)

That keeps schedules independent while preserving one orchestration contract and one dashboard view.

## Dashboard Behavior

The dashboard should show:

1. owner agent and default space
2. last orchestrated run
3. workflow schedule and last output
4. manual trigger buttons for:
   - job search digest
   - AI tools digest
   - both

## Artifact Contract

Each workflow should leave behind reusable files, not only Telegram text.

Current contract:

1. Job search digest writes `output/jobs/daily/<day>.json` and `.md`
2. AI tools digest writes `output/research/ai_tools_digest/<day>.json` and `.md`
3. ResearchFlow writes stable latest-record pointers per workflow into each shared dropzone, for example:
   - `data/researchflow/inbox/job_search_digest-latest.json`
   - `data/researchflow/inbox/ai_tools_watch-latest.json`

## Design Rule

ResearchFlow is an orchestration layer, not a second researcher personality.

It should:

1. wrap bounded scheduled workflows
2. write status snapshots
3. deliver to the researcher surface

It should not:

1. spawn new runtime agents
2. invent new state stores for job search or AIToolsDB
3. bypass the underlying workflow scripts
