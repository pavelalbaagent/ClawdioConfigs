# Tasks

## Immediate
- [ ] Fill `Channels to Monitor` in `/home/pavel/.openclaw/workspace/youtube-watchlist.md`
- [ ] Add 5-10 seed videos in queue with `pending`
- [ ] Validate tomorrow's 07:30 summary format in Slack `#news`

## Build Sprint 1 (MVP)
- [ ] Pick ingestion path: RSS or Zapier/Make
- [ ] Create append-only ingestion script/flow
- [ ] Implement dedup (`videoId` or normalized URL)
- [ ] Add status transitions (`pending -> summarized -> promoted/skipped`)

## Build Sprint 2 (Promotion)
- [ ] Define relevance scoring rubric (0-5)
- [ ] Add "Promote to #projects" section to daily output
- [ ] Add weekly roll-up summary

## Nice-to-have
- [ ] Add transcript-based summarization when transcript available
- [ ] Add confidence score + source freshness per item
