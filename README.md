# OpenClaw Rebuild Workspace

This workspace is for rebuilding OpenClaw from scratch in a config-first, modular, security-first way.

## What is already here

1. Recovery artifacts extracted from previous notes in `ops/scripts/`.
2. Planning docs in `docs/`.
3. Declarative config templates in `config/` so you can predefine behavior and avoid repeated prompt-based setup.
4. Cross-repo salvage notes from `clawdio-backups` and `YTIngest` in `docs/08-*` and `docs/09-*`.

## Suggested starting sequence

1. Review [docs/00-recovered-assets.md](/Users/palba/Projects/Clawdio/docs/00-recovered-assets.md).
2. Fill `config/*.yaml` with your real preferences and API constraints.
3. Execute the phase checklist in [docs/02-implementation-plan.md](/Users/palba/Projects/Clawdio/docs/02-implementation-plan.md).
4. Initialize git in this folder once you are happy with the initial scaffold.
5. Review recovered v1 config signals in [config/recovered/openclaw-v1-derived.yaml](/Users/palba/Projects/Clawdio/config/recovered/openclaw-v1-derived.yaml).

## Important constraint

For unattended server automation, you normally need API-accessible models/keys.
Use ChatGPT Plus primarily for supervised heavy tasks via CLI sessions, and reserve API quota for autonomous tasks.
