# Telegram Adapter Runtime

Last updated: 2026-03-09

## Goal

Provide the first real human channel for the rebuilt stack without reintroducing WhatsApp dependency.

The adapter is intentionally thin:

1. Telegram long polling only
2. one allowed private chat
3. route into existing runtimes and backend handlers
4. no chat-history-as-memory behavior
5. degrade cleanly when staged providers such as Google Calendar or Todoist are still disabled

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
10. route specialist-prefixed requests into agent-owned spaces and capture them as local tasks

## Supported Commands

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

## Specialist Routing

Current runtime contract:

1. no prefix -> default `assistant` front door
2. `research: ...` -> `researcher` in `research`
3. `fitness: ...` -> `fitness_coach` in `fitness`
4. `coding: ...` -> `builder` in `coding`
5. `ops: ...` -> `ops_guard` in `ops`
6. `reminders: ...`, `calendar: ...`, `tasks: ...`, `braindump: ...` stay under `assistant` but route into narrower spaces

Current behavior:

1. supported deterministic commands still execute directly
2. explicit specialist requests that are not yet implemented as live chat become routed local tasks
3. project hints still work and can be combined with specialist prefixes, for example:
   - `coding: [project:calendar-cleanup] tighten dashboard route view`

## State Files

1. Telegram adapter offset/state:
   - local default: `data/telegram-adapter-state.json`
   - VPS target: `/var/lib/openclaw/telegram-adapter-state.json`
2. Reminder state:
   - config-driven via [reminders.yaml](/Users/palba/Projects/Clawdio/config/reminders.yaml)
   - VPS target: `/var/lib/openclaw/reminders-state.json`
3. Agent runtime activity:
   - local default: `data/agent-runtime-state.json`
   - VPS target: `/var/lib/openclaw/agent-runtime-state.json`

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

## Why this shape

1. keeps Telegram as transport only
2. keeps business logic in the existing runtimes
3. gives reminders a real live runner path without inventing a second scheduler stack
4. removes WhatsApp as an MVP dependency
