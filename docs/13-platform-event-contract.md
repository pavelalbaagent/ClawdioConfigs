# Platform Event Contract

## Goal

Use one canonical inbound-event shape across Slack, Telegram, WhatsApp, email, and web so business logic is channel-agnostic.

## Canonical schema

1. Schema file: [canonical-event.schema.json](/Users/palba/Projects/Clawdio/contracts/canonical-event.schema.json)
2. Required fields: `platform`, `channel_id`, `user_id`, `message_id`, `text`, `ts_utc`.

## Normalization helper

1. Script: [normalize_event.py](/Users/palba/Projects/Clawdio/scripts/normalize_event.py)
2. Converts raw payloads into canonical format.
3. Supports `slack`, `telegram`, `whatsapp`, `email`, and `web`.

## Usage

```bash
python3 scripts/normalize_event.py --input /path/to/raw.json --platform slack
```

If `--platform` is omitted, the script attempts to infer platform from payload shape.
