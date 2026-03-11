# Provider Smoke Checks

Last updated: 2026-03-09

## Goal

Separate three states that were previously mixed together:

1. declared in config
2. wired locally with env vars / commands
3. actually working with a live probe

## Runtime

Main file:

1. [provider_smoke_check.py](/Users/palba/Projects/Personal/Clawdio/scripts/provider_smoke_check.py)

Snapshot output:

1. `data/provider-smoke-status.json`

## What it checks

For each configured provider:

1. required env vars present or missing
2. required CLI command present or missing
3. default model resolved
4. lane usage in current routing config
5. optional live probe result

It also exposes a situation matrix so you can see the exact provider-model candidates for:

1. `quick_read_write`
2. `coding_and_integration`
3. `architecture_or_high_ambiguity`
4. the rest of the configured situations

## Run

Local wiring check only:

```bash
python3 scripts/provider_smoke_check.py --env-file secrets/openclaw.env --json
```

Live probe:

```bash
python3 scripts/provider_smoke_check.py --env-file secrets/openclaw.env --live --json
```

## Current intended exact routing

1. `L1_low_cost`
   - provider: `google_ai_studio_free`
   - model: `gemini-2.5-flash-lite`
2. `L1_openrouter_free_fallback`
   - provider: `openrouter_free_overflow`
   - model: `openrouter/free`
3. `L2_balanced`
   - primary: `google_ai_studio_free` -> `gemini-2.5-flash`
   - reserve: `anthropic_credit_pool` -> `claude-sonnet-4-20250514`
4. `L3_heavy`
   - primary: `anthropic_credit_pool` -> `claude-sonnet-4-20250514`
   - fallback: `google_ai_studio_free` -> `gemini-2.5-pro`
   - manual supervised tools: `codex`, `gemini`

## Dashboard

The dashboard now shows:

1. provider local readiness
2. last live probe result
3. exact routed model candidates per situation
4. buttons for `Run Local Check` and `Run Live Probe`

This is intended to answer:

1. which model would be used here
2. is that provider actually wired
3. has it been live-tested
