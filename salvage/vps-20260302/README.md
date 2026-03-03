# VPS Salvage Pack (2026-03-02)

This folder contains consolidated, redacted assets recovered from the VPS snapshot.

## Source

1. Raw snapshot archive (not committed): `external/vps-salvage-20260302/vps-openclaw-full-20260302.tgz`.
2. Extracted source tree (not committed): `external/vps-salvage-20260302/extracted/`.

## Included

1. `consolidated/keep-core/`: files selected for direct reuse.
2. `consolidated/archive-reference/`: files worth keeping only as reference.

## Redactions applied

1. Personal WhatsApp number replaced with `<PRIVATE_PHONE>` in consolidated files.
2. `OPENCLAW_GATEWAY_TOKEN` replaced with `<REDACTED>` in service file.

## Handling policy

1. Treat all `external/vps-salvage-*` data as sensitive.
2. Do not commit raw `openclaw.json`, credentials, session logs, or `.env` from the snapshot.
3. Promote only reviewed files into `config/`, `docs/`, or `ops/`.
