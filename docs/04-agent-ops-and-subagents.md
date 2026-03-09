# Agent Operations and Sub-Agent Rules

## Two task systems by design

1. Personal task system: your tasks, reminders, and follow-ups.
2. Agent task system: work packages delegated to OpenClaw workers.

## Recommended split

1. Personal tasks use fast capture via Telegram or a quick web form.
2. Personal reminders are sent via Telegram plus daily email digest.
3. Agent tasks use a structured queue with status (`new`, `planned`, `running`, `blocked`, `done`).
4. Every agent task must have owner, deadline, and expected output format.

## Services vs agents

Keep these separate:

1. `services` own state and deterministic workflows
2. `agents` reason over services and help you decide or act
3. `spaces` isolate context

Examples of services:

1. reminders
2. calendar runtime
3. personal tasks
4. braindump
5. Gmail/Drive processors
6. fitness runtime
7. job-search runtime

Agents should not become the source of truth for those systems.

## Visible agent roles

1. `assistant`: default front door for reminders, tasks, calendar, braindump, and project coordination.
2. `researcher`: external research, job search, comparison work, and recommendation synthesis.
3. `fitness_coach`: workouts, exercise logging, progression review, and program guidance.
4. `builder`: implementation and repo-assigned coding work.
5. `ops_guard`: monitoring, failures, route health, and system reviews.

## Internal roles

1. `coordinator`: hidden routing role that decides which visible agent or space should handle a request.
2. `knowledge_librarian`: hidden compression role for summaries, checkpoints, and memory promotion suggestions.

## Sub-agent spawn rules

1. Spawn sub-agent only when task exceeds 30 minutes of focused work.
2. Spawn when task requires isolated context or specialized toolchain.
3. Do not spawn for quick edits, small summaries, or single-call operations.
4. Every sub-agent must include objective, allowed tools, max runtime, output schema, and stop conditions.
5. Coding, debugging, and deep investigation should default to sub-agent execution.
6. Before spawning, announce in one line which sub-agent role and model lane will be used.
7. On failure, report failure reason and fallback path in one line.

## Spaces

Core spaces:

1. `general`
2. `calendar`
3. `tasks`
4. `braindump`
5. `research`
6. `job-search`
7. `fitness`
8. `coding`
9. `ops`
10. `project:<slug>`

Agents operate inside spaces. Transport channels are not the same thing as spaces.

## Project Spaces: New Session vs New Agent

1. New ongoing project: create a new project space first.
2. Default for a new project space is a new assistant session, not a new dedicated agent.
3. Keep one coordinator session per active project objective or milestone.
4. Start a new session inside the same project space when milestone, toolchain, or objective shifts materially.
5. Create a dedicated project agent only when the project repeatedly needs:
   - the same specialized toolchain
   - the same narrow domain context
   - autonomous background work across multiple sessions
6. Do not create one always-on agent per project by default. That raises maintenance cost and context drift.
7. Project spaces own checkpoints; agents are temporary workers unless proven otherwise.

## Dedicated sub-agents worth keeping always-on

Only if repeated use proves the value:

1. `ops_monitor_agent`: uptime checks, alerts, and quota alarms.
2. `job_search_digest_worker`: daily job-search report generation.
3. `inbox_processor`: scheduled email triage.

Do not create always-on specialist agents just because a domain exists.

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

## Continuous improvement

1. Do not use a free-running self-improving agent.
2. Use a bounded review loop owned by `ops_guard`.
3. Daily review should look for route failures, noisy services, and context bloat.
4. Weekly review should look for stale spaces, repeated manual work, and opportunities to productize recurring behavior.
5. Structural changes still require human approval.
