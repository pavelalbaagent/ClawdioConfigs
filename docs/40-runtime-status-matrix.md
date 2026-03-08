# Runtime Status Matrix

Last updated: 2026-03-07

## Status Legend

1. `Design`
   - `done`: policy/config/docs are coherent
   - `partial`: intent exists but is not yet tight enough to guide implementation cleanly
2. `Runtime`
   - `done`: runnable path exists for the main use case
   - `partial`: some scripts/UI/runtime pieces exist, but not a full operational slice
   - `none`: planning only
3. `Test`
   - `done`: meaningful automated coverage exists
   - `partial`: some coverage exists, but core behavior is still unguarded
   - `none`: no useful automated coverage
4. `Deploy`
   - `done`: ready to run in the intended environment with clear activation steps
   - `partial`: can be run locally or manually, but not yet locked down operationally
   - `none`: not deployment-ready

## Matrix

| Module | Design | Runtime | Test | Deploy | Current assessment | Next gate |
| --- | --- | --- | --- | --- | --- | --- |
| Config profiles and readiness checks | done | done | done | partial | Strong baseline for modular activation and secrets validation. | Use the same profile discipline for every new runtime module. |
| Dashboard control plane | done | partial | done | partial | Good local control surface with hardened auth and approval checks. | Add real operational widgets: jobs, failures, queue health, spend by lane. |
| Model routing and cost policy | done | done | done | partial | Routing policy is coherent and test-backed, but still needs live provider telemetry in normal use. | Feed real usage logs into routing review and dashboard. |
| Reminder engine | done | partial | done | partial | Specs and state machine are solid; the end-user flow is still not fully closed as a live service. | Build the real runner path from message intake to scheduled delivery and reply handling. |
| Google Calendar integration | done | none | none | none | Clear canonical direction now exists, but runtime/API implementation is not built yet. | Implement read upcoming events + create/update with approval against one canonical calendar. |
| Hybrid memory (`1+2+4`) | done | partial | partial | partial | Good architecture and helper scripts; missing stronger end-to-end use in agent flows. | Wire memory sync/search into one live workflow and validate costs. |
| Transcript ingest / YouTube intake | done | partial | none | none | You have runbooks and prior recovery work, but not a stable ingest pipeline inside this repo yet. | Pick one deterministic URL-to-transcript ingestion path and lock it. |
| Integrations pack (Gmail, Drive, GitHub, tasks, n8n) | done | partial | partial | partial | Gmail inbox processing and Drive shared-root bootstrap now have runnable local/runtime scripts and tests; the broader pack is still staged. | Activate Gmail + Drive against real accounts, then add one task provider. |
| Telemetry / model usage reporting | done | partial | partial | none | Reporting schema exists, but this is not yet the source of truth for operational cost decisions. | Capture real model events and display them in the dashboard. |
| Fitness agent | done | none | none | none | Canonicalized well, but still architecture and data contract only. | Build SQLite bootstrap + `today/start/log/finish` command path. |
| Braindump app / micro-apps pattern | done | done | done | partial | Braindump now has a local SQLite runtime, dashboard capture/actions, and promotion paths into task/calendar/project surfaces. | Reuse the same capture path from the live Telegram adapter instead of building separate channel logic. |
| Agent markdown baseline | done | done | done | partial | Good baseline pack and validation story. | Decide exactly where this sits in the live onboarding flow. |
| VPS bootstrap / ops recovery | done | partial | none | partial | Recovery docs are strong; automation is still mostly dry-run and operator-driven. | Promote only the minimal scripts you will actually run on the VPS. |

## Overall Read

1. The repo is strong in `Design`.
2. The strongest fully-realized areas are:
   - config/readiness validation
   - model routing policy
   - dashboard auth/approval hardening
3. The weakest area is the gap between planning and live runtime in:
   - calendar and integrations
   - transcript ingest
   - fitness
4. Current bottleneck is not architecture quality.
5. Current bottleneck is finishing a few operational slices end to end.

## Rule For Future Work

Do not consider a module "real" unless all four are true:

1. config exists
2. runtime path exists
3. automated check or test exists
4. operator-facing activation/runbook exists
