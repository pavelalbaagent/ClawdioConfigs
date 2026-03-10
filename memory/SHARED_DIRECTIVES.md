# Shared Directives

Maintained by `knowledge_librarian` from bounded `ops_guard` reviews.

## Active Directives

- [all_agents] Treat the repo as the source of truth; do not treat chat history as durable memory.
- [all_agents] Keep `ops_guard` as detector/reviewer and `knowledge_librarian` as consolidator; do not create a new visible agent for this loop.
- [all_agents] Do not silently rewrite agent structure, provider order, integrations, or other structural policy without explicit approval.

## Approval Boundaries

- Changing credentials requires approval.
- Changing provider priorities requires approval.
- Enabling integrations requires approval.
- Creating persistent agents requires approval.

## Promotion Notes

- Auto-promotion requires repeated safe directive candidates across review history.
- Approval-required candidates stay in the shared findings file until a human approves the change.
