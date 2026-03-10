# Agent Scheme And Governance

Last updated: 2026-03-09

## Goal

Make the system feel like one coherent operator environment instead of a pile of unrelated bots.

The design should keep:

1. state in services
2. reasoning in agents
3. context isolated in spaces
4. improvement bounded by review and approval

## The stack

### Services

Services own durable state and deterministic actions:

1. reminders
2. calendar runtime
3. personal tasks
4. braindump
5. Gmail inbox processing
6. Drive shared workspace
7. fitness runtime
8. job-search runtime

### Visible agents

These are the roles you should think in:

1. `assistant`
2. `researcher`
3. `fitness_coach`
4. `builder`
5. `ops_guard`

### Internal roles

These exist to support the user-facing system, not to create more surfaces:

1. `coordinator`
2. `knowledge_librarian`

## Visible agent definitions

### Assistant

Use for:

1. reminders
2. personal tasks
3. calendar questions
4. schedule rearrangement
5. braindump capture and promotion
6. project-level coordination

Default spaces:

1. `general`
2. `reminders`
3. `calendar`
4. `tasks`
5. `braindump`
6. `project:<slug>`

### Researcher

Use for:

1. tool and product research
2. technical comparisons
3. strategy research
4. job search triage and recommendations

Default spaces:

1. `research`
2. `job-search`
3. `project:<slug>`

### Fitness Coach

Use for:

1. workout guidance
2. logging sessions
3. progression review
4. program adjustments

Default space:

1. `fitness`

### Builder

Use for:

1. coding
2. repo-scoped implementation
3. debugging
4. integration work

Default spaces:

1. `coding`
2. `project:<slug>`

### Ops Guard

Use for:

1. service health
2. failure review
3. route health
4. drift detection
5. bounded improvement reviews

Default space:

1. `ops`

## Internal role definitions

### Coordinator

Responsibility:

1. classify user requests
2. choose visible agent
3. choose space
4. keep the front door simple

This should usually be invisible to you.

### Knowledge Librarian

Responsibility:

1. compact long context
2. maintain summaries
3. suggest promotions into durable memory
4. reduce replay cost

This should also be invisible to you.

## Spaces

Core spaces:

1. `general`
2. `reminders`
3. `calendar`
4. `tasks`
5. `braindump`
6. `research`
7. `job-search`
8. `fitness`
9. `coding`
10. `ops`

Dynamic spaces:

1. `project:<slug>`

Rule:

1. channels are transport
2. spaces are context
3. services are state

## User-facing operating model

Recommended default:

1. the main bot surface enters through `assistant`
2. requests are rerouted logically when needed
3. Telegram should use one assistant front-door chat plus optional dedicated specialist chats for `researcher`, `builder`, and `fitness_coach`
4. explicit prefixes still exist as overrides, not as the primary interaction pattern

Examples:

1. in `assistant_main`: `what reminders do i have?`
2. in `assistant_main`: `what's on my calendar tomorrow?`
3. in `researcher_lab`: `compare OpenRouter vs Gemini for production fallback`
4. in `builder_workbench`: `review the dashboard auth flow in repo X`
5. in `fitness_coach`: `should i swap anything today if my elbow feels irritated?`
6. in any surface: `[project:calendar-cleanup] move tomorrow's block to Friday`

Practical rule:

1. Telegram chats are bound surfaces
2. spaces choose the context bucket
3. services still own the state
4. focus commands remain only as compatibility fallback inside `assistant_main`

## Runtime status

Implemented now:

1. dashboard agent registry and active-route visibility
2. Telegram specialist routing into agent-owned spaces
3. local route history persisted outside chat history
4. Telegram chat-surface bindings for assistant, research, builder, fitness, and ops
5. natural-language handoff for reminders, tasks, calendar, braindump, and common fitness phrases
6. hybrid conversational `fitness_coach` layered on deterministic workout state

Still pending:

1. richer `ops_guard` conversational/runtime surface if needed
2. Telegram topic/group support if separate chats become too fragmented
3. VPS-local `codex` install/auth if the OpenAI subscription lane should be usable there

## What should not become separate agents

Do not create a dedicated visible agent for:

1. inbox processing
2. calendar delivery
3. braindump capture
4. memory maintenance

Those are services or internal support functions.

## Continuous-improvement model

Do not run a free self-improving agent.

Use a bounded governance loop instead.

### Daily review

Owned by `ops_guard`.

Review:

1. failing routes
2. quota/rate-limit issues
3. noisy reminders or retries
4. context bloat hotspots
5. stale tasks or spaces

### Weekly review

Owned by `ops_guard` with support from `coordinator` and `knowledge_librarian`.

Review:

1. routing quality vs cost
2. repeated manual work worth automating
3. stale project spaces
4. memory quality
5. broken or unused integrations

### Bounded actions

Allowed without special redesign:

1. refresh summaries
2. flag stale spaces
3. propose config changes
4. generate review reports

Blocked without approval:

1. changing credentials
2. changing provider order
3. enabling integrations
4. creating persistent agents
5. altering approval gates

## Recommended next implementation steps

1. add an agent registry to the dashboard
2. expose current active agent and space in state
3. add explicit routing commands for specialist agents
4. add a bounded review report output for `ops_guard` (implemented)
