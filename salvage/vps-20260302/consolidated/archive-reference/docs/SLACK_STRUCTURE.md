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

## Platform Mapping

1. Slack/Discord: map each canonical space to a channel.
2. Telegram/WhatsApp: map spaces by prefix tags, for example `[tasks]`, `[news]`.
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

## Evolution Rule

Only split a space when one of these is true:

1. Context mixing causes repeated mistakes.
2. Volume makes review difficult for 7+ days.
3. Different audiences need different visibility.
