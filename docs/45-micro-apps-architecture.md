# Micro-Apps Architecture (Agent Reads/Writes, Apps Own State)

Last updated: 2026-03-07

## Core idea

The agent should not be the source of truth for recurring operational domains.

For domains that are:

1. repeatedly queried
2. repeatedly updated
3. naturally structured
4. review-oriented over time

use a small app with explicit state instead of storing everything in memory markdown.

## Right split

### Memory should hold

1. stable preferences
2. durable constraints
3. decisions
4. summaries
5. relationship context

### Apps should hold

1. tasks
2. reminders
3. fitness logs and active program state
4. braindump / idea parking lots
5. calendar candidates and event state
6. inbox-processing state

## Why this is better

1. Lower token usage
2. Better auditability
3. Cleaner promotion paths between systems
4. Easier dashboards
5. Less context pollution in agent sessions

## Recommended app pattern

Each app should have the same shape:

1. SQLite source of truth
2. optional markdown export or summary
3. small deterministic CLI or service API
4. dashboard-readable JSON snapshot
5. explicit promotion paths to other apps

## Proposed app family

### 1. Braindump app

Purpose:

1. capture low-friction thoughts fast
2. review them later by category or cadence
3. promote only selected items into tasks, calendar, gifts, research, or project queues

### 2. Task app

Purpose:

1. commitments
2. due dates
3. progress
4. execution queue

### 3. Fitness app

Purpose:

1. active workout program
2. session logs
3. progression state
4. review summaries

### 4. Calendar app / candidate layer

Purpose:

1. actual events
2. proposed events
3. pending approvals
4. scheduling review surface

### 5. Inbox ops app

Purpose:

1. email ingestion state
2. message classifications
3. promoted candidates
4. manual review queue

## Standard lifecycle pattern

For all apps, use a similar state model:

1. `capture`
2. `triage`
3. `review`
4. `promote`
5. `archive`

This makes cross-app behavior predictable.

## Promotion rules

The most useful part of this design is controlled promotion:

1. braindump -> task
2. braindump -> calendar candidate
3. braindump -> gift idea list
4. inbox -> task
5. inbox -> calendar candidate
6. fitness summary -> memory

## Rule for keeping memory clean

Do not store raw operational data in memory if it belongs to an app.

Examples:

1. raw workout set logs: app state
2. raw inbox decisions: app state
3. every passing idea: app state
4. durable training constraints: memory
5. durable life preferences: memory

## Recommendation now

Treat these as first-class local apps next:

1. braindump
2. personal tasks
3. fitness runtime

The agent should read and write them. It should not improvise their storage format in chat.
