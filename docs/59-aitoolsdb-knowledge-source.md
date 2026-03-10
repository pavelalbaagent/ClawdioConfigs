# AIToolsDB Knowledge Source

Last updated: 2026-03-09

## Goal

Use the local `AIToolsDB` corpus as a read-only knowledge source for `assistant`, `researcher`, and `builder`.

This is not a second memory system. It is a bounded local retrieval source for AI-tools and model ecosystem questions.

## Why this shape

1. The corpus already exists and has useful material.
2. It is better to read from it than to rebuild another ingestion pipeline first.
3. Keeping it read-only avoids polluting the main OpenClaw state model.

## Current config

1. [knowledge_sources.yaml](/Users/palba/Projects/Clawdio/config/knowledge_sources.yaml)

Default source:

1. `ai_tools_db`
2. root candidates:
   - `/opt/clawdio/external/AIToolsDB/corpus/ai_tools`
   - `/opt/aitoolsdb/corpus/ai_tools`
   - `/Users/palba/Projects/AIToolsDB/corpus/ai_tools`

## Current runtime

1. Search helper: [knowledge_source_search.py](/Users/palba/Projects/Clawdio/scripts/knowledge_source_search.py)
2. Daily digest: [ai_tools_digest.py](/Users/palba/Projects/Clawdio/scripts/ai_tools_digest.py)

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

Preview:

```bash
python3 scripts/ai_tools_digest.py --env-file /etc/openclaw/openclaw.env --json
```

Deliver to the research chat:

```bash
python3 scripts/ai_tools_digest.py --env-file /etc/openclaw/openclaw.env --apply --json
```

Systemd units:

1. [openclaw-ai-tools-digest.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-ai-tools-digest.service)
2. [openclaw-ai-tools-digest.timer](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-ai-tools-digest.timer)

## Deployment note

To use this on the VPS, sync the corpus to:

1. `/opt/clawdio/external/AIToolsDB/corpus/ai_tools`

That keeps the OpenClaw app repo separate from the larger research corpus while still allowing local retrieval.
