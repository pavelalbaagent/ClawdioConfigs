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
        (self.root / "data" / "continuous-improvement-history").mkdir(parents=True)

        shutil.copy(ROOT / "config" / "memory.yaml", self.root / "config" / "memory.yaml")
        shutil.copy(ROOT / "config" / "agents.yaml", self.root / "config" / "agents.yaml")
        shutil.copy(ROOT / "config" / "session_policy.yaml", self.root / "config" / "session_policy.yaml")
        shutil.copy(ROOT / "scripts" / "memory_index_sync.py", self.root / "scripts" / "memory_index_sync.py")
        shutil.copy(ROOT / "contracts" / "memory" / "sqlite_schema.sql", self.root / "contracts" / "memory" / "sqlite_schema.sql")
        (self.root / "baselines" / "agent_md" / "MEMORY.md").write_text(
            "# MEMORY\n\n## Priorities\nKeep reminders deterministic and provider routing cheap.\n",
            encoding="utf-8",
        )
        candidate = {
            "generated_at": "2026-03-09T07:30:00+00:00",
            "mode": "daily_ops_review",
            "directive_candidates": [
                {
                    "key": "reserve_heavy_lane_for_hard_work",
                    "scope": "all_agents",
                    "text": "Reserve L3_heavy for genuinely hard work; investigate if heavy-lane use becomes routine.",
                    "safe_to_promote": True,
                    "requires_approval": False,
                }
            ],
            "findings": [
                {
                    "id": "heavy_lane_overuse",
                    "summary": "Heavy-lane usage looks elevated.",
                }
            ],
            "cleanup_candidates": [],
            "report_path": str(self.root / "docs" / "reviews" / "2026-03-09-daily_ops_review.md"),
        }
        for idx, day in enumerate(("2026-03-09", "2026-03-10"), start=0):
            payload = dict(candidate)
            payload["generated_at"] = f"{day}T07:30:00+00:00"
            history_path = self.root / "data" / "continuous-improvement-history" / f"{day}-daily_ops_review.json"
            history_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        latest_status = self.root / "data" / "continuous-improvement-status.json"
        latest_status.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

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
        governance = payload["governance_consolidation"]
        self.assertTrue(governance["ok"])
        self.assertTrue((self.root / "memory" / "SHARED_DIRECTIVES.md").exists())
        self.assertTrue((self.root / "memory" / "SHARED_FINDINGS.md").exists())
        self.assertTrue((self.root / "data" / "knowledge-librarian-status.json").exists())
        directives = (self.root / "memory" / "SHARED_DIRECTIVES.md").read_text(encoding="utf-8")
        self.assertIn("Reserve L3_heavy for genuinely hard work", directives)

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
