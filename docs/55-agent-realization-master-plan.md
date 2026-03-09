# Agent Realization Master Plan

Last updated: 2026-03-09

## Goal

Realize the system as a coherent operator environment with:

1. one strong default `Assistant`
2. a small number of specialist agents
3. deterministic service backends
4. bounded context and cost
5. review-driven improvement instead of uncontrolled autonomy

## Executive Read

The repo is now strong enough to stop designing in the abstract and start converging on a real agent system.

What exists today:

1. deterministic services for reminders, braindump, calendar, tasks, Gmail/Drive scaffolding, and job-search
2. a Telegram adapter and dashboard
3. working provider stack locally
4. working API-backed providers on the VPS
5. a documented agent scheme

What is still missing:

1. a real specialist runtime for `fitness_coach`
2. a visible session registry and cleanup loop
3. governance surfaced directly in the dashboard as an operator habit
4. VPS-local access to the premium supervised coding lane

The next system should not be built as “one more agent.”
It should be built as:

1. services
2. agents over services
3. spaces over context
4. review loops over drift

## Current Gaps

### 1. Agents are defined, but not operationally visible

Today:

1. agent policy exists in config
2. routing policy exists in config
3. project spaces exist
4. runtime registry is visible in the dashboard
5. Telegram specialist prefixes route into agent-owned spaces

Remaining gap:

1. `assistant`, `researcher`, and `builder` are now conversational, but `fitness_coach` and `ops_guard` still route through structured paths

### 2. Memory is underpowered for the intended multi-agent design

Today:

1. local provider wiring supports embeddings
2. the active memory profile is now `hybrid_124`
3. memory sync and checkpoints exist, but session/governance visibility is still thin

Impact:

1. the current stack now supports stronger assistant/researcher/builder continuity
2. but it still needs timer-backed sync discipline and more visible session cleanup

### 3. Session discipline is defined but not enforced as a runtime workflow

Today:

1. checkpoint rules exist
2. project-space rules exist
3. restart/summarize rules exist

Missing:

1. no real session registry
2. no visible “spawned agent” history
3. no cleanup task that archives stale spaces/summaries

### 4. The premium OpenAI subscription/session lane is only local

Today:

1. it is modeled correctly in routing
2. it resolves and probes locally
3. the VPS lacks `codex`, so the lane is not usable there

Impact:

1. local supervised heavy work is available
2. VPS heavy work still falls back to Anthropic/Gemini only

### 5. Improvement is still a policy, not a process

Today:

1. `continuous_improvement` exists in config

Missing:

1. no timer-backed cadence on the VPS yet
2. no visible operator workflow around acting on review outputs
3. no cleanup automation that closes the loop on recommendations

## Target Operating Model

### Services

Services own durable state:

1. reminders
2. calendar
3. personal tasks
4. braindump
5. Gmail processor
6. Drive workspace
7. fitness runtime
8. job-search runtime

Rule:

1. agents never become the source of truth for these

### Visible agents

#### Assistant

Primary front door.

Use for:

1. reminders
2. tasks
3. calendar Q&A and scheduling
4. braindump triage and promotion
5. lightweight project coordination
6. general personal system questions

#### Researcher

Use for:

1. tech research
2. tool comparisons
3. job-search triage
4. recommendation memos
5. information gathering across sources

#### Fitness Coach

Use for:

1. workout guidance
2. logging
3. progression review
4. program updates

#### Builder

Use for:

1. coding
2. debugging
3. refactors
4. repo work

#### Ops Guard

Use for:

1. service health
2. failure review
3. quota/routing audits
4. improvement review outputs

### Internal roles

#### Coordinator

Invisible role that:

1. classifies request
2. chooses agent
3. chooses space
4. decides whether a spawn is warranted

#### Knowledge Librarian

Invisible role that:

1. writes summaries
2. compacts context
3. proposes memory promotions
4. identifies stale spaces

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

Rule:

1. transport is not context
2. raw chat history is not memory
3. the active space determines what is loaded

## Communication Model

### Recommended surfaces

1. one primary Telegram bot surface
2. dashboard as operator cockpit
3. optional later topics/groups only if human organization needs them

### Why not many channels first

Too many channels early creates:

1. browsing clutter
2. ambiguous ownership
3. duplicated context

The cleaner approach is:

1. one bot surface
2. explicit agent/space routing
3. dashboard visibility

### Recommended command grammar

1. no prefix -> `Assistant`
2. `reminders: ...`
3. `research: ...`
4. `fitness: ...`
5. `coding: ...`
6. `ops: ...`
7. `[project:<slug>] ...`

This should become the main runtime contract before adding more transport complexity.

## Memory Plan

### Recommendation

The repo is now ready for hybrid memory by default.

Use a bounded hybrid model:

1. keep `hybrid_124` live for `assistant`, `researcher`, and `builder`
2. keep numeric and app-backed state in SQLite/service stores
3. use retrieval selectively, not every turn
4. downgrade to `md_only` only during degraded-provider or deliberate cost-control windows

