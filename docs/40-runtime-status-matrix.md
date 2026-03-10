# Runtime Status Matrix

Last updated: 2026-03-09

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
| Telegram channel adapter | done | done | done | partial | Thin long-polling transport now exists and routes reminders, braindump, project-space capture, calendar reads, and simple task commands into the existing runtimes. | Prove the adapter against the live bot token on the VPS and keep the allowed-chat boundary strict. |
| Reminder engine | done | done | done | partial | The state machine now has a real live runner path through the Telegram adapter, including due delivery, one follow-up, and reply handling. | Validate the live VPS reminder file path and prove the flow end to end with the real bot. |
| Google Calendar integration | done | done | done | partial | Canonical calendar runtime exists, is credentialed, and is part of the live command-center profile, but still needs a timer-backed freshness loop and more operational visibility. | Add a VPS timer for snapshot refresh and show last successful calendar sync in the dashboard. |
| Personal task manager integration | done | done | done | partial | Todoist-first runtime now exists with snapshot/create/complete/defer flows and dashboard visibility. | Activate against live Todoist, then decide whether reminder/calendar linkage should stay local or become provider-aware. |
| Hybrid memory (`1+2+4`) | done | done | done | partial | Hybrid memory is now the active default, has explicit sync status, and is used by the conversational agent runtimes with bounded retrieval. | Enable the VPS timer, review actual embedding spend, and tune retrieval thresholds per agent. |
| Multi-agent conversational runtime | done | done | done | partial | `assistant`, `researcher`, and `builder` now have bounded chat runtimes with checkpoints, selective memory, and explicit space routing, while `fitness_coach` now has a real deterministic specialist runtime. | Add a visible session registry and decide whether `fitness_coach` should stay structured or gain bounded conversational review mode. |
| Ops-guard review loop | done | done | done | partial | Daily and weekly bounded reviews now have runtime scripts, dashboard status, and report outputs. | Enable the review timers on the VPS and use the reports to drive actual cleanup decisions. |
| Transcript ingest / YouTube intake | done | partial | none | none | You have runbooks and prior recovery work, but not a stable ingest pipeline inside this repo yet. | Pick one deterministic URL-to-transcript ingestion path and lock it. |
| Integrations pack (Gmail, Drive, GitHub, tasks, n8n) | done | partial | partial | partial | Gmail inbox processing and Drive shared-root bootstrap now have runnable local/runtime scripts and tests; the broader pack is still staged. | Activate Gmail + Drive against real accounts, then add one task provider. |
| Telemetry / model usage reporting | done | partial | partial | none | Reporting schema exists, but this is not yet the source of truth for operational cost decisions. | Capture real model events and display them in the dashboard. |
| Fitness agent | done | done | done | partial | SQLite-backed `today/start/log/finish` runtime now exists, writes markdown summaries, and is exposed through Telegram and the dashboard. | Deploy the runtime live on the VPS and decide whether to add progression review chat on top of the deterministic core. |
| Braindump app / micro-apps pattern | done | done | done | partial | Braindump now has a local SQLite runtime, dashboard capture/actions, promotion paths, and Telegram capture reuse. | Add live-channel review flows and keep category drift under control. |
| Agent markdown baseline | done | done | done | partial | Good baseline pack and validation story. | Decide exactly where this sits in the live onboarding flow. |
| VPS bootstrap / ops recovery | done | partial | none | partial | Recovery docs are strong; automation is still mostly dry-run and operator-driven. | Promote only the minimal scripts you will actually run on the VPS. |

## Overall Read

1. The repo is strong in `Design`.
2. The strongest fully-realized areas are:
   - config/readiness validation
   - model routing policy
   - dashboard auth/approval hardening
3. The weakest area is now the gap between planning and live runtime in:
   - deploy hardening
   - transcript ingest
   - fitness
4. Current bottleneck is no longer core design.
5. Current bottleneck is operationalizing the new agent runtime loops consistently on the VPS.

## Rule For Future Work

Do not consider a module "real" unless all four are true:

1. config exists
2. runtime path exists
3. automated check or test exists
4. operator-facing activation/runbook exists
