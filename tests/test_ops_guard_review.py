import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops_guard_review.py"


class OpsGuardReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "contracts" / "braindump").mkdir(parents=True)
        (self.root / "telemetry").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)

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
        ):
            shutil.copy(ROOT / "config" / name, self.root / "config" / name)
        shutil.copy(ROOT / "scripts" / "set_active_profiles.py", self.root / "scripts" / "set_active_profiles.py")
        shutil.copy(
            ROOT / "contracts" / "braindump" / "sqlite_schema.sql",
            self.root / "contracts" / "braindump" / "sqlite_schema.sql",
        )

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


if __name__ == "__main__":
    unittest.main()
