# Drive Shared Workspace Plan

Last updated: 2026-03-07

## Goal

Create one shared Drive workspace where both you and the agent can collaborate without confusion.

## Recommended ownership model

1. You create the shared root folder in your Google Drive.
2. You share that folder with the agent's Google account as editor.
3. OpenClaw uses that shared root as its only allowed Drive write boundary.

This is the recommended model because it reduces the risk that you lose visibility or ownership if the agent account changes later.

## Recommended root

Use `GOOGLE_DRIVE_ROOT_FOLDER_ID` as the ID of the shared root folder.

## Suggested top-level structure

1. `00_inbox`
2. `01_working`
3. `02_outputs`
4. `03_reference`
5. `04_archive`
6. `10_projects`
7. `11_agents`
8. `12_shared_sources`

Recommended nested structure:

1. `11_agents/assistant`
2. `11_agents/researcher`
3. `11_agents/builder`
4. `11_agents/fitness_coach`
5. `11_agents/ops_guard`
6. `12_shared_sources/inbox_attachments`
7. `12_shared_sources/ai_tools_reference`

## Recommended collaboration rules

1. You can create folders or drop files into `00_inbox` and `10_projects`.
2. The agent can create project subfolders inside `10_projects` and working artifacts inside `01_working`.
3. The agent should not write outside the shared root.
4. Folder-sharing changes should stay approval-gated.
5. Per-agent folders should be used for bounded working material, not as separate roots.
6. Shared sources should hold durable docs multiple agents may need.

## Scope choice

The Drive integration now assumes the broader `drive` scope because the old `drive.file` pattern is too narrow for a real shared-folder collaboration model.

Why:

1. `drive.file` works best for app-created or app-opened files.
2. A backend collaboration workspace with shared folders is closer to full Drive collaboration than app-file access.
3. The safety boundary should be enforced by root-folder policy, not by pretending the app has a narrower working set than it really does.

Official source:

1. [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

## Contract source

1. [contracts/drive/shared-workspace.yaml](/Users/palba/Projects/Personal/Clawdio/contracts/drive/shared-workspace.yaml)

## Current runtime

The current runtime exists and is safe by default:

1. [scripts/drive_workspace_bootstrap.py](/Users/palba/Projects/Personal/Clawdio/scripts/drive_workspace_bootstrap.py)

Behavior:

1. verifies that the configured shared root exists
2. compares current child folders with the contract layout
3. reports missing and extra folders
4. creates missing contract folders only when `--apply` is explicitly passed

## Run commands

Verify current shared root:

```bash
python3 scripts/drive_workspace_bootstrap.py --env-file /etc/openclaw/openclaw.env
```

Strict verification with JSON output:

```bash
python3 scripts/drive_workspace_bootstrap.py --env-file /etc/openclaw/openclaw.env --strict --json
```

Create missing contract folders:

```bash
python3 scripts/drive_workspace_bootstrap.py --env-file /etc/openclaw/openclaw.env --apply
```

The runtime also writes the latest summary to:

1. `data/drive-workspace-status.json`

## Current limits

1. Sharing changes are still manual/approval-gated outside this script.
2. The runtime manages only the top-level contract layout under the configured root.
3. It does not yet create per-project subfolders automatically.
4. Nested agent/shared-source subfolders are now scaffolded by the bootstrap runtime when `--apply` is used.
