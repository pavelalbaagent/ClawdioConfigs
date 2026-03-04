# YTIngest Transcript Ingestion Runbook

Last updated: 2026-03-03

## Goal

Enable deterministic transcript ingest on VPS with clear fallbacks, minimal token cost, and easy on/off control.

## Scope

1. Fix OAuth scope for owned-video caption download.
2. Install and configure public-video subtitle extraction (`yt-dlp`).
3. Add smoke-test commands and operational toggles.

This runbook avoids network or SSH config changes, and does not touch Tailscale/access settings.

## 1) Pull latest YTIngest code

Run on VPS:

```bash
cd /home/pavel/.openclaw/workspace/YTIngest
git pull --ff-only
npm install
```

Scope change now in code:
- [auth.js](/Users/palba/Projects/YTIngest/src/auth.js):37 uses `https://www.googleapis.com/auth/youtube.force-ssl`.

## 2) Install transcript prerequisites

Ubuntu/Debian VPS:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg python3-pip
python3 -m pip install --user -U yt-dlp
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
source ~/.profile
```

Verify:

```bash
which yt-dlp
yt-dlp --version
ffmpeg -version | head -n 1
```

## 3) Configure `.env`

Use or update:
- [YTIngest .env.example](/Users/palba/Projects/YTIngest/.env.example)

Minimum transcript settings:

```dotenv
TRANSCRIPT_OUTPUT_DIR=data/transcripts
TRANSCRIPT_LANGS=en.*,es.*
TRANSCRIPT_PUBLIC_ONLY=true
TRANSCRIPT_YTDLP_TIMEOUT_MS=180000
YTDLP_PATH=yt-dlp
```

Optional anti-bot settings for public videos:

```dotenv
YTDLP_COOKIES_FILE=/home/pavel/.openclaw/secrets/youtube-cookies.txt
# or
YTDLP_COOKIES_FROM_BROWSER=chrome
# optional proxy
YTDLP_EXTRA_ARGS=--proxy http://<proxy-host>:<port>
```

## 4) Refresh OAuth token (required once)

If token was created with `youtube.readonly`, regenerate it.

```bash
cd /home/pavel/.openclaw/workspace/YTIngest
cp .secrets/youtube-oauth-token.json .secrets/youtube-oauth-token.backup-$(date +%F-%H%M%S).json 2>/dev/null || true
npm run auth
```

Use scope: `youtube.force-ssl` (already handled by `npm run auth`).

## 5) Smoke tests

### Owned/manageable video test (OAuth captions API lane)

```bash
cd /home/pavel/.openclaw/workspace/YTIngest
npm run ingest -- --videoUrls "https://www.youtube.com/watch?v=<OWNED_OR_MANAGED_VIDEO_ID>" --withTranscripts --maxTranscriptVideos 1
```

Expected in output JSON:
- `videos[0].transcript.status = "ok"`
- `videos[0].transcript.method = "youtube_oauth_caption"`

### Public video test (public-caption lanes)

```bash
cd /home/pavel/.openclaw/workspace/YTIngest
npm run ingest -- --videoUrls "https://youtu.be/uUN1oy2PRHo" --withTranscripts --maxTranscriptVideos 1
```

Recommended for your goal (other people's videos):

```bash
npm run ingest -- --videoUrls "https://youtu.be/uUN1oy2PRHo" --withTranscripts --transcriptPublicOnly --maxTranscriptVideos 1
```

Expected:
- success: `method = "yt_dlp_subtitles"`
- failure: explicit reason, usually `ip_blocked_or_auth_required` or `no_subtitle_files_produced`

Quick inspect:

```bash
LATEST=$(ls -t data/yt-ingest-*.json | head -n 1)
jq '.transcripts, .videos[0].transcript' "$LATEST"
```

## 6) Modular on/off controls (cost-safe)

Default lane:
- run ingest without `--withTranscripts` for daily feed scans.

Transcript lane:
- enable only for selected jobs/videos:
  - `--withTranscripts`
  - `--maxTranscriptVideos N` to hard-cap work per run

Recommended policy:
1. Daily broad ingest: metadata only.
2. Deep-dive shortlist: transcripts on, `N <= 3`.
3. Disable transcript lane immediately if two consecutive runs fail on `ip_blocked_or_auth_required`.

## 7) Integration contract for downstream summaries

Only treat transcript summaries as high-confidence when:
1. `transcript.status == "ok"`.
2. `transcript.filePath` exists.

Otherwise:
1. Fall back to metadata summary.
2. Mark output as `low_confidence_no_transcript`.

## 8) Failure playbook

If `yt_dlp_not_installed`:
1. Re-run install section.
2. Confirm PATH includes `~/.local/bin`.

If `ip_blocked_or_auth_required`:
1. Add/update `YTDLP_COOKIES_FILE`.
2. Re-test with one public video.
3. If still blocked, use proxy in `YTDLP_EXTRA_ARGS`.

If OAuth lane fails with `captions_list_failed`:
1. Re-run `npm run auth`.
2. Confirm correct Google account owns/manages target video.

## 9) Current VPS status (2026-03-03)

Smoke test run:

```bash
npm run ingest -- --videoUrls "https://youtu.be/uUN1oy2PRHo" --withTranscripts --maxTranscriptVideos 1
```

Observed result before token refresh:
1. `youtube_oauth_caption` failed with `captions_list_failed: Request had insufficient authentication scopes`.
2. `yt_dlp_subtitles` failed with `ip_blocked_or_auth_required`.

Observed result after token refresh (`youtube.force-ssl`):
1. `youtube_oauth_caption` now reaches download step but fails with `captions_download_failed: 403` for this public non-owned video.
2. `yt_dlp_subtitles` still fails with `ip_blocked_or_auth_required`.

Observed result in public-only mode (`TRANSCRIPT_PUBLIC_ONLY=true`):
1. `youtube_public_captions` fails with `watch_ip_blocked_or_auth_required`.
2. `yt_dlp_subtitles` fails with `ip_blocked_or_auth_required`.

Interpretation:
1. OAuth scope and token are now correct.
2. OAuth caption lane is for owned/manageable videos.
3. Public transcript lanes still need cookies or proxy from VPS environment.
