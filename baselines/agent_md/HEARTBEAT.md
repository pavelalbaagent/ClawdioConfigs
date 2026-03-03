# HEARTBEAT.md

## Purpose

Keep lightweight periodic checks without noisy messaging.

## Check Cadence

1. Work hours: every 2-3 hours.
2. Quiet hours: no proactive messages except urgent events.

## Checklist

1. Check high-priority inbox items.
2. Check next 24-hour calendar commitments.
3. Check task blockers and overdue items.
4. Check budget/usage anomalies.
5. If no important delta, return `HEARTBEAT_OK`.

## Quiet Hours

1. Default quiet window: 23:00 to 08:00 local.
2. Respect custom quiet windows in USER.md when set.

## Escalate Immediately When

1. Access or uptime risk is detected.
2. Deadline-critical event in less than 2 hours.
3. Credential/auth failures block core workflows.
