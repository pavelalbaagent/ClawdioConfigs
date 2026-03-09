# Token Acquisition Playbook (One by One)

Last updated: 2026-03-07

## Working File

Use this local file to fill credentials:

- `secrets/openclaw.env` (already created, gitignored)

Validate at any point:

1. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --strict --addons-profile addons_off`
2. `python3 scripts/check_env_requirements.py --env-file secrets/openclaw.env --include-optional --addons-profile addons_search_brave`

## Phase 1: Required for initial VPS go-live (`bootstrap_core` + `addons_off`)

1. `TELEGRAM_BOT_TOKEN`
   - Go to Telegram, open `@BotFather`.
   - Run `/newbot`, finish setup, copy the bot token.
   - Paste into `TELEGRAM_BOT_TOKEN`.

2. `TELEGRAM_ALLOWED_CHAT_ID`
   - Send one message to your bot from your Telegram account.
   - Open in browser: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates`
   - Copy `message.chat.id` (your personal chat id) into `TELEGRAM_ALLOWED_CHAT_ID`.

3. `OPENCLAW_DASHBOARD_TOKEN`
   - Generate one locally:
   - `openssl rand -hex 32`
   - Paste into `OPENCLAW_DASHBOARD_TOKEN`.

## Phase 2: Turn on Google Calendar (`bootstrap_minimal`)

4. `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
   - In Google Cloud Console, create/select project.
   - Enable Google Calendar API.
   - Create OAuth client credentials.
   - Copy client id/secret into env file.

5. `GOOGLE_REFRESH_TOKEN`
   - Use OAuth flow with the Google account that will own your canonical calendar.
   - Request at minimum the Calendar scope for MVP.
   - If you want fewer re-auth steps later, you can also request Gmail modify + Drive scopes now and leave those integrations disabled until needed.
   - Save the refresh token in `GOOGLE_REFRESH_TOKEN`.

6. `GOOGLE_CALENDAR_ID`
   - Create or choose the Google calendar you want OpenClaw to use.
   - Copy the calendar ID from Google Calendar settings.

## Phase 3: Core integrations after MVP

7. `GMAIL_USER_EMAIL`
   - Put the exact Gmail address used in the OAuth grant.
   - This is the dedicated agent inbox address.
   - Planned use is scheduled inbox triage, not just manual read/send.

8. `GOOGLE_DRIVE_ROOT_FOLDER_ID`
   - In Google Drive, create/select one shared root folder for human/agent collaboration.
   - Recommended model: you create it in your Drive and share it with the agent account as editor.
   - Open folder and copy id from URL segment after `/folders/`.

9. `GITHUB_TOKEN`
   - In GitHub settings, create PAT (fine-grained or classic).
   - Minimum practical permissions for your flow: repo read/write, issues/PR actions, workflow access as needed.
   - Paste token into `GITHUB_TOKEN`.

10. `GITHUB_OWNER`
   - Set your org/user name, for example `pavelalbaagent`.

11. `PERSONAL_TASK_PROVIDER` and provider token
   - Keep `PERSONAL_TASK_PROVIDER=todoist` (default).
   - In Todoist settings, copy API token and paste into `TODOIST_API_TOKEN`.
   - If you switch provider later, update both provider name and corresponding token fields.

12. `AGENT_TASK_PROVIDER` and provider token
    - Keep `AGENT_TASK_PROVIDER=asana` (default).
    - In Asana developer settings, create PAT and paste into `ASANA_PERSONAL_ACCESS_TOKEN`.
    - Get workspace gid via Asana API or URL and paste into `ASANA_WORKSPACE_GID`.

13. `N8N_BASE_URL`
    - Set your reachable n8n base URL (for example `https://n8n.yourdomain.com`).

14. `N8N_API_KEY`
    - In n8n user/profile settings, create API key.
    - Paste into `N8N_API_KEY`.

15. `N8N_WEBHOOK_SECRET`
    - Generate one locally:
    - `openssl rand -hex 32`
    - Paste result into `N8N_WEBHOOK_SECRET`.

16. `OPENAI_API_KEY`
   - Create key at OpenAI platform API keys page.
   - Paste into `OPENAI_API_KEY`.
   - Needed only when you switch memory back from `md_only` to an embedding-enabled profile.

## Phase 4: Strongly recommended (cost/routing quality)

17. `GEMINI_API_KEY`
    - Create API key in Google AI Studio.
    - Paste into `GEMINI_API_KEY`.

18. `OPENROUTER_API_KEY`
    - Create key in OpenRouter dashboard.
    - Set `OPENROUTER_API_KEY`.
    - Optional: set a free fallback model in `OPENROUTER_FREE_MODEL`.

19. `ANTHROPIC_API_KEY` (optional reserve)
    - Create key in Anthropic console.
    - Keep for fallback or high-ambiguity tasks only.

20. Local generated app secrets
    - Generate these locally:
    - `openssl rand -hex 32` -> `OPENCLAW_GATEWAY_TOKEN`
    - `openssl rand -hex 32` -> `OPENCLAW_SIGNING_SECRET`
    - `openssl rand -hex 32` -> `OPENCLAW_DASHBOARD_TOKEN`

## Phase 5: Optional add-ons (enable only when needed)

20. Brave search add-on
    - `BRAVE_SEARCH_API_KEY` from Brave Search API account.

21. Slack add-on
    - Create Slack app.
    - Copy bot token to `SLACK_BOT_TOKEN`.
    - Copy signing secret to `SLACK_SIGNING_SECRET`.
    - If socket mode is used, add `SLACK_APP_TOKEN`.

22. AgentMail add-on
    - Create account in AgentMail Console.
    - Create API key.
    - Paste into `AGENTMAIL_API_KEY`.

23. Trello add-on
    - Get `TRELLO_API_KEY` and `TRELLO_TOKEN` from Trello developer portal.
    - Optional board id into `TRELLO_DEFAULT_BOARD_ID`.

24. 1Password add-on
    - Create service account in 1Password.
    - Paste token into `OP_SERVICE_ACCOUNT_TOKEN`.
    - Optional account shorthand into `OP_ACCOUNT`.

25. Transcript fallback add-on fields
    - `YTDLP_COOKIES_FILE`: set absolute path on VPS to YouTube cookies file.
    - `YTDLP_EXTRA_ARGS`: optional proxy/extra yt-dlp args.

26. Tavily or Codexbar
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
6. `python3 /opt/clawdio/scripts/check_env_requirements.py --env-file /etc/openclaw/openclaw.env --strict --addons-profile addons_off`
