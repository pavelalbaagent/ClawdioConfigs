import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_tools_digest.py"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import ai_tools_digest as digest  # noqa: E402


class AIToolsDigestTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_digest_preview_reads_recent_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            corpus_root = tmp_path / "corpus" / "ai_tools"
            corpus_root.mkdir(parents=True)
            (corpus_root / "blog_OpenAI_News_Introducing_GPT-5_3-Codex.md").write_text(
                "# Introducing GPT-5.3 Codex\n\nOpenAI released GPT-5.3 Codex.\n",
                encoding="utf-8",
            )
            config_path = tmp_path / "knowledge_sources.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "knowledge_sources:",
                        "  active_profile: default",
                        "  profiles:",
                        "    default:",
                        "      enabled_sources:",
                        "        - ai_tools_db",
                        "  sources:",
                        "    ai_tools_db:",
                        "      enabled: true",
                        "      root_candidates:",
                        f"        - {corpus_root}",
                        "      digest:",
                        "        enabled: true",
                        "        chat_id_env: TELEGRAM_RESEARCH_CHAT_ID",
                        "        max_items: 4",
                        "        lookback_hours: 72",
                    ]
                ),
                encoding="utf-8",
            )
            status_path = tmp_path / "digest-status.json"
            proc = self.run_script(["--config", str(config_path), "--status-file", str(status_path), "--json"])
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["item_count"], 1)
            self.assertIn("GPT-5.3 Codex", payload["preview"])

    def test_apply_sends_digest_to_configured_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            corpus_root = tmp_path / "corpus" / "ai_tools"
            corpus_root.mkdir(parents=True)
            (corpus_root / "blog_OpenAI_News_Introducing_GPT-5_3-Codex.md").write_text(
                "# Introducing GPT-5.3 Codex\n\nOpenAI released GPT-5.3 Codex.\n",
                encoding="utf-8",
            )
            config_path = tmp_path / "knowledge_sources.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "knowledge_sources:",
                        "  active_profile: default",
                        "  profiles:",
                        "    default:",
                        "      enabled_sources:",
                        "        - ai_tools_db",
                        "  sources:",
                        "    ai_tools_db:",
                        "      enabled: true",
                        "      root_candidates:",
                        f"        - {corpus_root}",
                        "      digest:",
                        "        enabled: true",
                        "        chat_id_env: TELEGRAM_RESEARCH_CHAT_ID",
                        "        max_items: 4",
                        "        lookback_hours: 72",
                    ]
                ),
                encoding="utf-8",
            )
            env_path = tmp_path / "openclaw.env"
            env_path.write_text(
                "TELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_RESEARCH_CHAT_ID=12345\n",
                encoding="utf-8",
            )
            with mock.patch.object(digest.TelegramClient, "send_long_message", return_value=[{"ok": True}]) as send_mock, mock.patch.object(
                sys,
                "argv",
                [
                    "ai_tools_digest.py",
                    "--config",
                    str(config_path),
                    "--env-file",
                    str(env_path),
                    "--apply",
                    "--json",
                ],
            ):
                result = digest.main()
            self.assertEqual(result, 0)
            send_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
