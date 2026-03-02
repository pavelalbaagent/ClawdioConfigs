# n8n Workflow Contract Pack (v1)

Last updated: 2026-03-02

## Files

1. [workflow-contracts.yaml](/Users/palba/Projects/Clawdio/contracts/n8n/workflow-contracts.yaml)
2. [webhook-envelope.schema.json](/Users/palba/Projects/Clawdio/contracts/n8n/webhook-envelope.schema.json)
3. [workflow-result.schema.json](/Users/palba/Projects/Clawdio/contracts/n8n/workflow-result.schema.json)

## v1 Workflows

1. `wf_inbox_router_v1`: ingress commands, normalize, route to task/reminder.
2. `wf_personal_reminder_v1`: create reminder, process `done`/`defer`, one follow-up at +1h.
3. `wf_agent_task_sync_v1`: sync task state with external task manager.
4. `wf_news_digest_v1`: optional daily brief pipeline (disabled by default).

## Approval Gates

1. External writes are approval-gated.
2. Destructive operations always require explicit approval.
3. News digest external posting is approval-gated.

## Cost Defaults

1. Keep reminder and task sync flows deterministic (`L0_no_model`).
2. Use model only for ambiguous triage or digest summarization.
3. Keep `wf_news_digest_v1` disabled until baseline is stable.

## n8n Module Toggles

Module toggles are in [config/integrations.yaml](/Users/palba/Projects/Clawdio/config/integrations.yaml) under `integrations.n8n.modules`.

1. `inbox_router`
2. `personal_reminders`
3. `agent_task_sync`
4. `news_digest`

## Deployment Notes

1. Keep `N8N_WEBHOOK_SECRET` required for inbound webhooks.
2. Keep `N8N_BASE_URL` and `N8N_API_KEY` in runtime secret store only.
3. For each workflow, validate inbound payload against webhook schema and outbound payload against result schema.
4. Send failures to `alerts` space and include `next_action=manual_handoff` when unresolved.
