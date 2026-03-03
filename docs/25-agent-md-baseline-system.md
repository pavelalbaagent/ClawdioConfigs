# Agent Markdown Baseline System

Last updated: 2026-03-02

## Goal

Start every agent workspace with the same strong, low-token continuity system.

## Canonical Files

1. `SOUL.md`: durable identity and behavioral contract.
2. `USER.md`: owner profile and stable preferences.
3. `MEMORY.md`: curated long-term memory.
4. `SESSION.md`: current objective, working context, and handoff.
5. `TODO.md`: personal and agent task queues.
6. `HEARTBEAT.md`: proactive periodic checks without spam.
7. `memory/YYYY-MM-DD.md`: short-lived daily logs.

## Source of Truth

1. Templates: [baselines/agent_md/](/Users/palba/Projects/Clawdio/baselines/agent_md)
2. Validation schema: [config/agent_md_baseline.yaml](/Users/palba/Projects/Clawdio/config/agent_md_baseline.yaml)
3. Bootstrap script: [scripts/bootstrap_agent_md.py](/Users/palba/Projects/Clawdio/scripts/bootstrap_agent_md.py)
4. Validation script: [scripts/validate_agent_md.py](/Users/palba/Projects/Clawdio/scripts/validate_agent_md.py)

## Lifecycle Rules

1. On first setup: bootstrap files into target workspace.
2. Every session start:
3. Read `SOUL.md`, `USER.md`, `SESSION.md`, `TODO.md`.
4. Read `MEMORY.md` only in direct/private main session.
5. During session:
6. Write decisions to `SESSION.md`.
7. Write actionable next steps to `TODO.md`.
8. End of session:
9. Compact `SESSION.md` into short handoff block.
10. Promote durable lessons to `MEMORY.md`.
11. Weekly:
12. Review `memory/` daily files and prune stale noise.
13. Keep `MEMORY.md` concise and current.

## Commands

1. Initialize workspace files:
2. `python3 scripts/bootstrap_agent_md.py --target /path/to/workspace`
3. Validate structure:
4. `python3 scripts/validate_agent_md.py --target /path/to/workspace`
5. Force refresh from latest templates:
6. `python3 scripts/bootstrap_agent_md.py --target /path/to/workspace --force`

## VPS Rollout Example

1. `python3 scripts/bootstrap_agent_md.py --target /home/pavel/.openclaw/workspace`
2. `python3 scripts/validate_agent_md.py --target /home/pavel/.openclaw/workspace`

## Security Notes

1. Keep secrets out of markdown files.
2. Keep personal-memory files private; do not load in group/public contexts.
3. Use file-based continuity, not implicit chat memory.
