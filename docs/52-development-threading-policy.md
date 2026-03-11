# Development Threading Policy

Last updated: 2026-03-09

## Core rule

Threads are for active reasoning.

The repo is the source of truth.

Do not treat one long chat thread as memory.

## Recommended thread structure

1. `Orchestration thread`
   - use for priorities
   - architecture decisions
   - deployment/cutover decisions
   - cross-module tradeoffs
   - review of overall system state
2. `Feature thread`
   - one bounded module or feature at a time
   - examples: calendar, reminders, Telegram UX, provider routing, dashboard
3. `Bug/incident thread`
   - one broken runtime or one incident
   - examples: gateway conflict, reminder failure, auth regression
4. `Research/brainstorm thread`
   - only for exploring new ideas before implementation

## When to start a new thread

Start a new thread if any of these are true:

1. the goal changes to a different module
2. the main files/toolchain change
3. the work will likely touch a different provider or integration boundary
4. the current thread would require a long recap before useful work can continue
5. you want a clean milestone boundary

## When to stay in the same thread

Stay in the same thread if:

1. it is the same module and same milestone
2. the change is a small follow-up or fix to very recent work
3. the same files and acceptance criteria still apply

## Recommended usage for this project

1. Keep one persistent `orchestration` thread for:
   - roadmap
   - activation decisions
   - profile changes
   - VPS rollout
   - cross-module policy
2. Use separate feature threads for:
   - `telegram`
   - `reminders`
   - `calendar`
   - `tasks`
   - `gmail-drive`
   - `dashboard`
   - `model-routing`
   - `fitness`
3. Close or stop using a feature thread once its milestone is shipped and summarized back into the repo.

## Project-space alignment

This should match the project-space policy in [docs/47-project-spaces-and-session-agent-strategy.md](/Users/palba/Projects/Personal/Clawdio/docs/47-project-spaces-and-session-agent-strategy.md):

1. new ongoing project -> new project space
2. project space -> usually a separate session/thread
3. runtime agents stay fixed; route project work to the right existing surface

## Practical rule of thumb

1. one thread per active workstream
2. one workstream per milestone
3. summarize back to repo files when the milestone ends

## Suggested kickoff template

Use:

1. [docs/templates/feature-thread-kickoff.md](/Users/palba/Projects/Personal/Clawdio/docs/templates/feature-thread-kickoff.md)
2. [docs/templates/thread-starters.md](/Users/palba/Projects/Personal/Clawdio/docs/templates/thread-starters.md)
