# Gateway Change Safety Protocol

Use this for any config change that might impact Dashboard/WhatsApp/Slack.

## Goal
Never get stuck after a bad restart. Always have:
- pre-change backup
- post-change health check
- fast rollback

---

## 1) Pre-change snapshot (always)

```bash
TS=$(date +%F-%H%M%S)
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$TS
openclaw status > ~/.openclaw/status.pre.$TS.txt
```

Optional (full state backup):

```bash
tar -czf ~/openclaw-state-$TS.tgz -C ~ .openclaw
```

---

## 2) Apply change

Make your config edit.

---

## 3) Controlled restart + checks

```bash
openclaw gateway restart
openclaw status
openclaw channels status --probe
```

Pass criteria:
- Dashboard reachable
- WhatsApp = enabled + connected
- Slack = running

---

## 4) Auto-rollback trigger

If any of these fail within 60-90 seconds, rollback immediately:
- gateway not running
- dashboard unreachable
- WhatsApp not connected

Rollback:

```bash
# replace <BACKUP_FILE> with latest known-good backup
cp <BACKUP_FILE> ~/.openclaw/openclaw.json
openclaw gateway restart
openclaw status
```

Find latest backup quickly:

```bash
ls -1t ~/.openclaw/openclaw.json.bak.* | head -n 5
```

---

## 5) WhatsApp-specific verification

After any restart or channel config change:

```bash
openclaw status
openclaw channels status --probe
```

Then send one real test message from your WhatsApp to confirm inbound/outbound flow.

---

## 6) Safe-change rule (operational)

For risky config changes:
1. Change one thing only.
2. Restart once.
3. Verify.
4. Continue.

No batch edits + restart unless explicitly needed.

---

## 7) Last-known-good pin

Keep one pinned backup file as your emergency known-good config:

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.known-good
```

Emergency recover:

```bash
cp ~/.openclaw/openclaw.json.known-good ~/.openclaw/openclaw.json
openclaw gateway restart
openclaw status
```

---

## 8) Minimal command checklist

```bash
# before
TS=$(date +%F-%H%M%S); cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$TS

# after edit
openclaw gateway restart && openclaw channels status --probe

# rollback if needed
cp ~/.openclaw/openclaw.json.bak.$TS ~/.openclaw/openclaw.json && openclaw gateway restart
```
