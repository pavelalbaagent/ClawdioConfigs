# OpenClaw Rebuild Workspace

This workspace is for rebuilding OpenClaw from scratch in a config-first, modular, security-first way.

## What is already here

1. Recovery artifacts extracted from previous notes in `ops/scripts/`.
2. Planning docs in `docs/`.
3. Declarative config templates in `config/` so you can predefine behavior and avoid repeated prompt-based setup.
4. Cross-repo salvage notes from `clawdio-backups` and `YTIngest` in `docs/08-*` and `docs/09-*`.
5. VPS salvage triage and consolidation decisions in `docs/10-*`, `docs/11-*`, and the remaining recovery templates under `ops/recovered/`.
6. Reminder v2 deterministic behavior spec in [docs/12-reminder-v2-spec.md](/Users/palba/Projects/Clawdio/docs/12-reminder-v2-spec.md) and [config/reminders.yaml](/Users/palba/Projects/Clawdio/config/reminders.yaml).
7. Platform-agnostic event contract and normalizer in [docs/13-platform-event-contract.md](/Users/palba/Projects/Clawdio/docs/13-platform-event-contract.md) and [normalize_event.py](/Users/palba/Projects/Clawdio/scripts/normalize_event.py).
8. Local quality gates in [docs/14-local-quality-gates.md](/Users/palba/Projects/Clawdio/docs/14-local-quality-gates.md), [validate_configs.py](/Users/palba/Projects/Clawdio/scripts/validate_configs.py), and [scan_secrets.py](/Users/palba/Projects/Clawdio/scripts/scan_secrets.py).
9. Dry-run VPS bootstrap plan in [docs/15-bootstrap-dry-run.md](/Users/palba/Projects/Clawdio/docs/15-bootstrap-dry-run.md) and [bootstrap_vps_dry_run.sh](/Users/palba/Projects/Clawdio/ops/scripts/bootstrap_vps_dry_run.sh).
10. Model telemetry schema/report tooling in [docs/16-model-telemetry.md](/Users/palba/Projects/Clawdio/docs/16-model-telemetry.md) and [model_usage_report.py](/Users/palba/Projects/Clawdio/scripts/model_usage_report.py).
11. Promoted VPS recovery templates in [docs/17-promoted-vps-assets.md](/Users/palba/Projects/Clawdio/docs/17-promoted-vps-assets.md), [openclaw-v1-derived.yaml](/Users/palba/Projects/Clawdio/config/recovered/openclaw-v1-derived.yaml), and `ops/recovered/`.
12. Review of external prompt/template bundle in [docs/19-possible-improvements-review.md](/Users/palba/Projects/Clawdio/docs/19-possible-improvements-review.md).
13. Integration profile system and credential inventory in [docs/20-integration-connection-structure.md](/Users/palba/Projects/Clawdio/docs/20-integration-connection-structure.md), [docs/21-credentials-onboarding-checklist.md](/Users/palba/Projects/Clawdio/docs/21-credentials-onboarding-checklist.md), and [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).
14. Session lifecycle policy in [docs/22-session-lifecycle-policy.md](/Users/palba/Projects/Clawdio/docs/22-session-lifecycle-policy.md) and [config/session_policy.yaml](/Users/palba/Projects/Clawdio/config/session_policy.yaml).
15. Environment readiness checker in [check_env_requirements.py](/Users/palba/Projects/Clawdio/scripts/check_env_requirements.py) and template [.env.example](/Users/palba/Projects/Clawdio/.env.example).
16. Provider bundle checklist in [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Clawdio/docs/23-provider-bundles-checklist.md).
17. n8n workflow contract pack in [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Clawdio/docs/24-n8n-workflow-contract-pack.md) and `contracts/n8n/`.
18. VPS transcript ingestion runbook in [docs/26-ytingest-transcript-ingestion-runbook.md](/Users/palba/Projects/Clawdio/docs/26-ytingest-transcript-ingestion-runbook.md).
19. Public-video transcript access setup in [docs/27-youtube-public-transcript-access.md](/Users/palba/Projects/Clawdio/docs/27-youtube-public-transcript-access.md).
20. Transcript-based usefulness analysis in [docs/28-youtube-transcript-usefulness-review.md](/Users/palba/Projects/Clawdio/docs/28-youtube-transcript-usefulness-review.md).
21. Hybrid memory runbook (`1+2+4`) in [docs/29-memory-hybrid-124-runbook.md](/Users/palba/Projects/Clawdio/docs/29-memory-hybrid-124-runbook.md), [config/memory.yaml](/Users/palba/Projects/Clawdio/config/memory.yaml), [memory_index_sync.py](/Users/palba/Projects/Clawdio/scripts/memory_index_sync.py), and [memory_search.py](/Users/palba/Projects/Clawdio/scripts/memory_search.py).
22. Reminder failure postmortem and hardening notes in [docs/30-reminder-failure-analysis.md](/Users/palba/Projects/Clawdio/docs/30-reminder-failure-analysis.md).
23. Reminder scheduler payload guard in [reminder_scheduler_adapter.py](/Users/palba/Projects/Clawdio/ops/scripts/reminder_scheduler_adapter.py) and [docs/12-reminder-v2-spec.md](/Users/palba/Projects/Clawdio/docs/12-reminder-v2-spec.md).
24. Secrets-file fast onboarding in [docs/31-secrets-file-onboarding.md](/Users/palba/Projects/Clawdio/docs/31-secrets-file-onboarding.md).
25. Modular optionalization matrix and stage profiles in [docs/32-modular-optionalization-matrix.md](/Users/palba/Projects/Clawdio/docs/32-modular-optionalization-matrix.md), [profile_matrix.py](/Users/palba/Projects/Clawdio/scripts/profile_matrix.py), and [set_active_profiles.py](/Users/palba/Projects/Clawdio/scripts/set_active_profiles.py).
26. Local dashboard control plane in [docs/33-dashboard-control-plane.md](/Users/palba/Projects/Clawdio/docs/33-dashboard-control-plane.md) and [dashboard/server.py](/Users/palba/Projects/Clawdio/dashboard/server.py).
27. Situation-based model routing playbook and resolver in [docs/34-model-routing-playbook.md](/Users/palba/Projects/Clawdio/docs/34-model-routing-playbook.md) and [model_route_decider.py](/Users/palba/Projects/Clawdio/scripts/model_route_decider.py).
28. Skill add-on modular pack in [docs/35-addons-modular-skill-pack.md](/Users/palba/Projects/Clawdio/docs/35-addons-modular-skill-pack.md) and [config/addons.yaml](/Users/palba/Projects/Clawdio/config/addons.yaml).
29. One-by-one token setup playbook in [docs/36-token-acquisition-playbook.md](/Users/palba/Projects/Clawdio/docs/36-token-acquisition-playbook.md) with local secrets file `secrets/openclaw.env`.
30. Fitness agent architecture and memory plan in [docs/37-fitness-agent-memory-plan.md](/Users/palba/Projects/Clawdio/docs/37-fitness-agent-memory-plan.md), with intake guide [docs/38-fitness-intake-questionnaire.md](/Users/palba/Projects/Clawdio/docs/38-fitness-intake-questionnaire.md) and config [config/fitness_agent.yaml](/Users/palba/Projects/Clawdio/config/fitness_agent.yaml).
31. Fitness canonical layout in [docs/39-fitness-canonical-layout.md](/Users/palba/Projects/Clawdio/docs/39-fitness-canonical-layout.md), with canonical files under `fitness/` and reference workbook [Workout_plan_reference.xlsx](/Users/palba/Projects/Clawdio/fitness/reference/Workout_plan_reference.xlsx).
32. Historical workout-planning iterations are archived under `docs/archive/fitness-planning/`.
33. Repo-wide module maturity view in [docs/40-runtime-status-matrix.md](/Users/palba/Projects/Clawdio/docs/40-runtime-status-matrix.md).
34. Recommended operationalization order in [docs/41-operationalization-priorities.md](/Users/palba/Projects/Clawdio/docs/41-operationalization-priorities.md).
35. Email/calendar decision note in [docs/42-email-and-calendar-strategy.md](/Users/palba/Projects/Clawdio/docs/42-email-and-calendar-strategy.md).
36. Gmail scheduled inbox-processing plan in [docs/43-gmail-inbox-processing-plan.md](/Users/palba/Projects/Clawdio/docs/43-gmail-inbox-processing-plan.md) and [contracts/gmail/inbox-processing-rules.yaml](/Users/palba/Projects/Clawdio/contracts/gmail/inbox-processing-rules.yaml).
37. Shared Google Drive workspace plan in [docs/44-drive-shared-workspace-plan.md](/Users/palba/Projects/Clawdio/docs/44-drive-shared-workspace-plan.md) and [contracts/drive/shared-workspace.yaml](/Users/palba/Projects/Clawdio/contracts/drive/shared-workspace.yaml).
38. Gmail inbox processor runtime in [gmail_inbox_processor.py](/Users/palba/Projects/Clawdio/scripts/gmail_inbox_processor.py) with SQLite schema [sqlite_schema.sql](/Users/palba/Projects/Clawdio/contracts/gmail/sqlite_schema.sql).
39. Drive shared-root bootstrap runtime in [drive_workspace_bootstrap.py](/Users/palba/Projects/Clawdio/scripts/drive_workspace_bootstrap.py).
40. Micro-apps architecture note in [docs/45-micro-apps-architecture.md](/Users/palba/Projects/Clawdio/docs/45-micro-apps-architecture.md).
41. Braindump micro-app plan and runtime in [docs/46-braindump-app-plan.md](/Users/palba/Projects/Clawdio/docs/46-braindump-app-plan.md), [braindump_app.py](/Users/palba/Projects/Clawdio/scripts/braindump_app.py), and schema [contracts/braindump/sqlite_schema.sql](/Users/palba/Projects/Clawdio/contracts/braindump/sqlite_schema.sql).
42. Project-space boundary and session-vs-agent rules in [docs/47-project-spaces-and-session-agent-strategy.md](/Users/palba/Projects/Clawdio/docs/47-project-spaces-and-session-agent-strategy.md).
43. Project-space routing and assignment are now exposed through the dashboard and routing helpers, including [space_router.py](/Users/palba/Projects/Clawdio/scripts/space_router.py).
44. Google Calendar runtime in [docs/48-google-calendar-runtime.md](/Users/palba/Projects/Clawdio/docs/48-google-calendar-runtime.md) and [google_calendar_runtime.py](/Users/palba/Projects/Clawdio/scripts/google_calendar_runtime.py).
45. Personal task runtime in [docs/49-personal-task-runtime.md](/Users/palba/Projects/Clawdio/docs/49-personal-task-runtime.md) and [personal_task_runtime.py](/Users/palba/Projects/Clawdio/scripts/personal_task_runtime.py).

