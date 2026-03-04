# Add-ons Modular Skill Pack

Last updated: 2026-03-04

## Goal

Keep external skills as profile-driven add-ons so they can be enabled/disabled without changing core integrations.

## Config Source

- [config/addons.yaml](/Users/palba/Projects/Clawdio/config/addons.yaml)

Structure:

1. `profiles`: named add-on presets with `active_profile`.
2. `addons`: add-on catalog with `enabled`, `tier`, env requirements, and conflict hints.

## Current Recommendation Tiers

1. `recommended_now`: `gemini`, `github`, `model_usage`, `markdown_converter`, `video_transcript_downloader`, `summarize`.
2. `optional`: `brave_search`, `slack`, `trello`, `nano_pdf`, `frontend_design`, `onepassword`.
3. `skip_for_now`: `gog`, `mcporter`, `self_improving_agent`, `tavily_search`.

## Commands

1. Show integration + add-on profile matrix:
2. `python3 scripts/profile_matrix.py`
3. Switch add-on profile:
4. `python3 scripts/set_active_profiles.py --addons-profile addons_core_recommended`
5. Validate required env for chosen add-on profile:
6. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --strict --addons-profile addons_core_recommended`
7. Inspect optional keys for add-ons:
8. `python3 scripts/check_env_requirements.py --env-file /path/to/openclaw.env --include-optional --addons-profile addons_search_brave`

## Conflict Rule

1. Keep exactly one API search add-on active at a time (`brave_search` or `tavily_search`).
2. Default recommendation is `brave_search` and `tavily_search` disabled.
