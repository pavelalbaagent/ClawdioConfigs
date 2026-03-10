import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))

import provider_smoke_check as smoke  # noqa: E402


class ProviderSmokeCheckTests(unittest.TestCase):
    def test_collect_status_reports_missing_google_env_by_default(self):
        status = smoke.collect_status(
            models_path=ROOT / "config" / "models.yaml",
            memory_path=ROOT / "config" / "memory.yaml",
            integrations_path=ROOT / "config" / "integrations.yaml",
            agents_path=ROOT / "config" / "agents.yaml",
            env_file=None,
            live=False,
        )
        google = next(row for row in status["providers"] if row["provider"] == "google_ai_studio_free")
        self.assertEqual(google["local_status"], "missing_env")
        self.assertIn("GEMINI_API_KEY", google["missing_env"])

    def test_collect_status_uses_env_file_for_google_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "openclaw.env"
            env_path.write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")
            status = smoke.collect_status(
                models_path=ROOT / "config" / "models.yaml",
                memory_path=ROOT / "config" / "memory.yaml",
                integrations_path=ROOT / "config" / "integrations.yaml",
                agents_path=ROOT / "config" / "agents.yaml",
                env_file=env_path,
                live=False,
            )
        google = next(row for row in status["providers"] if row["provider"] == "google_ai_studio_free")
        self.assertTrue(google["configured"])
        self.assertEqual(google["resolved_default_model"], "gemini-2.5-flash-lite")

    def test_openai_subscription_session_defaults_to_codex_exec_transport(self):
        status = smoke.collect_status(
            models_path=ROOT / "config" / "models.yaml",
            memory_path=ROOT / "config" / "memory.yaml",
            integrations_path=ROOT / "config" / "integrations.yaml",
            agents_path=ROOT / "config" / "agents.yaml",
            env_file=None,
            live=False,
        )
        openai = next(row for row in status["providers"] if row["provider"] == "openai_subscription_session")
        self.assertEqual(openai["transport"], "codex_exec_session")
        self.assertEqual(openai["default_model"], "gpt-5.3-codex-spark")


if __name__ == "__main__":
    unittest.main()
