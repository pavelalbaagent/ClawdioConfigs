# CONFIG_BASELINE.md

Baseline captured: 2026-02-28-022619 (UTC)

## Known-good config files
- /home/pavel/.openclaw/openclaw.json.known-good
- /home/pavel/.openclaw/openclaw.json.known-good.2026-02-28-022619

## Quick rollback
```bash
cp /home/pavel/.openclaw/openclaw.json.known-good /home/pavel/.openclaw/openclaw.json
/home/pavel/.openclaw/workspace/safe-restart.sh
```

## Active model routing baseline
- default-primary: openai-codex/gpt-5.2
- quick-primary: openai-codex/gpt-5.1-codex-mini
- coding-deep: openai-codex/gpt-5.3-codex
- fallback list order:
  1) openai-codex/gpt-5.1-codex-mini
  2) openai-codex/gpt-5.3-codex

## Gmail hook baseline
- hooks.defaultSessionKey: hook:ingress
- hooks.gmail.model: quick-primary
- hooks.gmail.thinking: off
