# Model Routing Policy (Cost-Aware and Quality-Aware)

## Objectives

1. Keep routine work on cheap/free capacity.
2. Reserve premium capability for high-impact tasks.
3. Fail gracefully when free-tier limits are exhausted.

## Important constraint

ChatGPT Plus is excellent for interactive supervised work, but unattended server automation usually depends on API-accessible credentials.
Treat Plus as your heavy manual lane unless your OpenClaw stack is explicitly wired to an API billing path.

## Task classes

1. `L0_no_model`: deterministic operations, routing logic, filters, cron, reminders.
2. `L1_low_cost`: summaries, rewriting, extraction, simple classification.
3. `L2_balanced`: multi-step planning, code review, integration troubleshooting.
4. `L3_heavy`: architecture design, ambiguous tasks, high-stakes reasoning.

## Routing defaults

1. `L0_no_model` -> no LLM call.
2. `L1_low_cost` -> Google free tier first.
3. `L2_balanced` -> paid model with moderate context, or Google fallback if budget mode is strict.
4. `L3_heavy` -> supervised run through Codex CLI or Gemini CLI with manual approval.

## Fallback ladder

1. Attempt primary model for lane.
2. If quota/rate limit hit, downgrade context size and retry once.
3. If still blocked, fallback to next cheaper available lane.
4. If task requires high confidence and no viable model remains, pause and ask for approval.

## Token and cost controls

1. Enforce per-task max tokens by lane.
2. Enforce daily and monthly spend caps.
3. Cache frequent prompt-response pairs when task class allows.
4. Summarize long histories and retrieve only relevant context windows.
5. Block auto-escalation to heavy lane without explicit rule or approval.

## Suggested lane budgets

1. `L1_low_cost`: 60-75% of total volume.
2. `L2_balanced`: 20-35% of total volume.
3. `L3_heavy`: 5-10% of total volume.

## When to use Codex and Gemini CLIs

1. Codex CLI for high-quality coding/planning tasks where you supervise output.
2. Gemini CLI for overflow and broad ideation when free quota is available.
3. Expose both only through controlled wrappers.
4. Wrapper requirements are command allowlist, timeout, and input/output logging.
5. High-cost runs must require manual escalation.