Best targets:

1. fitness
2. job-search
3. project spaces
4. ops reviews and durable architecture notes

Rule:

1. numeric/app state should remain in SQLite/runtime services
2. embeddings should support retrieval, not become the data store

### Memory hygiene rules

1. summarize stale sessions
2. cap recent-turn replay
3. promote only durable facts and reusable summaries
4. keep raw transient chatter out of durable memory

## Session Spawning And Cleanup

### Recommended spawn rules

Spawn only when one of these is true:

1. specialist toolchain required
2. objective large enough to justify isolation
3. background monitoring/retries needed
4. project-specific narrow context is cheaper than polluting main space

Do not spawn for:

1. one-step scheduling
2. simple status checks
3. quick transformations
4. straightforward app-backed commands

### Cleanup rules

Daily:

1. mark stale transient sessions
2. compact high-turn spaces
3. refresh summaries for active project spaces

Weekly:

1. archive dormant project spaces
2. flag spaces with summary drift
3. surface repeated manual operations

## Coordination Model

The best model is:

1. `Assistant` as visible front door
2. `Coordinator` as hidden router
3. `Knowledge Librarian` as hidden compactor

That avoids a visible “supervisor agent” while keeping the system structured.

This is better than making a separate visible “general agent” and “assistant agent”.

## Token Efficiency Rules

1. deterministic services first
2. keep the `Assistant` cheap for state lookups and scheduling
3. use `Researcher` and `Builder` on `L2` only when needed
4. reserve premium `L3` for hard work, not casual chat
5. never let raw channel history define context
6. always prefer:
   - space summary
   - current app state
   - recent turns
   over full history replay

## Recommended Models

### Local machine

This should be the richest environment.

1. `L1_low_cost` -> Gemini free (`gemini-2.5-flash-lite`)
2. `L1_openrouter_free_fallback` -> `openrouter/free`
3. `L2_balanced` -> Gemini free first, then OpenAI subscription/session, then OpenRouter, then Anthropic
4. `L3_heavy` -> OpenAI subscription/session first, then Anthropic, then Gemini Pro

### VPS

Current reality:

1. API-backed providers work
2. `codex` and `gemini` CLIs are missing

So current VPS practical routing is:

1. `L1` -> Gemini free
2. `L1 fallback` -> OpenRouter
3. `L2` -> Gemini -> OpenRouter -> Anthropic
4. `L3` -> Anthropic -> Gemini Pro

Recommendation:

1. treat the premium OpenAI subscription/session lane as local-first
2. only add it to the VPS after `codex` is installed and authenticated there

## Continuous Improvement Design

Do not build a self-improving autonomous agent.

Build a governance process owned by `Ops Guard`.

### Daily review output

Generate:

1. route failures
2. provider issues
3. stale spaces
4. repeated retries
5. manual hotspots

### Weekly review output

Generate:

1. cost mix by lane
2. quality issues by space
3. repeated manual work worth automating
4. stale integrations
5. architecture changes recommended

### Output contract

Write:

1. `observations`
2. `recommendations`
3. `approval_required_changes`
4. `cleanup_candidates`

No automatic structural changes.

## Missing Components To Build Next

### 1. Session registry and active-mode visibility

Need:

1. active session registry in the dashboard
2. visible `agent + space + lane + checkpoint`
3. explicit stale-session cleanup actions

### 2. Fitness specialist runtime

Need:

1. real `fitness_coach` conversational or semi-conversational flow
2. structured workout state reads/writes
3. progression review without raw chat replay

### 3. Ops review operationalization

Need:

1. daily timer on VPS
2. weekly timer on VPS
3. operator-facing review/cleanup habit

### 4. VPS premium supervised lane

Need:

1. install `codex` on VPS if desired
2. authenticate it cleanly
3. decide when `builder` escalates to that lane

### 5. Session cleanup

Need:

1. archive dormant project spaces
2. compact stale chat state
3. surface cleanup candidates directly in the dashboard

## Recommended Build Order

### Phase 1

1. dashboard agent registry
2. active agent/space state
3. explicit Telegram specialist routing

### Phase 2

1. `Assistant`, `Researcher`, and `Builder` conversational runtime
2. space-aware context loading
3. summary refresh hooks

### Phase 3

1. `Ops Guard` daily and weekly review outputs
2. memory sync status loop
3. stale-space management

### Phase 4

1. `Fitness Coach` runtime completion
2. deeper `Researcher` workflows
3. optional VPS `codex` install for premium subscription lane

## Final Recommendation

Do not add more agent names right now.

The right system is:

1. a strong `Assistant`
2. three strong specialists (`Researcher`, `Fitness Coach`, `Builder`)
3. one hidden router (`Coordinator`)
4. one hidden compactor (`Knowledge Librarian`)
5. one governance role (`Ops Guard`)

That is enough to feel like a serious multi-agent system without collapsing into complexity theater.
