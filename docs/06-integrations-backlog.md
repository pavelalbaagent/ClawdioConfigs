# Integrations Backlog and Priority

Last updated: 2026-03-07

Use this backlog together with [docs/20-integration-connection-structure.md](/Users/palba/Projects/Clawdio/docs/20-integration-connection-structure.md) and [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).

## Tier 1: Immediate next unlocks after MVP

These are the first integrations worth activating after the Telegram + dashboard + reminders + calendar loop is stable.

1. Gmail scheduled inbox processing with archive/trash/draft/task/calendar promotion logic.
2. Shared-root Google Drive workspace for human/agent collaboration.
3. Personal task manager (single provider selected).
4. Agent task manager (single provider selected).

## Tier 2: Productive expansion

1. GitHub read/write (approval-gated writes).
2. Better search provider for web browsing.
3. n8n webhook bridge.
4. Dashboard views for reminders, tasks, calendar, and inbox state.

## Tier 3: Optional/high-risk

1. LinkedIn integration (manual-review mode first).
2. Social publishing connectors.
3. Additional automation hubs beyond n8n.

## Integration acceptance criteria

1. Scope is documented and minimal.
2. Env/token requirements are tracked in `.env.example`.
3. Revocation procedure exists.
4. Logging and alerting are enabled.
5. Fallback behavior is defined.
6. Cost impact and default profile are documented.
