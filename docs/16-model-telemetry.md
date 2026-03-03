# Model Telemetry

## Goal

Track lane usage, fallbacks, errors, and estimated cost from model-call logs.

## Files

1. Schema: [model-call-log.schema.json](/Users/palba/Projects/Clawdio/telemetry/model-call-log.schema.json)
2. Example logs: [model-calls.example.ndjson](/Users/palba/Projects/Clawdio/telemetry/model-calls.example.ndjson)
3. Report generator: [model_usage_report.py](/Users/palba/Projects/Clawdio/scripts/model_usage_report.py)

## Generate report

```bash
python3 scripts/model_usage_report.py \
  --input telemetry/model-calls.example.ndjson \
  --output telemetry/model-usage-latest.md
```
