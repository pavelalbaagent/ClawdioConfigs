# OpenClaw Rebuild Workspace

This workspace is for rebuilding OpenClaw from scratch in a config-first, modular, security-first way.

## What is already here

1. Recovery artifacts extracted from previous notes in `ops/scripts/`.
2. Planning docs in `docs/`.
3. Declarative config templates in `config/` so you can predefine behavior and avoid repeated prompt-based setup.
4. Cross-repo salvage notes from `clawdio-backups` and `YTIngest` in `docs/08-*` and `docs/09-*`.
5. VPS salvage triage and consolidation decisions in `docs/10-*`, `docs/11-*`, and the remaining recovery templates under `ops/recovered/`.
6. Reminder v2 deterministic behavior spec in [docs/12-reminder-v2-spec.md](/Users/palba/Projects/Personal/Clawdio/docs/12-reminder-v2-spec.md) and [config/reminders.yaml](/Users/palba/Projects/Personal/Clawdio/config/reminders.yaml).
7. Platform-agnostic event contract and normalizer in [docs/13-platform-event-contract.md](/Users/palba/Projects/Personal/Clawdio/docs/13-platform-event-contract.md) and [normalize_event.py](/Users/palba/Projects/Personal/Clawdio/scripts/normalize_event.py).
8. Local quality gates in [docs/14-local-quality-gates.md](/Users/palba/Projects/Personal/Clawdio/docs/14-local-quality-gates.md), [validate_configs.py](/Users/palba/Projects/Personal/Clawdio/scripts/validate_configs.py), and [scan_secrets.py](/Users/palba/Projects/Personal/Clawdio/scripts/scan_secrets.py).
9. Dry-run VPS bootstrap plan in [docs/15-bootstrap-dry-run.md](/Users/palba/Projects/Personal/Clawdio/docs/15-bootstrap-dry-run.md) and [bootstrap_vps_dry_run.sh](/Users/palba/Projects/Personal/Clawdio/ops/scripts/bootstrap_vps_dry_run.sh).
10. Model telemetry schema/report tooling in [docs/16-model-telemetry.md](/Users/palba/Projects/Personal/Clawdio/docs/16-model-telemetry.md) and [model_usage_report.py](/Users/palba/Projects/Personal/Clawdio/scripts/model_usage_report.py).
11. Promoted VPS recovery templates in [docs/17-promoted-vps-assets.md](/Users/palba/Projects/Personal/Clawdio/docs/17-promoted-vps-assets.md), [openclaw-v1-derived.yaml](/Users/palba/Projects/Personal/Clawdio/config/recovered/openclaw-v1-derived.yaml), and `ops/recovered/`.
12. Review of external prompt/template bundle in [docs/19-possible-improvements-review.md](/Users/palba/Projects/Personal/Clawdio/docs/19-possible-improvements-review.md).
13. Integration profile system and credential inventory in [docs/20-integration-connection-structure.md](/Users/palba/Projects/Personal/Clawdio/docs/20-integration-connection-structure.md), [docs/21-credentials-onboarding-checklist.md](/Users/palba/Projects/Personal/Clawdio/docs/21-credentials-onboarding-checklist.md), and [config/integrations.yaml](/Users/palba/Projects/Personal/Clawdio/config/integrations.yaml).
14. Session lifecycle policy in [docs/22-session-lifecycle-policy.md](/Users/palba/Projects/Personal/Clawdio/docs/22-session-lifecycle-policy.md) and [config/session_policy.yaml](/Users/palba/Projects/Personal/Clawdio/config/session_policy.yaml).
15. Environment readiness checker in [check_env_requirements.py](/Users/palba/Projects/Personal/Clawdio/scripts/check_env_requirements.py) and template [.env.example](/Users/palba/Projects/Personal/Clawdio/.env.example).
16. Provider bundle checklist in [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Personal/Clawdio/docs/23-provider-bundles-checklist.md).
17. n8n workflow contract pack in [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Personal/Clawdio/docs/24-n8n-workflow-contract-pack.md) and `contracts/n8n/`.
18. VPS transcript ingestion runbook in [docs/26-ytingest-transcript-ingestion-runbook.md](/Users/palba/Projects/Personal/Clawdio/docs/26-ytingest-transcript-ingestion-runbook.md).
19. Public-video transcript access setup in [docs/27-youtube-public-transcript-access.md](/Users/palba/Projects/Personal/Clawdio/docs/27-youtube-public-transcript-access.md).
20. Transcript-based usefulness analysis in [docs/28-youtube-transcript-usefulness-review.md](/Users/palba/Projects/Personal/Clawdio/docs/28-youtube-transcript-usefulness-review.md).
21. Hybrid memory runbook (`1+2+4`) in [docs/29-memory-hybrid-124-runbook.md](/Users/palba/Projects/Personal/Clawdio/docs/29-memory-hybrid-124-runbook.md), [config/memory.yaml](/Users/palba/Projects/Personal/Clawdio/config/memory.yaml), [memory_index_sync.py](/Users/palba/Projects/Personal/Clawdio/scripts/memory_index_sync.py), and [memory_search.py](/Users/palba/Projects/Personal/Clawdio/scripts/memory_search.py).
22. Reminder failure postmortem and hardening notes in [docs/30-reminder-failure-analysis.md](/Users/palba/Projects/Personal/Clawdio/docs/30-reminder-failure-analysis.md).
23. Reminder scheduler payload guard in [reminder_scheduler_adapter.py](/Users/palba/Projects/Personal/Clawdio/ops/scripts/reminder_scheduler_adapter.py) and [docs/12-reminder-v2-spec.md](/Users/palba/Projects/Personal/Clawdio/docs/12-reminder-v2-spec.md).
24. Secrets-file fast onboarding in [docs/31-secrets-file-onboarding.md](/Users/palba/Projects/Personal/Clawdio/docs/31-secrets-file-onboarding.md).
25. Modular optionalization matrix and stage profiles in [docs/32-modular-optionalization-matrix.md](/Users/palba/Projects/Personal/Clawdio/docs/32-modular-optionalization-matrix.md), [profile_matrix.py](/Users/palba/Projects/Personal/Clawdio/scripts/profile_matrix.py), and [set_active_profiles.py](/Users/palba/Projects/Personal/Clawdio/scripts/set_active_profiles.py).
26. Local dashboard control plane in [docs/33-dashboard-control-plane.md](/Users/palba/Projects/Personal/Clawdio/docs/33-dashboard-control-plane.md) and [dashboard/server.py](/Users/palba/Projects/Personal/Clawdio/dashboard/server.py).
27. Situation-based model routing playbook and resolver in [docs/34-model-routing-playbook.md](/Users/palba/Projects/Personal/Clawdio/docs/34-model-routing-playbook.md) and [model_route_decider.py](/Users/palba/Projects/Personal/Clawdio/scripts/model_route_decider.py).
28. Skill add-on modular pack in [docs/35-addons-modular-skill-pack.md](/Users/palba/Projects/Personal/Clawdio/docs/35-addons-modular-skill-pack.md) and [config/addons.yaml](/Users/palba/Projects/Personal/Clawdio/config/addons.yaml).
29. One-by-one token setup playbook in [docs/36-token-acquisition-playbook.md](/Users/palba/Projects/Personal/Clawdio/docs/36-token-acquisition-playbook.md) with local secrets file `secrets/openclaw.env`.
30. Fitness agent architecture and memory plan in [docs/37-fitness-agent-memory-plan.md](/Users/palba/Projects/Personal/Clawdio/docs/37-fitness-agent-memory-plan.md), with intake guide [docs/38-fitness-intake-questionnaire.md](/Users/palba/Projects/Personal/Clawdio/docs/38-fitness-intake-questionnaire.md) and config [config/fitness_agent.yaml](/Users/palba/Projects/Personal/Clawdio/config/fitness_agent.yaml).
31. Fitness canonical layout in [docs/39-fitness-canonical-layout.md](/Users/palba/Projects/Personal/Clawdio/docs/39-fitness-canonical-layout.md), with canonical files under `fitness/` and reference workbook [Workout_plan_reference.xlsx](/Users/palba/Projects/Personal/Clawdio/fitness/reference/Workout_plan_reference.xlsx).
32. Historical workout-planning iterations are archived under `docs/archive/fitness-planning/`.
33. Repo-wide module maturity view in [docs/40-runtime-status-matrix.md](/Users/palba/Projects/Personal/Clawdio/docs/40-runtime-status-matrix.md).
34. Recommended operationalization order in [docs/41-operationalization-priorities.md](/Users/palba/Projects/Personal/Clawdio/docs/41-operationalization-priorities.md).
35. Email/calendar decision note in [docs/42-email-and-calendar-strategy.md](/Users/palba/Projects/Personal/Clawdio/docs/42-email-and-calendar-strategy.md).
36. Gmail scheduled inbox-processing plan in [docs/43-gmail-inbox-processing-plan.md](/Users/palba/Projects/Personal/Clawdio/docs/43-gmail-inbox-processing-plan.md) and [contracts/gmail/inbox-processing-rules.yaml](/Users/palba/Projects/Personal/Clawdio/contracts/gmail/inbox-processing-rules.yaml).
37. Shared Google Drive workspace plan in [docs/44-drive-shared-workspace-plan.md](/Users/palba/Projects/Personal/Clawdio/docs/44-drive-shared-workspace-plan.md) and [contracts/drive/shared-workspace.yaml](/Users/palba/Projects/Personal/Clawdio/contracts/drive/shared-workspace.yaml).
38. Gmail inbox processor runtime in [gmail_inbox_processor.py](/Users/palba/Projects/Personal/Clawdio/scripts/gmail_inbox_processor.py) with SQLite schema [sqlite_schema.sql](/Users/palba/Projects/Personal/Clawdio/contracts/gmail/sqlite_schema.sql).
39. Drive shared-root bootstrap runtime in [drive_workspace_bootstrap.py](/Users/palba/Projects/Personal/Clawdio/scripts/drive_workspace_bootstrap.py).
40. Micro-apps architecture note in [docs/45-micro-apps-architecture.md](/Users/palba/Projects/Personal/Clawdio/docs/45-micro-apps-architecture.md).
41. Braindump micro-app plan and runtime in [docs/46-braindump-app-plan.md](/Users/palba/Projects/Personal/Clawdio/docs/46-braindump-app-plan.md), [braindump_app.py](/Users/palba/Projects/Personal/Clawdio/scripts/braindump_app.py), and schema [contracts/braindump/sqlite_schema.sql](/Users/palba/Projects/Personal/Clawdio/contracts/braindump/sqlite_schema.sql).
42. Project-space boundary and session-vs-agent rules in [docs/47-project-spaces-and-session-agent-strategy.md](/Users/palba/Projects/Personal/Clawdio/docs/47-project-spaces-and-session-agent-strategy.md).
43. Project-space routing and assignment are now exposed through the dashboard and routing helpers, including [space_router.py](/Users/palba/Projects/Personal/Clawdio/scripts/space_router.py).
44. Google Calendar runtime in [docs/48-google-calendar-runtime.md](/Users/palba/Projects/Personal/Clawdio/docs/48-google-calendar-runtime.md) and [google_calendar_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/google_calendar_runtime.py).
45. Personal task runtime in [docs/49-personal-task-runtime.md](/Users/palba/Projects/Personal/Clawdio/docs/49-personal-task-runtime.md) and [personal_task_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/personal_task_runtime.py).
46. Telegram long-polling adapter runtime in [docs/50-telegram-adapter-runtime.md](/Users/palba/Projects/Personal/Clawdio/docs/50-telegram-adapter-runtime.md), [telegram_adapter.py](/Users/palba/Projects/Personal/Clawdio/scripts/telegram_adapter.py), and [openclaw-telegram-adapter.service](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-telegram-adapter.service), with one assistant front door and optional dedicated specialist chat bindings.
47. Gateway and dashboard VPS service templates in [openclaw-gateway.service](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-gateway.service), [openclaw-dashboard.service](/Users/palba/Projects/Personal/Clawdio/ops/systemd/openclaw-dashboard.service), and tunnel defaults in [openclaw-dashboard-tunnel.sh](/Users/palba/Projects/Personal/Clawdio/ops/scripts/openclaw-dashboard-tunnel.sh).
48. Live command-center profile in [integrations.yaml](/Users/palba/Projects/Personal/Clawdio/config/integrations.yaml) (`bootstrap_command_center`) and hybrid memory default in [memory.yaml](/Users/palba/Projects/Personal/Clawdio/config/memory.yaml) (`hybrid_124`) so Telegram + dashboard + reminders + calendar + personal tasks can ship as one coherent operator surface.
49. Provider wiring and live smoke-check tooling in [docs/51-provider-smoke-checks.md](/Users/palba/Projects/Personal/Clawdio/docs/51-provider-smoke-checks.md) and [provider_smoke_check.py](/Users/palba/Projects/Personal/Clawdio/scripts/provider_smoke_check.py).
50. Development thread/workstream policy in [docs/52-development-threading-policy.md](/Users/palba/Projects/Personal/Clawdio/docs/52-development-threading-policy.md) with kickoff template [feature-thread-kickoff.md](/Users/palba/Projects/Personal/Clawdio/docs/templates/feature-thread-kickoff.md) and quick starters [thread-starters.md](/Users/palba/Projects/Personal/Clawdio/docs/templates/thread-starters.md).
51. Agent scheme and governance in [docs/54-agent-scheme-and-governance.md](/Users/palba/Projects/Personal/Clawdio/docs/54-agent-scheme-and-governance.md).
52. Agent realization master plan in [docs/55-agent-realization-master-plan.md](/Users/palba/Projects/Personal/Clawdio/docs/55-agent-realization-master-plan.md).
53. Multi-agent conversational runtime in [docs/56-multi-agent-chat-runtime.md](/Users/palba/Projects/Personal/Clawdio/docs/56-multi-agent-chat-runtime.md) and [assistant_chat_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/assistant_chat_runtime.py).
54. Bounded `ops_guard + knowledge_librarian` governance loop in [docs/57-ops-guard-and-memory-sync.md](/Users/palba/Projects/Personal/Clawdio/docs/57-ops-guard-and-memory-sync.md), [memory_sync_runner.py](/Users/palba/Projects/Personal/Clawdio/scripts/memory_sync_runner.py), [ops_guard_review.py](/Users/palba/Projects/Personal/Clawdio/scripts/ops_guard_review.py), [memory/SHARED_DIRECTIVES.md](/Users/palba/Projects/Personal/Clawdio/memory/SHARED_DIRECTIVES.md), and [memory/SHARED_FINDINGS.md](/Users/palba/Projects/Personal/Clawdio/memory/SHARED_FINDINGS.md).
55. Fitness Coach runtime in [docs/58-fitness-runtime.md](/Users/palba/Projects/Personal/Clawdio/docs/58-fitness-runtime.md) and [fitness_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/fitness_runtime.py), with Telegram and dashboard control surfaces backed by SQLite and markdown logs plus a conversational coaching layer for non-logging questions.
56. AIToolsDB local knowledge-source scaffolding in [docs/59-aitoolsdb-knowledge-source.md](/Users/palba/Projects/Personal/Clawdio/docs/59-aitoolsdb-knowledge-source.md), [knowledge_sources.yaml](/Users/palba/Projects/Personal/Clawdio/config/knowledge_sources.yaml), [knowledge_source_search.py](/Users/palba/Projects/Personal/Clawdio/scripts/knowledge_source_search.py), and [ai_tools_digest.py](/Users/palba/Projects/Personal/Clawdio/scripts/ai_tools_digest.py).
57. ResearchFlow researcher orchestration in [docs/60-researchflow-orchestration.md](/Users/palba/Projects/Personal/Clawdio/docs/60-researchflow-orchestration.md), [research_flow.yaml](/Users/palba/Projects/Personal/Clawdio/config/research_flow.yaml), and [research_flow_runtime.py](/Users/palba/Projects/Personal/Clawdio/scripts/research_flow_runtime.py), wrapping the daily job-search digest and AIToolsDB AI-tools digest under one researcher-owned flow.

