import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops_guard_review.py"


class OpsGuardReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "contracts" / "braindump").mkdir(parents=True)
        (self.root / "contracts" / "fitness").mkdir(parents=True)
        (self.root / "fitness").mkdir(parents=True)
        (self.root / "fitness" / "logs").mkdir(parents=True)
        (self.root / "telemetry").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)
        (self.root / "docs" / "reviews").mkdir(parents=True)

        for name in (
            "integrations.yaml",
            "memory.yaml",
            "models.yaml",
            "core.yaml",
            "channels.yaml",
            "reminders.yaml",
            "dashboard.yaml",
            "agents.yaml",
            "session_policy.yaml",
            "fitness_agent.yaml",
        ):
            shutil.copy(ROOT / "config" / name, self.root / "config" / name)
        shutil.copy(ROOT / "scripts" / "set_active_profiles.py", self.root / "scripts" / "set_active_profiles.py")
        shutil.copy(
            ROOT / "contracts" / "braindump" / "sqlite_schema.sql",
            self.root / "contracts" / "braindump" / "sqlite_schema.sql",
        )
        shutil.copy(
            ROOT / "contracts" / "fitness" / "sqlite_schema.sql",
            self.root / "contracts" / "fitness" / "sqlite_schema.sql",
        )
        for name in ("ATHLETE_PROFILE.md", "PROGRAM.md", "EXERCISE_LIBRARY.md", "RULES.md", "SESSION_QUEUE.md"):
            shutil.copy(ROOT / "fitness" / name, self.root / "fitness" / name)

        now = datetime.now(timezone.utc)
        (self.root / "telemetry" / "model-calls.ndjson").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "ts": (now - timedelta(hours=2)).isoformat(),
                            "agent_id": "assistant",
                            "task_id": "t-001",
                            "lane": "L1_low_cost",
                            "provider": "google_ai_studio_free",
                            "model": "gemini-2.5-flash-lite",
                            "prompt_tokens": 120,
                            "completion_tokens": 40,
                            "latency_ms": 800,
                            "status": "ok",
                            "estimated_cost_usd": 0.0,
                        }
                    ),
                    json.dumps(
                        {
                            "ts": (now - timedelta(hours=1)).isoformat(),
                            "agent_id": "builder",
                            "task_id": "t-002",
                            "lane": "L3_heavy",
                            "provider": "openai_subscription_session",
                            "model": "gpt-5.4",
                            "prompt_tokens": 1000,
                            "completion_tokens": 400,
                            "latency_ms": 2400,
                            "status": "ok",
                            "estimated_cost_usd": 0.12,
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.root / "data" / "dashboard-workspace.json").write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "proj-paused",
                            "name": "Paused Cleanup",
                            "status": "paused",
                            "description": "Old paused project",
                            "owner": "pavel",
                            "created_at": (now - timedelta(days=20)).isoformat(),
                            "updated_at": (now - timedelta(days=20)).isoformat(),
                        }
                    ],
                    "spaces": [],
                    "tasks": [],
                    "runs": [],
                    "approvals": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        old_review = self.root / "docs" / "reviews" / "2026-01-01-daily_ops_review.md"
        old_review.write_text("# old review\n", encoding="utf-8")
        stale_temp = self.root / "data" / "tmp-stale.tmp"
        stale_temp.write_text("temp\n", encoding="utf-8")
        old_ts = (now - timedelta(days=40)).timestamp()
        os.utime(old_review, (old_ts, old_ts))
        os.utime(stale_temp, (old_ts, old_ts))

    def tearDown(self):
        self.tmp.cleanup()

    def test_review_generates_status_and_markdown(self):
        status_path = self.root / "data" / "continuous-improvement-status.json"
        review_dir = self.root / "docs" / "reviews"
        proc = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--root",
                str(self.root),
                "--mode",
                "daily_ops_review",
                "--status-file",
                str(status_path),
                "--review-dir",
                str(review_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "daily_ops_review")
        self.assertTrue(status_path.exists())
        self.assertTrue(Path(payload["report_path"]).exists())
        self.assertTrue(Path(payload["history_path"]).exists())
        self.assertIn("usage", payload)
        self.assertGreaterEqual(payload["usage"]["overall"]["total_tokens"], 1560)
        agent_ids = [row["agent_id"] for row in payload["usage"]["by_agent"]]
        self.assertIn("assistant", agent_ids)
        self.assertIn("builder", agent_ids)
        self.assertTrue(payload["directive_candidates"])
        self.assertTrue(payload["cleanup_candidates"])


if __name__ == "__main__":
    unittest.main()
