# Project Spaces And Session/Agent Strategy

Last updated: 2026-03-07

## Goal

Keep ongoing projects isolated enough to avoid context pollution without creating unnecessary always-on agents.

## Core rule

1. Every ongoing project gets its own project space.
2. A project space should usually start as a separate session, not as a separate agent.

## Why

Project work tends to accumulate:

1. decisions
2. task context
3. files and tool state
4. open questions
5. summaries and checkpoints

That is too much to keep mixed inside `main`, but it is still not enough to justify a dedicated persistent agent by default.

## Recommended default

For a new project:

1. create project
2. auto-create project space
3. start one coordinator session for that project
4. write checkpoints at milestones
5. spawn specialist agents only when needed

## When to use a new session in the same project space

1. milestone changed
2. technical direction changed
3. tool/integration auth state changed
4. current session has become summary-heavy and a fresh checkpoint is cheaper
5. you are resuming after a long idle gap

## When to use a new dedicated agent for a project

Only if one of these is true:

1. the same specialist role is repeatedly needed across several sessions
2. the project requires persistent narrow domain context
3. the project requires background monitoring or autonomous retries
4. the project has its own toolchain/runtime boundary that should stay isolated

Examples:

1. `good dedicated agent`: transcript ingestion worker, inbox triage worker, ops monitor
2. `not automatically a dedicated agent`: “project about calendar cleanup”, “project about dashboard improvements”

## Anti-pattern

Do not create:

1. one always-on agent per project
2. one giant shared session for all projects

Both fail for opposite reasons:

1. too many agents -> maintenance and cost sprawl
2. one giant session -> context contamination and token waste

## Recommended project-space template

Each project space should track:

1. `space_id`
2. `space_key`
3. `project_id`
4. `session_strategy`
5. `agent_strategy`
6. `summary`
7. `last_checkpoint_at`
8. `entry_command_hint`

## Current repo implementation

The dashboard workspace now auto-creates a project space record for each project and exposes:

1. space key
2. session strategy
3. agent strategy
4. entry command hint

Task-to-project promotion also creates the new project space automatically.

The routing layer now supports:

1. `[project:<slug>]` message prefixes for project-space targeting
2. explicit task moves into an existing project space
3. explicit calendar-candidate assignment into an existing project space

## Recommendation

1. use project spaces aggressively
2. use dedicated agents conservatively
3. let checkpoints and summaries carry continuity
4. let agents be scoped workers, not default homes for project memory
