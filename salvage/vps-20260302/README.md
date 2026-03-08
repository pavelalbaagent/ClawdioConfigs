# VPS Salvage Pack (2026-03-02)

This folder records the tracked salvage pass for the VPS snapshot.

## Source

1. Raw snapshot archive (not committed): `external/vps-salvage-20260302/vps-openclaw-full-20260302.tgz`.
2. Extracted source tree (not committed): `external/vps-salvage-20260302/extracted/`.

## Current state

1. The temporary `consolidated/` tree was removed after useful assets were either promoted or discarded.
2. Remaining canonical recovery templates live under:
   - `ops/recovered/`
   - `config/recovered/`
3. Raw source remains outside the tracked repo under `external/vps-salvage-20260302/`.

## Redactions applied

1. Personal WhatsApp number was redacted during the review pass.
2. Historical gateway token values were redacted during the review pass.

## Handling policy

1. Treat all `external/vps-salvage-*` data as sensitive.
2. Do not commit raw `openclaw.json`, credentials, session logs, or `.env` from the snapshot.
3. Promote only reviewed files into `config/`, `docs/`, or `ops/`.
4. Do not recreate large tracked salvage duplicates once a canonical replacement exists.
