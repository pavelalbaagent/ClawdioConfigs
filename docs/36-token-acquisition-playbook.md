# Token Acquisition Playbook (One by One)

Last updated: 2026-03-04

## Working File

Use this local file to fill credentials:

- `secrets/openclaw.env` (already created, gitignored)

Validate at any point:

1. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --strict --addons-profile addons_off`
2. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --include-optional --addons-profile addons_search_brave`

## Phase 1: Required for current baseline (`lean_manual` + `addons_off`)

1. `TELEGRAM_BOT_TOKEN`
   - Go to Telegram, open `@BotFather`.
   - Run `/newbot`, finish setup, copy the bot token.
   - Paste into `TELEGRAM_BOT_TOKEN`.

2. `TELEGRAM_ALLOWED_CHAT_ID`
   - Send one message to your bot from your Telegram account.
   - Open in browser: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates`
   - Copy `message.chat.id` (your personal chat id) into `TELEGRAM_ALLOWED_CHAT_ID`.

3. `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
   - In Google Cloud Console, create/select project.
   - Enable Gmail API and Google Drive API.
   - Create OAuth client credentials.
   - Copy client id/secret into env file.

4. `GOOGLE_REFRESH_TOKEN`
   - Use OAuth flow with your OpenClaw Gmail account and the same client id/secret.
   - Request scopes for Gmail + Drive (and Calendar if you plan to enable it later).
   - Exchange auth code for refresh token and save it in `GOOGLE_REFRESH_TOKEN`.

5. `GMAIL_USER_EMAIL`
   - Put the exact Gmail address used in the OAuth grant.

6. `GOOGLE_DRIVE_ROOT_FOLDER_ID`
   - In Google Drive, create/select root folder for agent files.
   - Open folder and copy id from URL segment after `/folders/`.

7. `GITHUB_TOKEN`
   - In GitHub settings, create PAT (fine-grained or classic).
   - Minimum practical permissions for your flow: repo read/write, issues/PR actions, workflow access as needed.
   - Paste token into `GITHUB_TOKEN`.

8. `GITHUB_OWNER`
   - Set your org/user name, for example `pavelalbaagent`.

9. `PERSONAL_TASK_PROVIDER` and provider token
   - Keep `PERSONAL_TASK_PROVIDER=todoist` (default).
   - In Todoist settings, copy API token and paste into `TODOIST_API_TOKEN`.
   - If you switch provider later, update both provider name and corresponding token fields.

10. `AGENT_TASK_PROVIDER` and provider token
    - Keep `AGENT_TASK_PROVIDER=asana` (default).
    - In Asana developer settings, create PAT and paste into `ASANA_PERSONAL_ACCESS_TOKEN`.
    - Get workspace gid via Asana API or URL and paste into `ASANA_WORKSPACE_GID`.

11. `N8N_BASE_URL`
    - Set your reachable n8n base URL (for example `https://n8n.yourdomain.com`).

12. `N8N_API_KEY`
    - In n8n user/profile settings, create API key.
    - Paste into `N8N_API_KEY`.

13. `N8N_WEBHOOK_SECRET`
    - Generate one locally:
    - `openssl rand -hex 32`
    - Paste result into `N8N_WEBHOOK_SECRET`.

14. `OPENAI_API_KEY`
    - Create key at OpenAI platform API keys page.
    - Paste into `OPENAI_API_KEY`.

## Phase 2: Strongly recommended (cost/routing quality)

15. `GEMINI_API_KEY`
    - Create API key in Google AI Studio.
    - Paste into `GEMINI_API_KEY`.

16. `OPENROUTER_API_KEY`
    - Create key in OpenRouter dashboard.
    - Set `OPENROUTER_API_KEY`.
    - Optional: set a free fallback model in `OPENROUTER_FREE_MODEL`.

17. `ANTHROPIC_API_KEY` (optional reserve)
    - Create key in Anthropic console.
    - Keep for fallback or high-ambiguity tasks only.

18. Local generated app secrets
    - Generate these locally:
    - `openssl rand -hex 32` -> `OPENCLAW_GATEWAY_TOKEN`
    - `openssl rand -hex 32` -> `OPENCLAW_SIGNING_SECRET`
    - `openssl rand -hex 32` -> `OPENCLAW_DASHBOARD_TOKEN`

## Phase 3: Optional add-ons (enable only when needed)

19. Brave search add-on
    - `BRAVE_SEARCH_API_KEY` from Brave Search API account.

20. Slack add-on
    - Create Slack app.
    - Copy bot token to `SLACK_BOT_TOKEN`.
    - Copy signing secret to `SLACK_SIGNING_SECRET`.
    - If socket mode is used, add `SLACK_APP_TOKEN`.

21. Trello add-on
    - Get `TRELLO_API_KEY` and `TRELLO_TOKEN` from Trello developer portal.
    - Optional board id into `TRELLO_DEFAULT_BOARD_ID`.

22. 1Password add-on
    - Create service account in 1Password.
    - Paste token into `OP_SERVICE_ACCOUNT_TOKEN`.
    - Optional account shorthand into `OP_ACCOUNT`.

23. Transcript fallback add-on fields
    - `YTDLP_COOKIES_FILE`: set absolute path on VPS to YouTube cookies file.
    - `YTDLP_EXTRA_ARGS`: optional proxy/extra yt-dlp args.

24. Tavily or Codexbar
    - `TAVILY_API_KEY` only if you explicitly enable Tavily add-on.
    - `CODEXBAR_API_KEY` only if Codexbar provider mode requires auth in your setup.

## Final checks

1. Required-only readiness:
2. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --strict --addons-profile addons_off`
3. Recommended add-ons readiness:
4. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --strict --addons-profile addons_core_recommended`
5. Optional visibility check:
6. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --include-optional --addons-profile addons_search_brave`

## VPS deployment

1. Copy to VPS:
2. `scp -i ~/.ssh/id_ed25519_pawork secrets/openclaw.env pavel@100.119.27.8:/tmp/openclaw.env`
3. Move to runtime path on VPS:
4. `sudo mkdir -p /etc/openclaw && sudo mv /tmp/openclaw.env /etc/openclaw/openclaw.env && sudo chmod 600 /etc/openclaw/openclaw.env`
5. Validate on VPS:
6. `python3 /home/pavel/Projects/Clawdio/scripts/check_env_requirements.py --env-file /etc/openclaw/openclaw.env --strict --addons-profile addons_off`
