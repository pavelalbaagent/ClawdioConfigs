import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))

import openai_session_transport  # noqa: E402


class OpenAISessionTransportTests(unittest.TestCase):
    def test_invoke_codex_session_builds_bounded_exec_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, cwd=None, capture_output=None, text=None, env=None, timeout=None):
                self.assertEqual(cmd[0], "codex")
                self.assertIn("exec", cmd)
                self.assertIn("--sandbox", cmd)
                self.assertIn("read-only", cmd)
                self.assertIn("--ephemeral", cmd)
                self.assertIn("-m", cmd)
                self.assertIn("gpt-5-mini", cmd)
                output_idx = cmd.index("-o") + 1
                Path(cmd[output_idx]).write_text("Bounded reply", encoding="utf-8")
                self.assertEqual(cwd, str(root))
                self.assertEqual(env["OTEL_SDK_DISABLED"], "true")
                self.assertEqual(env["NO_COLOR"], "1")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch("openai_session_transport.shutil.which", return_value="/usr/local/bin/codex"), mock.patch(
                "openai_session_transport.subprocess.run",
                side_effect=fake_run,
            ):
                result = openai_session_transport.invoke_codex_session(
                    root=root,
                    model="gpt-5-mini",
                    system_prompt="You are a planner.",
                    messages=[{"role": "user", "content": "Help me plan tomorrow."}],
                    timeout_seconds=120,
                )

        self.assertEqual(result["text"], "Bounded reply")
        self.assertGreaterEqual(int(result["latency_ms"]), 0)

    def test_probe_requires_exact_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with mock.patch(
                "openai_session_transport.invoke_codex_session",
                return_value={"text": "OK", "latency_ms": 12, "prompt_tokens": 0, "completion_tokens": 0},
            ):
                probe = openai_session_transport.probe_codex_session(root=root, model="gpt-5-mini")

        self.assertTrue(probe["ok"])
        self.assertEqual(probe["latency_ms"], 12)

    def test_probe_rejects_unexpected_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch(
                "openai_session_transport.invoke_codex_session",
                return_value={"text": "Not OK", "latency_ms": 12, "prompt_tokens": 0, "completion_tokens": 0},
            ):
                with self.assertRaises(RuntimeError):
                    openai_session_transport.probe_codex_session(root=root, model="gpt-5-mini")


if __name__ == "__main__":
    unittest.main()
