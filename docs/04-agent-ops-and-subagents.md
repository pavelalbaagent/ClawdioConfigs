# Agent Operations and Sub-Agent Rules

## Two task systems by design

1. Personal task system: your tasks, reminders, and follow-ups.
2. Agent task system: work packages delegated to OpenClaw workers.

## Recommended split

1. Personal tasks use fast capture via Telegram or a quick web form.
2. Personal reminders are sent via Telegram plus daily email digest.
3. Agent tasks use a structured queue with status (`new`, `planned`, `running`, `blocked`, `done`).
4. Every agent task must have owner, deadline, and expected output format.

## Core agent roles

1. `coordinator`: triage, routing, approvals, and synthesis.
2. `researcher`: external research and context building.
3. `builder`: implementation and integration work.
4. `ops_guard`: monitoring, retries, health checks, and incident response.

## Sub-agent spawn rules

1. Spawn sub-agent only when task exceeds 30 minutes of focused work.
2. Spawn when task requires isolated context or specialized toolchain.
3. Do not spawn for quick edits, small summaries, or single-call operations.
4. Every sub-agent must include objective, allowed tools, max runtime, output schema, and stop conditions.
5. Coding, debugging, and deep investigation should default to sub-agent execution.
6. Before spawning, announce in one line which sub-agent role and model lane will be used.
7. On failure, report failure reason and fallback path in one line.

## Dedicated sub-agents worth keeping always-on

1. `inbox_triage_agent`: classifies incoming requests.
2. `calendar_reminder_agent`: reminders and scheduling.
3. `ops_monitor_agent`: uptime checks, alerts, and quota alarms.

## Approval gates

1. Human approval is required for model escalation to heavy lane.
2. Human approval is required for external posting or account actions.
3. Human approval is required for credential scope changes.
4. Human approval is required for destructive operations.

## Delegation Message Format

1. Spawn notice: `Delegating to <role> on <lane> for <objective>.`
2. Completion notice: `Sub-agent completed <objective>. Key result: <result>.`
3. Failure notice: `Sub-agent failed <objective>. Cause: <cause>. Next: <fallback>.`

## Communication policy

1. Keep WhatsApp optional, not primary.
2. Primary interaction channel should support command clarity and searchable history.
3. Use concise command grammar such as `add-task: ...`.
4. Use command `run-agent-task: ...` for delegated agent work.
5. Keep short status commands such as `status`, `budget`, and `approve <task-id>`.
