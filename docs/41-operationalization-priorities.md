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

### 1. Multi-Agent Runtime VPS Hardening

Why this is first:

1. Conversational `assistant`, `researcher`, and `builder` now exist, along with memory sync and ops reviews.
2. The next highest-value step is making those loops operational and visible on the VPS.
3. This is where timer, path, and state-drift issues will show up.
4. It prevents the new command-center surface from degrading into another half-live stack.

What "done" means:

1. Telegram adapter and dashboard run cleanly on the VPS
2. memory sync timer runs successfully
3. ops-guard daily review timer runs successfully
4. agent runtime state updates live from Telegram traffic
5. one researcher chat and one builder chat turn succeed on the VPS

Recommended implementation scope:

1. keep the current live profile at `bootstrap_command_center`
2. keep one private Telegram chat only
3. use timers and dashboard state before adding more autonomy

### 2. Deterministic Reminder/Task/Calendar Linkage

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

### 3. Dashboard Session And Governance Layer

Why this is third:

1. The dashboard now exposes agent registry, provider health, and runtime state, but it still lacks a real session/governance cockpit.
2. That matters more now that multiple conversational roles exist.
3. It gives you one operator view instead of scattered state files and chat history.

What "done" means:

1. show active agent sessions and checkpoints
2. show pending reminders and linked tasks
3. show upcoming calendar items
4. show latest ops-guard review and memory-sync status
5. show recent model usage by lane

Recommended implementation scope:

1. use local JSON/SQLite-backed views first
2. avoid adding broad remote writes from the dashboard until read-side visibility is strong

### 4. Fitness Coach Runtime

Status:

1. Completed on 2026-03-09.

Why this is fourth:

1. The fitness domain already has the cleanest structured-state design in the repo.
2. It is the best next specialist to turn from routed capture into a real agent runtime.
3. It will force good decisions about session boundaries and structured logging.

What "done" means:

1. `fitness:` opens a real specialist runtime instead of task capture
2. today/start/log/finish flows work against the fitness state store
3. workout progression is visible without raw chat replay
4. dashboard shows fitness runtime state cleanly
5. fitness logs stay app-backed, not memory-backed

Recommended implementation scope:

1. keep the first version tightly scoped to workout guidance and logging
2. do not expand into nutrition or reminders yet
3. keep progression deterministic and SQLite-backed

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

1. harden the multi-agent runtime loops on the VPS
2. link reminders, tasks, and calendar deterministically
3. improve the dashboard as the session/governance cockpit
4. build `fitness_coach` as the next real specialist runtime
