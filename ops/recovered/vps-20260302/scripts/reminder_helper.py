#!/usr/bin/env python3
"""Helper to schedule resilient WhatsApp reminders with keep-alive pings."""
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import dedent

OPENCLAW = "/usr/bin/openclaw"
REMINDERS_FILE = Path("/home/pavel/.openclaw/workspace/REMINDERS.md")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True)


def parse_iso(ts: str) -> datetime:
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def format_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def schedule_cron(cron_args: list[str]) -> None:
    run(cron_args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule WhatsApp reminders with keep-alive")
    parser.add_argument("--name", required=True, help="Base job name (e.g., reminder-1805) ")
    parser.add_argument("--when", required=True, help="ISO timestamp (UTC or with offset)")
    parser.add_argument("--tz", required=True, help="IANA timezone for scheduling")
    parser.add_argument("--message", required=True, help="Reminder text")
    parser.add_argument("--target", default="<PRIVATE_PHONE>", help="WhatsApp destination")
    parser.add_argument("--retries", type=int, default=1, help="Number of isolated retries after the backup")
    parser.add_argument("--retry-delay", type=int, default=20, help="Seconds between retries")
    parser.add_argument("--keepalive", action="store_true", help="Send a ping before the reminder")
    parser.add_argument("--keepalive-delay", type=int, default=30, help="Seconds between keep-alive and reminder")
    args = parser.parse_args()

    when_dt = parse_iso(args.when)
    keepalive_time = when_dt - timedelta(seconds=args.keepalive_delay)
    primary_when = when_dt.isoformat()

    if args.keepalive:
        schedule_cron([
            OPENCLAW,
            "cron",
            "add",
            "--name",
            f"{args.name}-keepalive",
            "--agent",
            "clawdio-main",
            "--session",
            "isolated",
            "--model",
            "quick-primary",
            "--message",
            f"Keep-alive ping for reminder {args.name}",
            "--at",
            keepalive_time.isoformat(),
            "--tz",
            args.tz,
            "--delete-after-run",
            "--announce",
            "--description",
            "keeps WhatsApp socket awake before reminder",
        ])

    schedule_cron([
        OPENCLAW,
        "cron",
        "add",
        "--name",
        args.name,
        "--agent",
        "clawdio-main",
        "--session",
        "main",
        "--system-event",
        f"WhatsApp reminder: {args.message}",
        "--at",
        primary_when,
        "--tz",
        args.tz,
        "--delete-after-run",
        "--description",
        "primary reminder for main session",
    ])

    backup_names = []
    base_at = when_dt
    for attempt in range(args.retries + 1):
        retry_dt = base_at + timedelta(seconds=attempt * args.retry_delay)
        job_name = f"{args.name}-backup" + (f"-retry-{attempt}" if attempt > 0 else "")
        backup_names.append((job_name, retry_dt))
        schedule_cron([
            OPENCLAW,
            "cron",
            "add",
            "--name",
            job_name,
            "--agent",
            "clawdio-main",
            "--session",
            "isolated",
            "--model",
            "quick-primary",
            "--message",
            f"Send WhatsApp {args.target} '{args.message}' and log delivery (attempt {attempt + 1})",
            "--at",
            retry_dt.isoformat(),
            "--tz",
            args.tz,
            "--delete-after-run",
            "--announce",
            "--description",
            "isolated WhatsApp backup retry",
        ])

    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = dedent(
        f"""
        ### Reminder pair created {datetime.utcnow().isoformat()}Z
        - **Name:** {args.name}
        - **When (UTC):** {format_dt(when_dt)}
        - **Timezone:** {args.tz}
        - **Message:** {args.message}
        - **Target:** {args.target}
        - **Keep-alive:** {'yes' if args.keepalive else 'no'} (delay {args.keepalive_delay}s)
        - **Backup attempts:**
{chr(10).join(f"    {name} @ {dt.isoformat()}" for name, dt in backup_names)}
        - **Note:** Delivery mimics the old WhatsApp digest pattern: keep-alive ping, main system event, isolated send + retries.
        """
    )
    with REMINDERS_FILE.open("a") as out:
        out.write(entry + "\n")

    print("Reminder pair scheduled: main + backups (keep-alive: %s)" % ("yes" if args.keepalive else "no"))


if __name__ == "__main__":
    main()
