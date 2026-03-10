# Telegram Adapter Runtime

Last updated: 2026-03-09

## Goal

Provide the first real human channel for the rebuilt stack without reintroducing WhatsApp dependency.

The adapter is intentionally thin, but it is no longer command-only:

1. Telegram long polling only
2. one allowed private chat
3. route into existing runtimes and backend handlers
4. no chat-history-as-memory behavior
5. degrade cleanly when staged providers such as Google Calendar or Todoist are still disabled
6. keep a small persistent conversation focus so Pavel can stay in one specialist mode without prefixes on every message

## Runtime

Main file:

1. [telegram_adapter.py](/Users/palba/Projects/Clawdio/scripts/telegram_adapter.py)

Current responsibilities:

1. poll Telegram updates
2. enforce `TELEGRAM_ALLOWED_CHAT_ID`
3. create reminders from supported reminder grammar
4. send due reminders and one follow-up from the same long-poll loop
5. accept `done` and `defer until <time>`
6. capture braindump items
7. create simple personal tasks
8. read calendar today / next
9. convert `[project:slug] ...` text into local project tasks
10. route specialist-prefixed requests into agent-owned spaces
11. hand `assistant`, `researcher`, and `builder` requests to conversational runtimes
12. execute the deterministic `fitness_coach` runtime directly
13. fall back to structured capture for non-conversational specialists that still have no live runtime
14. persist a current Telegram focus such as `researcher`, `builder`, or `fitness_coach`
15. infer common natural-language requests for reminders, tasks, calendar, braindump, and workout logging before sending text to chat runtimes

## Supported Interaction Model

Recommended default:

1. use one main private Telegram chat
2. talk naturally for reminders, tasks, calendar, and assistant questions
3. switch focus when you want a specialist to own the next part of the conversation
4. keep explicit prefixes only as an override, not as the main interface

Natural phrases now supported:

1. `what reminders do i have?`
2. `add review syllabus to my tasks for tomorrow 10am`
3. `what's on my calendar tomorrow?`
4. `note this: test AgentMail later`
5. `switch to research mode`
6. `switch to coding mode`
7. `switch back`
8. `what mode are we in?`
9. `what's my workout today?`
10. `I'm starting my workout`
11. `I did hammer curls 12 reps with 10kg each`

Explicit grammar that still works:

1. `remind me <message> at <time>`
2. `remind me <message> in <duration>`
3. `done`
4. `defer until <time>`
5. `bd <category> <text> [#tag] [@review_bucket]`
6. `add-task <title> :: <optional due string>`
7. `tasks`
8. `calendar today`
9. `calendar next`
10. `status`
11. `[project:slug] <text>`
12. `assistant: <text>`
13. `reminders: <text>`
14. `research: <text>`
15. `fitness: <text>`
16. `coding: <text>`
17. `ops: <text>`
18. `workout today`
19. `start workout`
20. `log ...`
21. `finish workout`
22. `set barbell empty <kg>kg`

## Specialist Routing

Current runtime contract:

1. no prefix -> default `assistant` front door, unless a sticky focus is active or a clear natural specialist intent is detected
2. `research: ...` -> `researcher` in `research`
3. `fitness: ...` -> `fitness_coach` in `fitness`
4. `coding: ...` -> `builder` in `coding`
5. `ops: ...` -> `ops_guard` in `ops`
6. `reminders: ...`, `calendar: ...`, `tasks: ...`, `braindump: ...` stay under `assistant` but route into narrower spaces
7. project hints still work, and a sticky specialist focus can apply on top of a project space

Current behavior:

1. supported deterministic commands still execute directly
2. `assistant`, `researcher`, and `builder` prefixes open bounded conversational runtimes
3. `fitness` executes its own deterministic workout runtime
4. `ops` remains a structured route for now
5. project hints still work and can be combined with specialist prefixes, for example:
   - `coding: [project:calendar-cleanup] tighten dashboard route view`
6. sticky focus survives across turns in Telegram until Pavel switches back or selects another agent

## State Files

1. Telegram adapter offset/state:
   - local default: `data/telegram-adapter-state.json`
   - VPS target: `/var/lib/openclaw/telegram-adapter-state.json`
   - includes the current `conversation_focus`
2. Reminder state:
   - config-driven via [reminders.yaml](/Users/palba/Projects/Clawdio/config/reminders.yaml)
   - VPS target: `/var/lib/openclaw/reminders-state.json`
3. Agent runtime activity:
   - local default: `data/agent-runtime-state.json`
   - VPS target: `/var/lib/openclaw/agent-runtime-state.json`
4. Agent conversational state:
   - local defaults: `data/assistant-chat-state.json`, `data/researcher-chat-state.json`, `data/builder-chat-state.json`
   - VPS target directory: `/var/lib/openclaw/`

The adapter keeps a small mapping from outgoing reminder message ids to reminder ids so Telegram replies can resolve the correct reminder without forcing manual ids.

## Local Run

```bash
python3 scripts/telegram_adapter.py --env-file secrets/openclaw.env --once --json
```

```bash
python3 scripts/telegram_adapter.py --env-file secrets/openclaw.env
```

## VPS Unit

User-mode systemd unit:

1. [openclaw-telegram-adapter.service](/Users/palba/Projects/Clawdio/ops/systemd/openclaw-telegram-adapter.service)

Planned activation:

```bash
mkdir -p ~/.config/systemd/user
cp /opt/clawdio/ops/systemd/openclaw-telegram-adapter.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openclaw-telegram-adapter.service
systemctl --user status openclaw-telegram-adapter.service --no-pager
```

## Current Limits

1. no Telegram webhook mode
2. no group/topic mode
3. calendar support is read-first in chat; candidate editing stays in dashboard
4. if Calendar or personal-task providers are not configured yet, the adapter returns a clear unavailable message instead of failing
5. personal-task support is simple create/list, not the full dashboard surface
6. reminder/task/calendar linkage is still separate work
7. `fitness_coach` is runtime-backed and supports common natural workout phrases, but it is still not a freeform chat coach
8. `ops_guard` is still not conversational
9. sticky focus is chat-local, not yet split across Telegram topics or multiple human channels

## Why this shape

1. keeps Telegram as transport only
2. keeps business logic in the existing runtimes
3. gives reminders a real live runner path without inventing a second scheduler stack
4. removes WhatsApp as an MVP dependency
