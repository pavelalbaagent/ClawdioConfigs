# Codex CLI and Gemini CLI on VPS

## Goal

Run both CLIs on the VPS as controlled tools that OpenClaw can call through wrappers, with strict limits.

## Preflight checks on VPS

1. `command -v codex && codex --version`
2. `command -v gemini && gemini --version`
3. Confirm environment variables and auth are configured for each CLI.
4. Confirm wrappers are executable and reachable by OpenClaw service user.

## Integration pattern

1. OpenClaw never calls raw `codex` or `gemini` directly.
2. OpenClaw calls `ops/scripts/run-codex-safe.sh` or `ops/scripts/run-gemini-safe.sh`.
3. Wrappers enforce timeout, arg denylist, output length cap, and audit logs.

## Suggested usage model

1. `L1_low_cost` and `L2_balanced` tasks run through normal API routes.
2. `L3_heavy` tasks can call CLI wrappers only with approval.
3. Critical outputs require review before external side effects.

## Service account considerations

1. Run CLI wrappers under a dedicated non-root user.
2. Keep auth tokens in restricted env file.
3. Rotate credentials and verify token scopes quarterly.

## Operational guardrails

1. Set per-call timeout to 5 minutes initially.
2. Block unrestricted tool flags in wrapper denylist.
3. Track call count, latency, and failure reasons in logs.
4. If wrapper fails twice for same task, route to manual review.
