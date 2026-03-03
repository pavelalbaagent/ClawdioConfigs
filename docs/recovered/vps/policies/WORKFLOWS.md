# WORKFLOWS.md

## 1) Paper Workflow (Abstract + Intro)
1. Define target audience + venue (2 lines).
2. Clarity pass: remove vague claims, tighten opening paragraph.
3. Contribution pass: explicit novelty bullets (2–3).
4. Grant-fit pass: align language with impact/use-case criteria.
5. Final pass: tone, concision, and consistency.

## 2) Grant-Fit Workflow
1. Pick top 3 grant opportunities.
2. Extract criteria into bullets.
3. Score paper fit (High/Medium/Low) per criterion.
4. Identify gaps + mitigation plan.
5. Decide: apply now / revise then apply / skip.

## 3) US Visa Workflow
1. Confirm visa type + required documents.
2. Create account + monitor appointment slots.
3. Prepare DS/application details checklist.
4. Prepare supporting documents folder.
5. Confirm appointment and prep interview notes.

## 4) Daily Execution Rhythm
- 07:00 — AI news digest
- Morning (before teaching) — pick Top 3 tasks
- 17:30–20:00 — no pings (family/commute)
- 20:00 — side-project check-in (focus sprint or intentional rest)

## 5) Project Design Workflow (`design:` mode → Claude)
Use this when the task is complex and needs clear structure before execution.

1. **Problem framing (1 screen)**
   - Goal
   - Constraints
   - Success criteria
2. **Scope split**
   - In scope
   - Out of scope (for now)
3. **Architecture / approach**
   - Components
   - Data/flow
   - Key decisions
4. **Execution plan**
   - Phases (P0/P1/P2...)
   - Milestones and deliverables
   - Dependencies and critical path
5. **Risk plan**
   - Top 5 risks
   - Mitigations
   - Early warning signals
6. **Operating cadence**
   - Weekly checkpoints
   - What to review each checkpoint
7. **First 72-hour action list**
   - Concrete next actions
   - Owners (if any)
   - Definition of done

### Design Output Template
- **Summary** (5–8 lines)
- **Scope** (in/out)
- **Architecture** (simple, concrete)
- **Phased roadmap** (with dates or sequence)
- **Risks + mitigations**
- **Immediate next 3 actions**

## 6) Daily Reflection + Persistence Sync
Use once per day (or via cron) to retain practical learning.

1. Read `memory/YYYY-MM-DD.md` for today + yesterday.
2. Extract: decisions, lessons learned, recurring friction, and one process fix.
3. Append a short `Daily Lessons` block to today’s memory file (no duplicates).
4. Promote durable rules/preferences into `MEMORY.md`.
5. If it changes operations, update one canonical doc (`WORKFLOWS.md`, `AGENTS.md`, `TOOLS.md`, or project plan).

## 7) Ops Change Control (Anti-Drift)
Use when model routing, security posture, or automation policy changes.

1. Update one **primary** canonical doc first (`WORKFLOWS.md` or project plan).
2. Mirror only distilled durable points into `MEMORY.md` (not full implementation detail).
3. In the same pass, check neighboring docs for stale conflicting guidance and fix it immediately.
4. Record the change in that day’s `memory/YYYY-MM-DD.md` under `Daily Lessons`/Consolidation.

## 8) Model Lane Health
- Track quick/default/deep lane share using `intel/model-usage/latest.md` as part of the daily rollup.
- When the quick lane share exceeds ~70% or a WhatsApp thread nears ~150K tokens, chunk the thread (auto-summarize + follow-on session) and shift reminder-architecture rework or any summary expected to exceed ~20K tokens into gpt-5.2 so the deep lane handles the heavy reasoning.
- Keep reminder backups on gpt-5.2 and log their outcomes in `REMINDERS.md`, ensuring the 499-window retries stay synchronized with the canonical schedule.
