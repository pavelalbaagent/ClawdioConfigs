# Local Quality Gates

## Included checks

1. Config validator: [validate_configs.py](/Users/palba/Projects/Clawdio/scripts/validate_configs.py)
2. Secret scanner: [scan_secrets.py](/Users/palba/Projects/Clawdio/scripts/scan_secrets.py)

## Pre-commit hook

1. Hook path: [.githooks/pre-commit](/Users/palba/Projects/Clawdio/.githooks/pre-commit)
2. Enable once:

```bash
git config core.hooksPath .githooks
```

## Manual checks

```bash
python3 scripts/validate_configs.py --config-dir config
python3 scripts/scan_secrets.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
