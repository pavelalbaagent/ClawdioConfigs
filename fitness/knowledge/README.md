# Fitness Grounding Corpus

## Purpose

1. This folder is a read-only coaching context source for `fitness_coach`.
2. It is for conversational guidance, recovery reasoning, progression heuristics, and curated trend summaries.
3. It is not the source of truth for workout control, queue state, or logged sets.

## Source Of Truth Boundary

1. Deterministic workout control stays in SQLite plus the canonical files in `fitness/`.
2. Program definition still lives in:
   - `fitness/PROGRAM.md`
   - `fitness/ATHLETE_PROFILE.md`
   - `fitness/RULES.md`
   - `fitness/EXERCISE_LIBRARY.md`
   - `fitness/SESSION_QUEUE.md`
3. Files in this folder may inform coaching language, but they must not silently override the canonical plan.

## Update Pattern

1. Add short curated markdown notes instead of large dumps.
2. Prefer one note per topic or review batch.
3. Include concrete takeaways the chat runtime can quote or summarize quickly.
4. If a new external research review changes coaching guidance, summarize it here and keep the change explicit.
