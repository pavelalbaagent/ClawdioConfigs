# AI Tools Knowledge Source

Last updated: 2026-03-10

## Goal

Use the local AI-tools corpus as a read-only knowledge source for `assistant`, `researcher`, and `builder`.

The source id remains `ai_tools_db` for compatibility, but the canonical local corpus now lives in `KnowledgeCorpus`.

This is not a second memory system. It is a bounded local retrieval source for AI-tools and model ecosystem questions.

## Why this shape

1. The corpus already exists and has useful material.
2. It is better to read from it than to rebuild another ingestion pipeline first.
3. Keeping it read-only avoids polluting the main OpenClaw state model.

## Current config

1. [knowledge_sources.yaml](/Users/palba/Projects/Personal/Clawdio/config/knowledge_sources.yaml)

Default source:

1. `ai_tools_db`
2. root candidates:
   - `/opt/clawdio/external/KnowledgeCorpus/data/raw`
   - `/opt/clawdio/external/AIToolsDB/corpus/ai_tools` (legacy fallback)
   - `/opt/knowledgecorpus/data/raw`
   - `/opt/aitoolsdb/corpus/ai_tools` (legacy fallback)
   - `../../KnowledgeCorpus/data/raw` (local dev path relative to `config/knowledge_sources.yaml`)

## Current runtime

1. Search helper: [knowledge_source_search.py](/Users/palba/Projects/Personal/Clawdio/scripts/knowledge_source_search.py)
2. Daily digest: [ai_tools_digest.py](/Users/palba/Projects/Personal/Clawdio/scripts/ai_tools_digest.py)
3. ResearchFlow orchestrator: [research_flow_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/research_flow_runtime.py)

## Agent usage

Current policy:

1. `researcher` may auto-query this source for relevant requests
2. `assistant` may query it when the message clearly concerns AI tools, models, or workflows
3. `builder` may query it for coding-assistant/tooling questions

It is intentionally not used for:

1. reminders
2. calendar actions
3. fitness logging
4. generic personal task handling

## Search usage

Preview local results:

```bash
python3 scripts/knowledge_source_search.py --query "GPT-5.3 Codex" --agent-id researcher --space-key research --json
```

## Daily digest

The digest is deterministic and based on recently modified corpus files.

Outputs now include:

1. `output/research/ai_tools_digest/<day>.json`
2. `output/research/ai_tools_digest/<day>.md`
3. `data/ai-tools-digest-status.json`

Preview:

```bash
python3 scripts/ai_tools_digest.py --env-file /etc/openclaw/openclaw.env --json
```

Deliver to the research chat:

```bash
python3 scripts/ai_tools_digest.py --env-file /etc/openclaw/openclaw.env --apply --json
```

Deliver through the researcher-owned ResearchFlow wrapper:

```bash
python3 scripts/research_flow_runtime.py \
  --env-file /etc/openclaw/openclaw.env \
  run --workflow ai_tools_watch --apply --json
```

Research Telegram surface:

1. `run tech digest`
2. `research flow status`

Systemd units:

1. [openclaw-ai-tools-digest.service](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-ai-tools-digest.service)
2. [openclaw-ai-tools-digest.timer](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-ai-tools-digest.timer)

## Deployment note

Preferred VPS sync target:

1. `/opt/clawdio/external/AIToolsDB/corpus/ai_tools`

Canonical target going forward:

1. `/opt/clawdio/external/KnowledgeCorpus/data/raw`

The legacy `AIToolsDB` path is still listed as a fallback so the runtime does not break during deployment cleanup.
