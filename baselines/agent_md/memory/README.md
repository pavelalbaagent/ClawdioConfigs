# memory/README.md

Memory lane for structured, low-token continuity.

Core files:

1. `PROFILE.md`: stable owner profile and durable preferences.
2. `PROJECTS.md`: active/paused projects and priority order.
3. `DECISIONS.md`: durable decisions and revisit triggers.
4. `INTEGRATIONS.md`: integration state and known failure notes.
5. `YYYY-MM-DD.md`: short-lived daily notes.

Rules:

1. Keep entries factual and concise.
2. Do not store raw secrets.
3. Promote durable lessons to `../MEMORY.md` and structured files above.
4. Archive or compact daily entries older than 30 days.
5. Re-index this folder after major updates:
6. `python3 scripts/memory_index_sync.py --workspace <agent_workspace_path>`
