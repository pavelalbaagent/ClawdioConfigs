# OpenClaw Rebuild Workspace

This workspace is for rebuilding OpenClaw from scratch in a config-first, modular, security-first way.

## What is already here

1. Recovery artifacts extracted from previous notes in `ops/scripts/`.
2. Planning docs in `docs/`.
3. Declarative config templates in `config/` so you can predefine behavior and avoid repeated prompt-based setup.
4. Cross-repo salvage notes from `clawdio-backups` and `YTIngest` in `docs/08-*` and `docs/09-*`.
5. VPS salvage triage and consolidation decisions in `docs/10-*`, `docs/11-*`, and `salvage/vps-20260302/`.
6. Reminder v2 deterministic behavior spec in [docs/12-reminder-v2-spec.md](/Users/palba/Projects/Clawdio/docs/12-reminder-v2-spec.md) and [config/reminders.yaml](/Users/palba/Projects/Clawdio/config/reminders.yaml).
7. Platform-agnostic event contract and normalizer in [docs/13-platform-event-contract.md](/Users/palba/Projects/Clawdio/docs/13-platform-event-contract.md) and [normalize_event.py](/Users/palba/Projects/Clawdio/scripts/normalize_event.py).
8. Local quality gates in [docs/14-local-quality-gates.md](/Users/palba/Projects/Clawdio/docs/14-local-quality-gates.md), [validate_configs.py](/Users/palba/Projects/Clawdio/scripts/validate_configs.py), and [scan_secrets.py](/Users/palba/Projects/Clawdio/scripts/scan_secrets.py).
9. Dry-run VPS bootstrap plan in [docs/15-bootstrap-dry-run.md](/Users/palba/Projects/Clawdio/docs/15-bootstrap-dry-run.md) and [bootstrap_vps_dry_run.sh](/Users/palba/Projects/Clawdio/ops/scripts/bootstrap_vps_dry_run.sh).
10. Model telemetry schema/report tooling in [docs/16-model-telemetry.md](/Users/palba/Projects/Clawdio/docs/16-model-telemetry.md) and [model_usage_report.py](/Users/palba/Projects/Clawdio/scripts/model_usage_report.py).
11. Promoted keep-core VPS assets in [docs/17-promoted-vps-assets.md](/Users/palba/Projects/Clawdio/docs/17-promoted-vps-assets.md) and `docs/recovered/` + `ops/recovered/`.
12. Review of external prompt/template bundle in [docs/19-possible-improvements-review.md](/Users/palba/Projects/Clawdio/docs/19-possible-improvements-review.md).
13. Integration profile system and credential inventory in [docs/20-integration-connection-structure.md](/Users/palba/Projects/Clawdio/docs/20-integration-connection-structure.md), [docs/21-credentials-onboarding-checklist.md](/Users/palba/Projects/Clawdio/docs/21-credentials-onboarding-checklist.md), and [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).
14. Session lifecycle policy in [docs/22-session-lifecycle-policy.md](/Users/palba/Projects/Clawdio/docs/22-session-lifecycle-policy.md) and [config/session_policy.yaml](/Users/palba/Projects/Clawdio/config/session_policy.yaml).
15. Environment readiness checker in [check_env_requirements.py](/Users/palba/Projects/Clawdio/scripts/check_env_requirements.py) and template [.env.example](/Users/palba/Projects/Clawdio/.env.example).
16. Provider bundle checklist in [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Clawdio/docs/23-provider-bundles-checklist.md).
17. n8n workflow contract pack in [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Clawdio/docs/24-n8n-workflow-contract-pack.md) and `contracts/n8n/`.

## Suggested starting sequence

1. Review [docs/00-recovered-assets.md](/Users/palba/Projects/Clawdio/docs/00-recovered-assets.md).
2. Review VPS salvage triage in [docs/10-vps-salvage-triage.md](/Users/palba/Projects/Clawdio/docs/10-vps-salvage-triage.md) and promoted assets in [docs/17-promoted-vps-assets.md](/Users/palba/Projects/Clawdio/docs/17-promoted-vps-assets.md).
3. Pick integration profile and fill required keys:
4. `python3 scripts/check_env_requirements.py`
5. `python3 scripts/check_env_requirements.py --strict`
6. Review provider bundle and n8n contracts:
7. [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Clawdio/docs/23-provider-bundles-checklist.md)
8. [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Clawdio/docs/24-n8n-workflow-contract-pack.md)
9. Run local gates:
10. `python3 scripts/validate_configs.py --config-dir config`
11. `python3 scripts/scan_secrets.py`
12. `python3 -m unittest discover -s tests -p 'test_*.py' -v`
13. Execute the phase checklist in [docs/02-implementation-plan.md](/Users/palba/Projects/Clawdio/docs/02-implementation-plan.md).

## Important constraint

For unattended server automation, you normally need API-accessible models/keys.
Use ChatGPT Plus primarily for supervised heavy tasks via CLI sessions, and reserve API quota for autonomous tasks.
