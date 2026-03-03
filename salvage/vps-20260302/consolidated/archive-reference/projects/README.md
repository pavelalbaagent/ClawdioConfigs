# Project: YouTube Watchlist Auto-Pipeline

## Purpose
Automatically collect AI-relevant videos into a watchlist, generate daily summaries, and promote high-value ideas into actionable projects.

## Outcome
A low-friction pipeline:
1. **Discover** videos (channels/playlists/feeds)
2. **Queue** candidates in `youtube-watchlist.md`
3. **Summarize** selected videos daily into Slack `#news`
4. **Promote** best ideas into `#projects` with clear next actions

## Current State
- Daily digest jobs already post to Slack `#news`
- `youtube-watchlist.md` exists as manual queue input
- Daily YouTube watchlist summary cron job exists

## Target Architecture (phased)

### Phase 1 — Reliable manual-in + auto-summary (now)
- Input: manually added links in `youtube-watchlist.md`
- Processing: daily cron summarizes `pending` links
- Output: summary in Slack `#news`

### Phase 2 — Semi-automatic ingestion
- Source options (choose one first):
  - YouTube channel RSS feeds
  - YouTube playlist RSS feed
  - Zapier/Make webhook appending to watchlist file
- Deduplicate by `videoId`
- Auto-tag: `tool`, `use-case`, `news`, `tutorial`

### Phase 3 — Promotion engine (#tools -> #projects)
- Daily/weekly scoring for promoted candidates
- Score dimensions: ROI, effort, relevance, novelty
- Push top 1–3 recommendations to `#projects`

## Deliverables
- Ingestion flow (RSS or Zapier/Make)
- Queue format + dedup rules
- Daily summary format stable in `#news`
- Promotion template and criteria
- Minimal runbook for maintenance