## Suggested starting sequence

1. Review [docs/00-recovered-assets.md](/Users/palba/Projects/Personal/Clawdio/docs/00-recovered-assets.md).
2. Review VPS salvage triage in [docs/10-vps-salvage-triage.md](/Users/palba/Projects/Personal/Clawdio/docs/10-vps-salvage-triage.md) and promoted assets in [docs/17-promoted-vps-assets.md](/Users/palba/Projects/Personal/Clawdio/docs/17-promoted-vps-assets.md).
3. Pick integration/memory/add-on profiles and fill required keys:
4. `python3 scripts/check_env_requirements.py`
5. `python3 scripts/check_env_requirements.py --strict --addons-profile addons_off`
6. Review provider bundle and n8n contracts:
7. [docs/23-provider-bundles-checklist.md](/Users/palba/Projects/Personal/Clawdio/docs/23-provider-bundles-checklist.md)
8. [docs/24-n8n-workflow-contract-pack.md](/Users/palba/Projects/Personal/Clawdio/docs/24-n8n-workflow-contract-pack.md)
9. Run local gates:
10. `python3 scripts/validate_configs.py --config-dir config`
11. `python3 scripts/scan_secrets.py`
12. `python3 -m unittest discover -s tests -p 'test_*.py' -v`
13. Configure and test hybrid memory:
14. [docs/29-memory-hybrid-124-runbook.md](/Users/palba/Projects/Personal/Clawdio/docs/29-memory-hybrid-124-runbook.md)
15. `python3 scripts/memory_index_sync.py --workspace /path/to/workspace --dry-run`
16. Set dashboard auth token before starting the dashboard: `export OPENCLAW_DASHBOARD_TOKEN='<strong-random-token>'`
17. Start the local dashboard control plane (optional): `python3 dashboard/server.py --host 127.0.0.1 --port 18789`
18. Smoke-test the Telegram adapter locally: `python3 scripts/telegram_adapter.py --env-file secrets/openclaw.env --once --json`
19. Check which providers are really wired: `python3 scripts/provider_smoke_check.py --env-file secrets/openclaw.env --json`
20. For the current live command-center cutover, keep profiles at `bootstrap_command_center + hybrid_124`; fall back to `bootstrap_core + md_only` only for emergency cost-control or degraded-provider windows.
21. Run one bounded ops review before widening autonomy: `python3 scripts/ops_guard_review.py --mode daily_ops_review --json`
22. Run one memory sync so `knowledge_librarian` consolidates and indexes the shared directives/findings files: `python3 scripts/memory_sync_runner.py --env-file secrets/openclaw.env --json`
23. Execute the phase checklist in [docs/02-implementation-plan.md](/Users/palba/Projects/Personal/Clawdio/docs/02-implementation-plan.md).
24. Use [docs/40-runtime-status-matrix.md](/Users/palba/Projects/Personal/Clawdio/docs/40-runtime-status-matrix.md) and [docs/41-operationalization-priorities.md](/Users/palba/Projects/Personal/Clawdio/docs/41-operationalization-priorities.md) before adding new modules.

## Important constraint

For unattended server automation, you normally need API-accessible models/keys.
Use ChatGPT Plus primarily for supervised heavy tasks via CLI sessions, and reserve API quota for autonomous tasks.
