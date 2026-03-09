import fcntl
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "memory_sync_runner.py"


class MemorySyncRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "contracts" / "memory").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "baselines" / "agent_md").mkdir(parents=True)

        shutil.copy(ROOT / "config" / "memory.yaml", self.root / "config" / "memory.yaml")
        shutil.copy(ROOT / "scripts" / "memory_index_sync.py", self.root / "scripts" / "memory_index_sync.py")
        shutil.copy(ROOT / "contracts" / "memory" / "sqlite_schema.sql", self.root / "contracts" / "memory" / "sqlite_schema.sql")
        (self.root / "baselines" / "agent_md" / "MEMORY.md").write_text(
            "# MEMORY\n\n## Priorities\nKeep reminders deterministic and provider routing cheap.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_runner_writes_status_snapshot(self):
        status_path = self.root / "data" / "memory-sync-status.json"
        proc = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--root",
                str(self.root),
                "--config",
                str(self.root / "config" / "memory.yaml"),
                "--status-file",
                str(status_path),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile"], "hybrid_124")
        self.assertTrue(status_path.exists())

    def test_runner_skips_when_lock_is_held(self):
        status_path = self.root / "data" / "memory-sync-status.json"
        lock_dir = self.root / ".memory"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "memory-sync.lock"
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--root",
                    str(self.root),
                    "--config",
                    str(self.root / "config" / "memory.yaml"),
                    "--status-file",
                    str(status_path),
                    "--lock-timeout-seconds",
                    "0",
                    "--json",
                ],
                capture_output=True,
                text=True,
            )
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["skipped"])
        self.assertEqual(payload["reason"], "lock_held")
        self.assertFalse(status_path.exists())


if __name__ == "__main__":
    unittest.main()
