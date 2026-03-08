# Braindump App Plan

Last updated: 2026-03-07

## Goal

Create a zero-friction capture app for short items that are not yet tasks.

Examples:

1. topic to research later
2. tool to test
3. gift idea for wife
4. thing daughter might want
5. purchase candidate
6. idea for a workflow or project

## What this is not

This is not the task manager.

A task means:

1. commitment
2. owner
3. execution intent
4. maybe a due date

A braindump item means:

1. remember this exists
2. check it later
3. maybe promote it later

## Recommended capture model

Minimal required fields:

1. `short_text`
2. `category`

Optional but useful:

1. `tags`
2. `review_bucket`
3. `notes`

## Recommended categories

Start with a small set:

1. `research_topic`
2. `tool_to_test`
3. `gift_idea_wife`
4. `kid_idea`
5. `purchase_candidate`
6. `project_idea`
7. `content_idea`
8. `personal_note`
9. `someday_maybe`

Allow custom categories later, but do not start with too many.

## Recommended statuses

1. `inbox`
2. `parked`
3. `reviewing`
4. `promoted`
5. `archived`

## Recommended review buckets

1. `daily`
2. `weekly`
3. `monthly`
4. `seasonal`
5. `manual_only`

Default mapping suggestion:

1. `gift_idea_wife` -> `weekly`
2. `kid_idea` -> `weekly`
3. `tool_to_test` -> `weekly`
4. `research_topic` -> `weekly`
5. `purchase_candidate` -> `monthly`
6. `project_idea` -> `weekly`
7. `someday_maybe` -> `monthly`

## Recommended commands

Capture:

1. `dump gift_idea_wife perfume note`
2. `dump tool_to_test agentmail`
3. `dump kid_idea lego set`
4. `dump research_topic local llm calendar sync`

Review:

1. `review braindump weekly`
2. `review braindump gifts`
3. `review braindump tools`
4. `show braindump category research_topic`

Promote:

1. `promote braindump <id> to task`
2. `promote braindump <id> to calendar`
3. `promote braindump <id> to project`
4. `archive braindump <id>`

## Best storage pattern

Use SQLite as the source of truth.

Why:

1. short structured records
2. easy filtering by category/status/review date
3. easy dashboard rendering
4. easy promotion into tasks/calendar later

Schema:

1. [contracts/braindump/sqlite_schema.sql](/Users/palba/Projects/Clawdio/contracts/braindump/sqlite_schema.sql)

## Best review behavior

This app becomes useful only if review is built in.

Recommended review loop:

1. no reminder on every capture
2. one scheduled review block per bucket
3. review screen shows items grouped by category
4. each item offers:
   - keep parked
   - promote to task
   - promote to calendar
   - archive

## How it fits with other apps

1. braindump captures uncertain or low-commitment items
2. task app handles committed next actions
3. calendar app handles actual scheduled events
4. fitness app handles workout-specific operational state
5. memory stores summaries and stable preferences, not raw braindump items

## Strong recommendation

Yes: this should be a real app.

It is a better fit than:

1. scattered markdown notes
2. stuffing ideas into `MEMORY.md`
3. pretending every idea is a task

## Best implementation order

1. build braindump SQLite runtime
2. add simple add/review/promote CLI
3. add dashboard card and review view
4. connect promotion to task app and calendar candidates

## Current runtime

The local runtime now exists in:

1. [braindump_app.py](/Users/palba/Projects/Clawdio/scripts/braindump_app.py)

Current commands:

1. `python3 scripts/braindump_app.py add gift_idea_wife perfume sampler`
2. `python3 scripts/braindump_app.py capture "bd gift perfume sampler #birthday @monthly"`
3. `python3 scripts/braindump_app.py review --json`
4. `python3 scripts/braindump_app.py park --id <item_id> --review-bucket monthly`
5. `python3 scripts/braindump_app.py promote --id <item_id> --to task`
6. `python3 scripts/braindump_app.py promote --id <item_id> --to calendar`
7. `python3 scripts/braindump_app.py archive --id <item_id>`
8. `python3 scripts/braindump_app.py snapshot --json`

Current outputs:

1. SQLite source of truth at `.memory/braindump.db` by default
2. dashboard snapshot at `data/braindump-snapshot.json`
3. task promotion into `data/dashboard-workspace.json`
4. calendar promotion into `data/calendar-candidates.json`
5. dashboard/web capture and action endpoints through `dashboard/server.py`
6. project promotion now lands in a project that also receives its own project space template inside the dashboard workspace

## Current category handling

Curated categories remain the default:

1. `research_topic`
2. `tool_to_test`
3. `gift_idea_wife`
4. `kid_idea`
5. `purchase_candidate`
6. `project_idea`
7. `content_idea`
8. `personal_note`
9. `someday_maybe`

Aliases are supported for faster capture:

1. `gift` -> `gift_idea_wife`
2. `kid` or `daughter` -> `kid_idea`
3. `tool` -> `tool_to_test`
4. `research` -> `research_topic`
5. `project` -> `project_idea`
6. `purchase` or `buy` -> `purchase_candidate`

Custom categories are also allowed and default to `weekly` review unless you override the bucket.

Current gap:

1. There is still no live Telegram or Slack adapter; future channel handling should call the same capture path instead of inventing a new one.
