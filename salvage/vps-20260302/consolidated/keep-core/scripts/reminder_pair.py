#!/usr/bin/env python3
"""Schedule a 499-aware WhatsApp reminder pair and log it in REMINDERS.md."""
import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/Guayaquil"
DEFAULT_CONTACT = "<PRIVATE_PHONE>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up a reminder system-event + backup send pair and log it."
    )
    parser.add_argument(
        "--time",
        required=True,
        help="ISO-ish local time when the reminder should fire (e.g., 2026-03-02T19:10).",
    )
    parser.add_argument(
        "--message",
        "-m",
        required=True,
        help="What to remind Pavel about (this text appears in the WhatsApp reminder).",
    )
    parser.add_argument(
        "--name",
        "-n",
        help="Optional short reminder name (will be lowercased and spaces become dashes).",
    )
    parser.add_argument(
        "--tz",
        default=DEFAULT_TZ,
        help=f"IANA timezone for --time (default: {DEFAULT_TZ}).",
    )
    parser.add_argument(
        "--contact",
        default=DEFAULT_CONTACT,
        help=f"WhatsApp contact to ping (default: {DEFAULT_CONTACT}).",
    )
    return parser.parse_args()


def sanitize_name(raw: str) -> str:
    raw = raw.strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^a-z0-9-]", "-", raw)
    raw = re.sub(r"-+", "-", raw)
    return raw.strip("-") or "reminder"


def parse_local_dt(time_str: str, tz: str) -> datetime.datetime:
    normalized = time_str.strip().replace(" ", "T")
    try:
        dt = datetime.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(
            "--time must look like YYYY-MM-DDTHH:MM (seconds optional)."
        ) from exc
    zone = ZoneInfo(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    else:
        dt = dt.astimezone(zone)
    return dt


def run_cron_add(cmd: list[str]) -> dict:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            "Failed to add cron job:\n"
            + result.stderr.strip()
            + "\nCommand: "
            + " ".join(cmd)
        )
    payload = result.stdout.strip()
    if not payload:
        raise SystemExit("Cron add returned no JSON payload.")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit("Could not parse cron add output as JSON") from exc


def update_log(log_path: Path, entry: str) -> None:
    header = "\n## Backup repo & automation"
    text = log_path.read_text()
    if header not in text:
        raise SystemExit("REMINDERS.md is missing the expected header for backup section.")
    before, after = text.split(header, 1)
    new_text = before.rstrip() + "\n\n" + entry.strip() + "\n\n" + header + after
    log_path.write_text(new_text)


def build_entry(local_dt: datetime.datetime, tz_label: str, message: str, main_name: str, main_id: str, backup_id: str) -> str:
    local_time = local_dt.strftime("%I:%M %p").lstrip("0")
    if not local_time:
        local_time = local_dt.strftime("%I:%M %p")
    date_label = local_dt.strftime("%Y-%m-%d")
    escaped_message = message.replace('"', '\\"')
    return (
        f"- `{main_name}` → one-shot for {local_time} {tz_label} on {date_label} (message: \"{escaped_message}\")."
        f" Main job `{main_id}` / backup job `{backup_id}` (backup uses coding-deep and retries once when a 499 occurs before replying)."
    )


def main() -> None:
    args = parse_args()
    local_dt = parse_local_dt(args.time, args.tz)
    utc_dt = local_dt.astimezone(datetime.timezone.utc)
    iso_utc = utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    base_name = args.name or f"reminder-{local_dt.strftime('%Y%m%dT%H%M')}"
    base_name = sanitize_name(base_name)
    backup_name = f"{base_name}-backup"

    main_text = (
        f"Reminder: {args.message} (scheduled for {local_dt.strftime('%Y-%m-%d %H:%M %Z')})."
    )
    backup_message = (
        f"Send a WhatsApp message to {args.contact} via the message tool saying \"Reminder: {args.message}\". "
        "If the send fails with HTTP 499 or the connection drops, wait 20 seconds and try once more. "
        "After the final attempt succeeds or fails, reply here with the outcome."
    )

    main_cmd = [
        "openclaw",
        "cron",
        "add",
        "--json",
        "--name",
        base_name,
        "--agent",
        "clawdio-main",
        "--session",
        "main",
        "--system-event",
        main_text,
        "--at",
        iso_utc,
        "--delete-after-run",
        "--tz",
        args.tz,
    ]
    main_job = run_cron_add(main_cmd)

    backup_cmd = [
        "openclaw",
        "cron",
        "add",
        "--json",
        "--name",
        backup_name,
        "--agent",
        "clawdio-main",
        "--session",
        "isolated",
        "--model",
        "coding-deep",
        "--message",
        backup_message,
        "--at",
        iso_utc,
        "--delete-after-run",
        "--tz",
        args.tz,
        "--announce",
    ]
    backup_job = run_cron_add(backup_cmd)

    log_path = Path(__file__).resolve().parents[1] / "REMINDERS.md"
    tt = args.tz
    entry = build_entry(
        local_dt,
        tt,
        args.message,
        base_name,
        main_job["id"],
        backup_job["id"],
    )
    update_log(log_path, entry)

    print("Scheduled reminder pair:")
    print(f"  - {base_name} → {main_job['id']}")
    print(f"  - {backup_name} → {backup_job['id']}")
    print(f"Logged entry in {log_path}")


if __name__ == "__main__":
    main()
