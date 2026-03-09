import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "memory_index_sync.py"
SEARCH_SCRIPT = ROOT / "scripts" / "memory_search.py"
MEMORY_CONFIG = ROOT / "config" / "memory.yaml"


class MemoryRuntimeTests(unittest.TestCase):
    def _hybrid_memory_config(self, workspace: Path) -> Path:
        config_path = workspace / "memory.yaml"
        text = MEMORY_CONFIG.read_text(encoding="utf-8").replace(
            "active_profile: md_only",
            "active_profile: hybrid_124",
            1,
        )
        config_path.write_text(text, encoding="utf-8")
        return config_path

    def run_script(self, script: Path, args: list[str]):
        return subprocess.run(
            ["python3", str(script), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_index_sync_and_keyword_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_path = self._hybrid_memory_config(workspace)
            (workspace / "MEMORY.md").write_text(
                "# MEMORY\n\n## Priorities\nFix the reminder scheduler and stabilize dashboard auth.\n",
                encoding="utf-8",
            )

            sync = self.run_script(
                SYNC_SCRIPT,
                ["--workspace", str(workspace), "--config", str(config_path)],
            )
            self.assertEqual(sync.returncode, 0, msg=sync.stdout + sync.stderr)
            self.assertIn("Sync summary:", sync.stdout)
            self.assertTrue((workspace / ".memory" / "memory.db").exists())

            search = self.run_script(
                SEARCH_SCRIPT,
                [
                    "--workspace",
                    str(workspace),
                    "--config",
                    str(config_path),
                    "--query",
                    "dashboard auth",
                    "--mode",
                    "keyword",
                    "--json",
                ],
            )
            self.assertEqual(search.returncode, 0, msg=search.stdout + search.stderr)
            payload = json.loads(search.stdout)
            self.assertEqual(payload["mode"], "keyword")
            self.assertGreaterEqual(payload["count"], 1)
            self.assertIn("stabilize dashboard auth", json.dumps(payload["results"]).lower())

    def test_auto_search_falls_back_to_keyword_without_openai_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_path = self._hybrid_memory_config(workspace)
            (workspace / "MEMORY.md").write_text(
                "# MEMORY\n\n## Notes\nUse Tailscale and keep reminders deterministic.\n",
                encoding="utf-8",
            )

            sync = self.run_script(
                SYNC_SCRIPT,
                ["--workspace", str(workspace), "--config", str(config_path)],
            )
            self.assertEqual(sync.returncode, 0, msg=sync.stdout + sync.stderr)

            search = self.run_script(
                SEARCH_SCRIPT,
                [
                    "--workspace",
                    str(workspace),
                    "--config",
                    str(config_path),
                    "--query",
                    "deterministic reminders",
                    "--mode",
                    "auto",
                    "--json",
                ],
            )
            self.assertEqual(search.returncode, 0, msg=search.stdout + search.stderr)
            payload = json.loads(search.stdout)
            self.assertEqual(payload["mode"], "keyword")
            self.assertGreaterEqual(payload["count"], 1)


if __name__ == "__main__":
    unittest.main()
