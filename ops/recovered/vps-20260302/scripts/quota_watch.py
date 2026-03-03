#!/usr/bin/env python3
"""Monitor agent usage quotas and warn when thresholds are crossed."""
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

WORKSPACE = Path("/home/pavel/.openclaw/workspace")
STATE_FILE = WORKSPACE / "quota-watch.json"
SESSION_STORE = Path("/home/pavel/.openclaw/agents/clawdio-main/sessions/sessions.json")
SESSIONS_DIR = SESSION_STORE.parent
OPENCLAW = "/usr/bin/openclaw"
TARGET_NUMBER = "<PRIVATE_PHONE>"
THRESHOLDS_5H = [80, 60, 40, 20, 0]
THRESHOLDS_DAY = [90, 80, 70, 60, 50, 40, 30, 20, 10]


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"5h_index": 0, "day_index": 0}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state) + "\n")


def find_session_file() -> Optional[Path]:
    if not SESSION_STORE.exists():
        return None
    data = json.loads(SESSION_STORE.read_text())
    for session in data.get("sessions", []):
        if session.get("key") == "agent:clawdio-main:main":
            session_id = session.get("sessionId")
            if session_id:
                candidate = SESSIONS_DIR / f"{session_id}.jsonl"
                if candidate.exists():
                    return candidate
    return None


def latest_usage_text(session_file: Path) -> Optional[str]:
    if not session_file.exists():
        return None
    lines = session_file.read_text().splitlines()
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        if message.get("toolName") != "session_status":
            continue
        for chunk in reversed(message.get("content", [])):
            if chunk.get("type") == "text" and "📊 Usage" in chunk.get("text", ""):
                return chunk["text"]
    return None


def parse_usage(text: str) -> Optional[tuple[int, int]]:
    match = re.search(r"5h\s*(\d+)%\s*left.*?Day\s*(\d+)%\s*left", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def send_warning(messages: list[str]):
    if not messages:
        return
    payload = "Quota warnings:\n" + "\n".join(messages)
    cmd = [
        OPENCLAW,
        "message",
        "send",
        "--channel",
        "whatsapp",
        "--target",
        TARGET_NUMBER,
        "--message",
        payload,
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    state = load_state()
    session_file = find_session_file()
    if not session_file:
        return
    usage_text = latest_usage_text(session_file)
    if not usage_text:
        return
    parsed = parse_usage(usage_text)
    if not parsed:
        return
    left_5h, left_day = parsed
    alerts: list[str] = []

    while state["5h_index"] < len(THRESHOLDS_5H) and left_5h <= THRESHOLDS_5H[state["5h_index"]]:
        threshold = THRESHOLDS_5H[state["5h_index"]]
        alerts.append(f"⚠️ 5h quota dropping: {left_5h}% left (≤ {threshold}%).")
        state["5h_index"] += 1

    while state["day_index"] < len(THRESHOLDS_DAY) and left_day <= THRESHOLDS_DAY[state["day_index"]]:
        threshold = THRESHOLDS_DAY[state["day_index"]]
        alerts.append(f"⚠️ Weekly quota dropping: {left_day}% left (≤ {threshold}%).")
        state["day_index"] += 1

    if alerts:
        send_warning(alerts)
        save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        ...
