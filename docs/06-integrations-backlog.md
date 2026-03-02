# Integrations Backlog and Priority

Use this backlog together with [docs/20-integration-connection-structure.md](/Users/palba/Projects/Clawdio/docs/20-integration-connection-structure.md) and [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml).

## Tier 1: Baseline (lean_manual)

1. Gmail read/send with approval gate.
2. Drive root-folder file operations.
3. GitHub read/write (approval-gated writes).
4. Personal task manager (single provider selected).
5. Agent task manager (single provider selected).
6. n8n webhook bridge.

## Tier 2: Productivity upgrades

1. Calendar sync for planning and reminders.
2. Better search provider for web browsing.
3. Web dashboard for approvals and task visibility.

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
