# Communication Structure (Platform Agnostic)

Last updated: 2026-03-02

## Purpose

Keep one communication model that works the same way across Slack, Telegram, Discord, WhatsApp, email inboxes, or a dashboard.

## Canonical Spaces

1. `main`: command and coordination stream.
2. `tasks`: active execution queue (owner + next action).
3. `notes`: durable decisions, references, and summaries.
4. `projects`: committed workstreams.
5. `research`: exploration and findings before commitment.
6. `tools`: experiments and tool evaluations.
7. `config`: environment, security, and integration changes.
8. `news`: digests, watchlist summaries, and intelligence briefs.
9. `alerts`: incidents, failures, and quota warnings.

## Project Space Rule

1. Every ongoing project gets its own derived project space, for example `projects/calendar-review`.
2. A project space is not just a tag. It is a separate working context with its own checkpoints and summaries.
3. Promoting a task into a project should create that project space automatically.
4. Project spaces inherit the `projects` visibility lane, but keep their own context boundary.

## Platform Mapping

1. Slack/Discord: map each canonical space to a channel.
2. Telegram/WhatsApp: map spaces by prefix tags, for example `[tasks]`, `[news]`, or `[project:calendar-review]`.
3. Email: map spaces by labels or subject prefixes.
4. Web dashboard: map spaces by tabs/lanes.

## Workflow Funnel

`tools` + `research` -> evaluate -> `projects` -> execution in `tasks` -> durable outcomes in `notes`

## Promotion Criteria

1. Clear practical value.
2. A realistic first 60-minute action exists.
3. Fits current priorities and budget.

## Agent Interaction Rules

1. Agent default response space is `main` unless command explicitly targets another space.
2. High-impact actions require explicit approval in `main` or `alerts`.
3. Daily digest goes to `news`.
4. Incident and health events go to `alerts`.

## Current Project Routing Syntax

1. Use `[project:<slug>]` at the start of a message to target a specific project space.
2. Example: `[project:calendar-review] review tomorrow's conflicts`.
3. The transport layer should pass the cleaned body into the relevant app or workflow after routing resolves the project space.

## Evolution Rule

Only split a space when one of these is true:

1. Context mixing causes repeated mistakes.
2. Volume makes review difficult for 7+ days.
3. Different audiences need different visibility.

Project spaces are the main planned exception:

1. once work becomes a real ongoing project, split it immediately
2. do not wait for the generic `projects` lane to become noisy first
