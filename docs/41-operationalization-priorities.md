# Operationalization Priorities

Last updated: 2026-03-06

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

### 2. Google Calendar Integration

Why this is second:

1. Calendar mess is a real day-to-day pain point.
2. A single canonical calendar gives OpenClaw one clean scheduling target.
3. It materially improves the usefulness of reminders, planning, and future task scheduling.

What "done" means:

1. read upcoming events from one Google calendar
2. create events with approval
3. update events with approval
4. expose next events in the dashboard
5. keep Outlook out of the MVP write path

Recommended implementation scope:

1. support one canonical Google calendar only
2. avoid Outlook write support
3. keep work-calendar mirroring as a later optional layer

### 3. Personal Task Manager Integration

Why this is third:

1. To-dos are one of your highest-friction daily problems.
2. Tasks combine naturally with reminders and calendar planning.
3. It can stay low-risk if you pick one provider and keep writes approval-aware.

What "done" means:

1. list personal tasks
2. create tasks
3. complete tasks
4. defer/reschedule tasks
5. expose them cleanly in the dashboard and main channel

Recommended implementation scope:

1. pick one provider only
2. avoid multi-provider abstraction complexity in the first live cut
3. keep task capture and reminder linkage explicit

### 4. Dashboard Operations Layer

Why this is fourth:

1. The dashboard already exists and is now safer.
2. It becomes more useful once reminders, calendar, tasks, and telemetry surface there.
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

## Modules To Delay

### Broad integrations pack

Delay because:

1. it is credential-heavy
2. it expands failure surface quickly
3. it is easy to overbuild before the core loops are stable

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
2. finish Google Calendar integration end to end
3. finish personal task manager integration end to end
4. turn the dashboard into the operator cockpit for those systems
