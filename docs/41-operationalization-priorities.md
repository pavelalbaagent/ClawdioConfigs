# Operationalization Priorities

Last updated: 2026-03-09

## Selection Rule

Prioritize modules that satisfy all of the following:

1. high day-to-day usefulness
2. bounded implementation scope
3. clear cost control
4. minimal credential risk
5. strong leverage on the rest of the system

## Top 4 Next Modules

### 1. VPS MVP Deployment Pass

Why this is first:

1. The channel adapter and reminder loop now exist locally.
2. The next highest-value step is proving the real go-live path cleanly on the VPS.
3. This is where path mismatches, env mistakes, and service wiring issues usually appear.
4. It prevents another “partially alive but practically dead” runtime like the old WhatsApp-centric box.

What "done" means:

1. Telegram adapter runs as a user service
2. dashboard is reachable through the intended tunnel path
3. reminder state file is shared correctly across runtime and dashboard
4. Telegram, dashboard auth, and reminder state validate on the VPS
5. one real end-to-end smoke test passes

Recommended implementation scope:

1. keep the first live profile at `bootstrap_core`
2. do not add extra providers during the deploy pass
3. prove one private Telegram chat only

### 2. Reminder/Task/Calendar Linkage

Why this is second:

1. The individual pieces now exist, but daily usefulness depends on deterministic linkage.
2. Once deployed, this is the next biggest leverage increase.
3. It will make the system feel coherent instead of like separate micro-tools.

What "done" means:

1. a task can create a reminder
2. a task can promote to calendar candidate
3. reminders can reference task ids cleanly
4. dashboard shows linked objects without ambiguity
5. model usage stays low because linkage remains deterministic

Recommended implementation scope:

1. do not invent a universal object graph
2. link by explicit ids and small metadata only
3. keep cross-module writes approval-aware where needed

### 3. Dashboard Operations Layer

Why this is third:

1. The dashboard already exists and now surfaces Gmail, Drive, braindump, Google Calendar, and personal tasks, but the first live cut should not wait on the staged providers.
2. It becomes materially better once live reminders and Telegram are on the VPS too.
3. It gives you one operator view instead of scattered files and chat history.

What "done" means:

1. show pending reminders
2. show upcoming calendar items
3. show active projects/tasks
4. show integration/module status
5. show recent model usage by lane

Recommended implementation scope:

1. use local JSON/SQLite-backed views first
2. avoid adding broad remote writes from the dashboard until read-side visibility is strong

### 4. Live Provider Activation Hardening

Why this is fourth:

1. Calendar, Gmail, Drive, and Todoist runtimes exist, but they still need real-account proof.
2. Provider bugs are easier to solve after the Telegram/reminder loop is live.
3. This keeps the migration disciplined instead of turning into a credentials scramble mid-deploy.

What "done" means:

1. Google Calendar snapshot works with the real account before switching the live profile from `bootstrap_core` to `bootstrap_minimal`
2. one personal task create/complete/defer cycle works against the live provider
3. Gmail batch processing runs once safely against the real inbox
4. Drive root verification works against the real shared folder
5. failures are visible in the dashboard or logs without guesswork

Recommended implementation scope:

1. activate only one provider per surface
2. prefer read-side or low-risk write-side proofs first
3. keep Gmail/Drive off until Telegram/reminders are stable if the timeline forces a cut

## Modules To Delay

### Broad integrations pack

Delay because:

1. it is credential-heavy
2. it expands failure surface quickly
3. it is easy to overbuild before the core loops are stable

### Personal task provider expansion

Delay because:

1. the Todoist-first runtime now exists
2. Google Tasks and Asana add provider complexity, not immediate leverage
3. linkage and channel routing now matter more than more provider coverage

### Transcript intake pipeline

Delay because:

1. it is useful, but it is not one of your top daily pain points
2. reminders, calendar, and tasks now have higher immediate leverage

### Fitness runtime

Delay because:

1. the plan is good, but it is not the highest leverage system module yet
2. it can be built cleanly later once reminder/session patterns are stable

### More add-on skills

Delay because:

1. you already have enough modular options
2. more add-ons now mostly increase complexity, not utility

## Suggested Sequence

1. deploy the Telegram + reminder MVP cleanly on the VPS
2. link reminders, tasks, and calendar deterministically
3. improve the dashboard as the operator cockpit
4. activate live providers one by one
