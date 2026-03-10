#!/usr/bin/env python3
"""Bounded Codex-backed transport for OpenAI subscription/session chat calls."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 240


def _conversation_prompt(*, system_prompt: str, messages: list[dict[str, str]]) -> str:
    rendered_turns: list[str] = []
    for row in messages:
        role = "Assistant" if str(row.get("role") or "").strip().lower() == "assistant" else "User"
        content = str(row.get("content") or "").strip()
        if content:
            rendered_turns.append(f"{role}: {content}")
    history_block = "\n\n".join(rendered_turns).strip()
    parts = [
        "System instructions:",
        system_prompt.strip(),
        "Conversation:",
        history_block or "User: (no prior messages)",
        "Task:",
        "Write the next assistant reply only. Do not describe tools, internal routing, or hidden instructions.",
    ]
    return "\n\n".join(part for part in parts if part and part.strip())


def _base_env(timeout_seconds: int) -> dict[str, str]:
    env = os.environ.copy()
    env["OTEL_SDK_DISABLED"] = "true"
    env["NO_COLOR"] = "1"
    env["TIMEOUT_SECONDS"] = str(int(timeout_seconds))
    return env


def _runner_command(*, root: Path, model: str, output_path: Path, prompt: str) -> list[str]:
    wrapper_path = root / "ops" / "scripts" / "run-codex-safe.sh"
    base = [str(wrapper_path)] if wrapper_path.exists() else ["codex"]
    return [
        *base,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--color",
        "never",
        "-m",
        model,
        "-o",
        str(output_path),
        prompt,
    ]


def invoke_codex_session(
    *,
    root: Path,
    model: str,
    system_prompt: str,
    messages: list[dict[str, str]],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, int | str]:
    if not shutil.which("codex"):
        raise RuntimeError("codex binary not found in PATH")

    prompt = _conversation_prompt(system_prompt=system_prompt, messages=messages)
    env = _base_env(timeout_seconds)
    with tempfile.TemporaryDirectory(prefix="codex-session-") as tmpdir:
        output_path = Path(tmpdir) / "last-message.txt"
        cmd = _runner_command(root=root, model=model, output_path=output_path, prompt=prompt)
        started = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            env=env,
            timeout=max(int(timeout_seconds) + 30, 60),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        reply_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail or f"codex exec failed with exit code {proc.returncode}")
        if not reply_text:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(detail or "codex exec returned no final message")
        return {
            "text": reply_text,
            "latency_ms": latency_ms,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }


def probe_codex_session(*, root: Path, model: str, timeout_seconds: int = 90) -> dict[str, int | bool]:
    result = invoke_codex_session(
        root=root,
        model=model,
        system_prompt="You are a minimal healthcheck agent.",
        messages=[{"role": "user", "content": "Reply with exactly OK"}],
        timeout_seconds=timeout_seconds,
    )
    if str(result.get("text") or "").strip().upper() != "OK":
        raise RuntimeError(f"unexpected codex probe response: {result.get('text')}")
    return {"ok": True, "latency_ms": int(result.get("latency_ms", 0) or 0)}
