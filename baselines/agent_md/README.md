# Agent Markdown Baseline Pack

This folder contains reusable baseline files for agent continuity and control.

Core files:

1. `SOUL.md`: identity and durable behavior contract.
2. `USER.md`: owner profile and preferences.
3. `MEMORY.md`: curated long-term memory.
4. `SESSION.md`: current-session checkpoint.
5. `TODO.md`: actionable tasks.
6. `HEARTBEAT.md`: periodic low-noise checks.
7. `memory/`: daily logs.

Use scripts:

1. `python3 scripts/bootstrap_agent_md.py --target <workspace>`
2. `python3 scripts/validate_agent_md.py --target <workspace>`
