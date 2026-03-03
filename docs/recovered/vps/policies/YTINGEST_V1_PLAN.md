# YTINGEST_V1_PLAN.md

## 1) Project Definition (must be explicit)
- **Project name:** YTIngest v1
- **Why this exists (problem):** We need a reliable way to turn YouTube channels/playlists into structured, reusable intelligence instead of ad-hoc watching.
- **Who it serves:** Pavel + collaborators in Anbu-Logic-Labs.
- **Success metric (1-3 max):**
  1. 95%+ successful ingest runs for target playlists/channels.
  2. Weekly insight output generated in <5 minutes from latest ingested data.
  3. Zero secrets committed to git.
- **Out of scope (hard no):** Video downloading, copyright-sensitive media extraction, full transcript scraping pipeline in v1.

## 2) Job Specs (no vague assistants)

### Job A — Playlist/Channel Ingest
- **Trigger:** Manual CLI (v1), cron in v1.1
- **Inputs:** `playlistId` or `channelId`, `maxItems`
- **Output contract:** JSON snapshot with normalized metadata + run stats
- **Owner:** Pavel (operator), Clawdio (implementation)
- **Failure behavior:** Exit non-zero, print actionable error, keep prior snapshots untouched
- **Stop condition:** API response complete or page token exhausted/max items reached

### Job B — Normalize + Deduplicate
- **Trigger:** Post-ingest step
- **Inputs:** Raw ingest snapshot
- **Output contract:** Deterministic normalized dataset keyed by `videoId`
- **Owner:** Clawdio
- **Failure behavior:** Log malformed records, continue processing valid records
- **Stop condition:** All candidate records processed

### Job C — Insight Extractor
- **Trigger:** Manual command (v1), scheduled in v1.1
- **Inputs:** Latest normalized dataset
- **Output contract:** Markdown brief with top videos, recurring themes, and actionable takeaways
- **Owner:** Pavel + Clawdio
- **Failure behavior:** Return partial summary with explicit missing sections
- **Stop condition:** Report file generated

## 3) Model Routing Plan
- **Quick lane:** `quick-primary` (`gpt-5.1-codex-mini`) for routine extraction/format transforms
- **Default lane:** `default-primary` (`gpt-5.2`) for normal analysis and summaries
- **Deep lane:** `coding-deep` (`gpt-5.3-codex`) for code refactors and complex reasoning
- **Design lane:** Claude only for complex architecture planning
- **Failover order:** `gpt-5.1-codex-mini` → `gpt-5.3-codex` (no infinite loops)

## 4) Security Baseline (day 1, not later)
- [x] Secrets in env/secret store only (never in repo/chat)
- [x] Least-privilege token scopes (`youtube.readonly`)
- [ ] Sensitive actions require approval gate (N/A for ingest-only now, add before outbound integrations)
- [ ] Audit logging enabled (add structured run logs in v1)
- [x] Known-good config snapshot created
- [x] Rollback command tested once (`safe-restart.sh` for gateway; git rollback for app)

## 5) Operational Baseline
- [x] Health check command (`npm run ingest -- ...` + non-zero on failures)
- [x] Safe restart path (gateway side)
- [ ] Error alert path (add Slack/WhatsApp alert in v1.1)
- [ ] Weekly review cadence (set Sunday review)
- [ ] KPI dashboard/log summary (add lightweight markdown KPI report)

## 6) Data Policy
- **Data classes:**
  - Public: video metadata (title, views, duration)
  - Internal: derived summaries/insights
  - Restricted: OAuth tokens and credentials
- **Retention policy:** Keep snapshots 30 days by default; keep weekly rollups long-term.
- **Redaction rules:** Never include tokens, client secret, or raw auth URLs in logs/reports.
- **Export/deletion policy:** Export via markdown/json; delete by removing files in `data/` and `.secrets/` as needed.

## 7) Release Plan (staged)
- **v0.1:** Scaffold + local snapshot output ✅
- **v0.2:** YouTube API metadata ingest ✅
- **v0.3:** OAuth private playlist support ✅
- **v1.0 (next):**
  - normalized canonical dataset file
  - dedupe/index by `videoId`
  - insight report command (`npm run report`)
  - run log summary
- **Go-live criteria:**
  - 3 consecutive successful ingest runs
  - private + public source both verified
  - insight report produced from latest dataset

## 8) Risk Register (top 5)
1. **Risk:** OAuth token expiry/revocation
   - **Impact:** Ingest fails for private playlists
   - **Mitigation:** re-auth command + clear error message
   - **Detection signal:** 401/403 auth errors
   - **Rollback action:** switch to public/API-key mode where possible

2. **Risk:** YouTube quota exhaustion
   - **Impact:** incomplete data pulls
   - **Mitigation:** batch requests, cap `maxItems`, retry strategy
   - **Detection signal:** quotaExceeded errors
   - **Rollback action:** reduce scope and rerun later

3. **Risk:** Schema drift from API changes
   - **Impact:** parser breaks / missing fields
   - **Mitigation:** defensive parsing + defaults
   - **Detection signal:** spike in null/undefined fields
   - **Rollback action:** pin to last known parser version

4. **Risk:** Data clutter from snapshot sprawl
   - **Impact:** hard-to-use outputs
   - **Mitigation:** add normalized canonical output and retention cleanup
   - **Detection signal:** large `data/` growth, duplicate records
   - **Rollback action:** keep latest-only policy

5. **Risk:** Secrets leak via logs/commits
   - **Impact:** account compromise
   - **Mitigation:** `.gitignore`, redaction checks, manual review before push
   - **Detection signal:** secret patterns in diff/log
   - **Rollback action:** rotate credentials immediately

## 9) 72-hour Launch Plan
- **0-24h:** Implement normalized canonical dataset writer + dedupe by `videoId`.
- **24-48h:** Build `report` command to generate actionable markdown insights.
- **48-72h:** Add run logs/KPI summary + test against 2 playlists (public + private).

## 10) Final pre-build gate
- [x] Scope
- [x] Job specs
- [x] Model routing
- [x] Security baseline
- [x] Rollback path
