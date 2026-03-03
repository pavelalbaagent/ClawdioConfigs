# Implementation Plan

## 0) Decisions to lock
- Primary ingestion source: RSS first (simplest)
- Summary cadence: daily 07:30 (already configured)
- Promotion cadence: daily lightweight + weekly deeper review

## 1) Data model
Use this line format in `youtube-watchlist.md` queue:

- [ ] pending | <title> | <url> | source:<channel> | tag:<tool/use-case/news/tutorial>
- [ ] summarized | ...
- [ ] promoted | ...
- [ ] skipped | ...

## 2) Ingestion MVP
- Add tracked channels with RSS URLs
- Pull new videos once per day
- Append unseen videos as `pending`
- Keep only newest N pending entries (e.g., 30)

## 3) Summarization
- Daily cron reads `pending`
- Summarize top 3-5 (by recency/relevance)
- Post concise block to Slack `#news`
- Mark items as `summarized`

## 4) Promotion logic
Promote candidate if:
- Relevance to current goals is high
- Can be tested in <= 60 min
- Practical output expected (prototype, benchmark, or doc)

Promotion output format:
- Candidate
- Why now
- ROI (H/M/L)
- Effort (S/M/L)
- First 60-min action

## 5) Reliability
- Dedup by video URL/video ID
- Fail-safe if source unavailable: skip + report
- Keep pipeline idempotent (safe to rerun)
