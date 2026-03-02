# Repos Salvage Report (2026-03-02)

## Scope reviewed

1. `pavelalbaagent/clawdio-backups`
2. `pavelalbaagent/YTIngest`
3. `pavelalbaagent/ClawdioConfigs` (empty target repo)

## 1) clawdio-backups: what to recover

### Keep and migrate

1. Model routing pattern:
2. Primary: `openai-codex/gpt-5.1-codex-mini`
3. Fallbacks: Google flash + Claude Sonnet
4. Operational controls:
5. `compaction.mode=safeguard`
6. agent concurrency caps (`maxConcurrent=4`, subagents `maxConcurrent=8`)
7. Gmail hook architecture:
8. webhook path `/hooks`
9. Gmail preset enabled with local listener + Tailscale funnel path
10. Reminder concepts from `REMINDERS.md`:
11. one-shot + daily reminders,
12. explicit reminder IDs,
13. backup retry path for delivery failures.
14. Model telemetry style from `model-usage-latest.md`:
15. lane share reporting,
16. top consumer analysis,
17. corrective action section.

### Do not copy as-is

1. Channel credentials and hook secrets in `openclaw.json`.
2. Open channel policies that are too permissive (`allowFrom: *` patterns).
3. WhatsApp-first operational dependency.

### Immediate security action

1. Rotate all credentials that have ever been committed to backup history:
2. Slack bot/app tokens.
3. Hook tokens and push tokens.
4. Any API keys present in prior configs.
5. Move all secrets to `/etc/openclaw/openclaw.env` on VPS (or equivalent secret store).

## 2) YTIngest: current status

1. Solid base exists for YouTube API ingest:
2. channel + playlist modes,
3. API key and OAuth support,
4. metadata enrichment,
5. local JSON snapshot storage.
6. Missing production features:
7. watchlist-driven ingest,
8. incremental sync,
9. dedupe canonical dataset,
10. structured run logs + failure classes,
11. scheduling and delivery integration.

## 3) ClawdioConfigs: target usage

1. Use as the canonical versioned home for this rebuild scaffolding.
2. Keep docs, config templates, wrappers, and runbooks here.
3. Exclude cloned external repos and runtime data from commits.

## Recovery summary

1. Strong operational patterns are recoverable from backups.
2. Secrets exposure risk is real and must be treated as already compromised.
3. YTIngest should be upgraded, not discarded.

