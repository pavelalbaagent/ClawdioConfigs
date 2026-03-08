# Operationalization Priorities

Last updated: 2026-03-08

## Selection Rule

Prioritize modules that satisfy all of the following:

1. high day-to-day usefulness
2. bounded implementation scope
3. clear cost control
4. minimal credential risk
5. strong leverage on the rest of the system

## Top 4 Next Modules

### 1. Reminder Service v2

Why this is first:

1. It already has the clearest postmortem and deterministic spec.
2. It directly improves your real daily use.
3. It is the cleanest example of the repo philosophy: deterministic first, model second.
4. It avoids wide integration scope if started with one message channel.

What "done" means:

1. inbound message creates reminder
2. scheduler fires on time
3. `done` clears it
4. `defer` shifts it by exactly one hour
5. no reply triggers exactly one follow-up one hour later
6. reminder state is visible in dashboard

Recommended implementation scope:

1. keep one primary chat channel only
2. keep provider abstraction at the event-contract layer
3. do not add smart natural-language parsing beyond the supported grammar yet

### 2. Dashboard Operations Layer

Why this is second:

1. The dashboard already exists and now surfaces Gmail, Drive, braindump, Google Calendar, and personal tasks.
2. It becomes materially better once reminders are fully operational too.
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

### 3. Telegram Channel Adapter

Why this is third:

1. Telegram is still the most realistic MVP human channel.
2. Multiple runtimes now exist locally and need one thin command surface.
3. It can stay lightweight if it routes into existing app/runtime handlers instead of owning business logic.

What "done" means:

1. one private chat receives commands and capture
2. route braindump, reminders, project-space text, and simple calendar/task requests
3. reuse existing backend/runtime paths instead of duplicating logic
4. keep long-polling only
5. keep WhatsApp out of the first live cut

Recommended implementation scope:

1. keep Telegram as a thin transport adapter
2. do not use Telegram channels as memory
3. route into app state and selective context, not raw chat history

### 4. Reminder/Task/Calendar Linkage

Why this is fourth:

1. The individual modules now exist, but they are still loosely connected.
2. This is where the system starts feeling coherent in daily use.
3. Linkage is higher leverage now than adding more providers.

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

1. finish Reminder Service v2 end to end
2. turn the dashboard into the operator cockpit for reminders, calendar, and tasks
3. add the Telegram adapter as a thin transport layer over those systems
4. link reminders, tasks, and calendar deterministically
