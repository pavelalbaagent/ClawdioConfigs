# YouTube Public Transcript Access (VPS)

Last updated: 2026-03-03

## Goal

Make transcript ingest work for public videos owned by other creators.

## Why this is needed

From VPS, YouTube often blocks anonymous transcript/subtitle fetches.  
Current failures in YTIngest show:
1. `watch_ip_blocked_or_auth_required`
2. `ip_blocked_or_auth_required`

## Option A (recommended): cookies file

1. On your desktop browser (logged into YouTube), export cookies for `youtube.com` in Netscape `cookies.txt` format.
2. Copy file to VPS:

```bash
scp -i ~/.ssh/id_ed25519_pawork ~/Downloads/youtube-cookies.txt pavel@100.119.27.8:/home/pavel/.openclaw/secrets/youtube-cookies.txt
```

3. On VPS, secure file and set env:

```bash
ssh -i ~/.ssh/id_ed25519_pawork pavel@100.119.27.8 '
mkdir -p /home/pavel/.openclaw/secrets
chmod 600 /home/pavel/.openclaw/secrets/youtube-cookies.txt
cd /home/pavel/.openclaw/workspace/YTIngest
if grep -q "^YTDLP_COOKIES_FILE=" .env; then
  sed -i "s|^YTDLP_COOKIES_FILE=.*|YTDLP_COOKIES_FILE=/home/pavel/.openclaw/secrets/youtube-cookies.txt|" .env
else
  printf "\nYTDLP_COOKIES_FILE=/home/pavel/.openclaw/secrets/youtube-cookies.txt\n" >> .env
fi
'
```

4. Re-test:

```bash
ssh -i ~/.ssh/id_ed25519_pawork pavel@100.119.27.8 '
cd /home/pavel/.openclaw/workspace/YTIngest
npm run ingest -- --videoUrls "https://youtu.be/uUN1oy2PRHo" --withTranscripts --transcriptPublicOnly --maxTranscriptVideos 1
'
```

## Option B: proxy

If cookies still fail, route subtitle requests through a trusted proxy:

```dotenv
YTDLP_EXTRA_ARGS=--proxy http://<proxy-host>:<port>
```

## Operational notes

1. Cookies expire; refresh periodically.
2. Keep cookies file outside git and permissioned (`600`).
3. Keep transcript lane modular:
   - on: `--withTranscripts --transcriptPublicOnly`
   - off: omit `--withTranscripts`
