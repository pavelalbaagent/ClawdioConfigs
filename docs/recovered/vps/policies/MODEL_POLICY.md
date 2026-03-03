# MODEL_POLICY.md

## Goal
Optimize quality/cost by using OpenAI as default and Claude only for complex project design.

## Provider Routing Rules
- **Default provider:** OpenAI (`gpt-5.2`) for day-to-day execution.
- **Claude (Anthropic):** only for complex project design tasks where clear structure and planning are the main need.

## Active OpenAI Routing (configured)
- **quick-primary:** `openai-codex/gpt-5.1-codex-mini`
- **shared backup lane:** `openai-codex/gpt-5.1` (`fallback-51`) — manual failover only (no auto fallback list)
- **default-primary:** `openai-codex/gpt-5.2`
- **coding-deep (coding/reasoning):** `openai-codex/gpt-5.3-codex`

## OpenAI Cost Tiers (practical)
- **Tier A — Small/Cheap:** `gpt-5.1-codex-mini` for routine admin, formatting, extraction, quick transforms.
- **Tier B — Default:** `gpt-5.2` for most real work.
- **Tier C — Deep/Coding:** `gpt-5.3-codex` for complex coding and deep reasoning.

Runtime note: fallback list cycles across configured lanes in this order:
1) `gpt-5.1-codex-mini` (quick)
2) `gpt-5.3-codex` (deep/coding)

## Task-to-Mode Mapping (OpenAI default)
- **Quick mode (default, ~75–85%)**
  - Todo updates, short rewrites, formatting, simple summaries, routine admin, quick troubleshooting.
- **Balanced mode (~10–20%)**
  - Normal planning, moderate research synthesis, draft cleanup, workflow improvements.
- **Deep mode (~5%, explicit)**
  - High-stakes reasoning, major tradeoffs, decision memos, difficult revisions.

## Claude Trigger (strict)
Use Claude only when at least one is true:
1. The user explicitly asks for a complex project blueprint/architecture.
2. The task needs a multi-phase plan with dependencies, milestones, and risk controls.
3. The expected output is a structured design artifact (roadmap, implementation plan, system design).

If none apply, stay on OpenAI.

## User Command Shortcuts
- `quick: ...` → OpenAI quick mode (`quick-primary`)
- `balanced: ...` → OpenAI default mode (`default-primary`)
- `deep: ...` → OpenAI deep mode (`coding-deep`)
- `design: ...` → Claude project-design mode (structure/plan first)

## Response Shape by Mode
- **Quick:** concise, action-first, minimal explanation.
- **Balanced:** concise + key rationale + next actions.
- **Deep:** explicit assumptions, options, tradeoffs, recommendation.
- **Design (Claude):** deliverables-first: scope, architecture, phases, timeline, risks, checkpoints.

## Assistant Behavior
- Confirm mode briefly only when it changes.
- Return to OpenAI Quick/Balanced after Claude design tasks.
- Prefer fast, good-enough decisions unless deep/design is explicitly needed.
- Downshift to cheapest sufficient OpenAI tier for repetitive or low-risk tasks.
- Upshift only when output quality would materially benefit.

## Next Setup Step (when you want)
Configure explicit OpenAI aliases for tiers after adding more OpenAI models, e.g.:
- `openclaw models aliases add --alias openai-small --model <cheap-model-id>`
- `openclaw models aliases add --alias openai-default --model openai-codex/gpt-5.3-codex`
Then we can bind `quick:` to `openai-small` and keep `balanced:` on `openai-default`.
