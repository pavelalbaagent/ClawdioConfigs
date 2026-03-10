# Multi-Agent Chat Runtime

Last updated: 2026-03-09

## Goal

Make the visible agent scheme real without turning every request into a new autonomous worker.

Rule:

1. services own data
2. spaces own context
3. agents own reasoning behavior
4. chat state stays bounded and checkpointed

## Live conversational agents

Current conversational runtimes:

1. `assistant`
2. `researcher`
3. `builder`
4. `fitness_coach`

Current non-conversational specialist roles:

1. `ops_guard`

`ops_guard` still routes through structured handlers or task capture until its dedicated runtime exists.

## Main file

1. [assistant_chat_runtime.py](/Users/palba/Projects/Clawdio/scripts/assistant_chat_runtime.py)

The file now hosts the generalized role-aware chat runtime used by:

1. `assistant`
2. `researcher`
3. `builder`
4. `fitness_coach`

## Routing contract

Telegram routing:

1. no prefix -> `assistant`
2. `assistant: ...` -> `assistant`
3. `research: ...` -> `researcher`
4. `coding: ...` -> `builder`
5. `fitness: ...` -> `fitness_coach` structured route
6. `ops: ...` -> `ops_guard` structured route
7. `[project:<slug>] ...` narrows the active space
8. `coding: [project:<slug>] ...` combines specialist role and project context

## Context controls

The runtime does not replay full Telegram history.

It builds prompts from:

1. agent system prompt
2. current space and project context
3. bounded recent-turn history
4. latest checkpoint summary
5. optional selective memory retrieval

Checkpoint controls come from [session_policy.yaml](/Users/palba/Projects/Clawdio/config/session_policy.yaml).

## Memory behavior

When hybrid memory is active:

1. `assistant` can pull general operational context
2. `researcher` can pull prior findings and relevant docs
3. `builder` can pull project and implementation context

Builder-specific workbench context now also carries:

1. local `codex` readiness
2. local `gemini` readiness
3. GitHub repo/account wiring state for the builder surface
4. explicit reminders to stay repo/task oriented and keep project-space routing explicit

Memory is selective:

1. retrieval is not performed on every turn
2. structured service state still takes priority over memory recalls
3. transient chatter is not durable memory

## State files

Local defaults:

1. `data/assistant-chat-state.json`
2. `data/researcher-chat-state.json`
3. `data/builder-chat-state.json`
4. `data/agent-runtime-state.json`

These are runtime artifacts and stay out of git.

## Current limits

1. no conversational `ops_guard` yet
2. no visible session registry UI yet
3. no cross-agent handoff transcripts beyond checkpoints and route history
4. `fitness_coach` still depends on deterministic workout/runtime state for actions; chat is advisory, not authoritative

## Next gates

1. add a visible session registry in the dashboard
2. decide whether `builder` gets VPS-local `codex` or remains API-first there
3. decide whether `ops_guard` gets a bounded conversational runtime or stays structured-only
