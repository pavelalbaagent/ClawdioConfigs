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
            (workspace / "MEMORY.md").write_text(
                "# MEMORY\n\n## Priorities\nFix the reminder scheduler and stabilize dashboard auth.\n",
                encoding="utf-8",
            )

            sync = self.run_script(
                SYNC_SCRIPT,
                ["--workspace", str(workspace), "--config", str(MEMORY_CONFIG)],
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
                    str(MEMORY_CONFIG),
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
            (workspace / "MEMORY.md").write_text(
                "# MEMORY\n\n## Notes\nUse Tailscale and keep reminders deterministic.\n",
                encoding="utf-8",
            )

            sync = self.run_script(
                SYNC_SCRIPT,
                ["--workspace", str(workspace), "--config", str(MEMORY_CONFIG)],
            )
            self.assertEqual(sync.returncode, 0, msg=sync.stdout + sync.stderr)

            search = self.run_script(
                SEARCH_SCRIPT,
                [
                    "--workspace",
                    str(workspace),
                    "--config",
                    str(MEMORY_CONFIG),
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