## Suggested starting sequence

1. Review [docs/00-recovered-assets.md](/Users/palba/Projects/Clawdio/docs/00-recovered-assets.md).
2. Review VPS salvage triage in [docs/10-vps-salvage-triage.md](/Users/palba/Projects/Clawdio/docs/10-vps-salvage-triage.md) and promoted assets in [docs/17-promoted-vps-assets.md](/Users/palba/Projects/Clawdio/docs/17-promoted-vps-assets.md).
3. Pick integration/memory/add-on profiles and fill required keys:
4. `python3 scripts/check_env_requirements.py`
5. `python3 scripts/check_env_requirements.py --strict --addons-profile addons_off`
6. Review provider bundle and n8n contracts:
7. [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Clawdio/docs/23-provider-bundles-checklist.md)
8. [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Clawdio/docs/24-n8n-workflow-contract-pack.md)
9. Run local gates:
10. `python3 scripts/validate_configs.py --config-dir config`
11. `python3 scripts/scan_secrets.py`
12. `python3 -m unittest discover -s tests -p 'test_*.py' -v`
13. Configure and test hybrid memory:
14. [docs/29-memory-hybrid-124-runbook.md](/Users/palba/Projects/Clawdio/docs/29-memory-hybrid-124-runbook.md)
15. `python3 scripts/memory_index_sync.py --workspace /path/to/workspace --dry-run`
16. Set dashboard auth token before starting the dashboard: `export OPENCLAW_DASHBOARD_TOKEN='<strong-random-token>'`
17. Start the local dashboard control plane (optional): `python3 dashboard/server.py --host 127.0.0.1 --port 18789`
18. Execute the phase checklist in [docs/02-implementation-plan.md](/Users/palba/Projects/Clawdio/docs/02-implementation-plan.md).
19. Use [docs/40-runtime-status-matrix.md](/Users/palba/Projects/Clawdio/docs/40-runtime-status-matrix.md) and [docs/41-operationalization-priorities.md](/Users/palba/Projects/Clawdio/docs/41-operationalization-priorities.md) before adding new modules.

## Important constraint

For unattended server automation, you normally need API-accessible models/keys.
Use ChatGPT Plus primarily for supervised heavy tasks via CLI sessions, and reserve API quota for autonomous tasks.
