import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "personal_task_runtime.py"
sys.path.insert(0, str(ROOT / "scripts"))
import personal_task_runtime as task_runtime  # noqa: E402


class PersonalTaskRuntimeTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_snapshot_with_fixture_writes_status(self):
        fixture = {
            "tasks": [
                {
                    "id": "1",
                    "content": "Pay insurance",
                    "priority": 3,
                    "due": {"date": "2026-03-10", "string": "tomorrow"},
                },
                {
                    "id": "2",
                    "content": "Buy gift",
                    "priority": 2,
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "todoist-fixture.json"
            status_path = tmp_path / "personal-task-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--status-file",
                    str(status_path),
                    "--json",
                    "snapshot",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["open_count"], 2)
            self.assertTrue(status_path.exists())

    def test_create_complete_and_defer_with_fixture(self):
        fixture = {
            "tasks": [
                {
                    "id": "1",
                    "content": "Call bank",
                    "priority": 2,
                    "due": {"date": "2026-03-10"},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "todoist-fixture.json"
            status_path = tmp_path / "personal-task-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            created = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--status-file",
                    str(status_path),
                    "--json",
                    "create",
                    "--title",
                    "Buy groceries",
                    "--due-string",
                    "tomorrow 6pm",
                    "--apply",
                ]
            )
            self.assertEqual(created.returncode, 0, msg=created.stdout + created.stderr)
            created_payload = json.loads(created.stdout)
            self.assertEqual(created_payload["summary"]["open_count"], 2)

            deferred = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--status-file",
                    str(status_path),
                    "--json",
                    "defer",
                    "--task-id",
                    "1",
                    "--due-date",
                    "2026-03-15",
                    "--apply",
                ]
            )
            self.assertEqual(deferred.returncode, 0, msg=deferred.stdout + deferred.stderr)
            deferred_payload = json.loads(deferred.stdout)
            self.assertEqual(deferred_payload["recent_results"][0]["status"], "updated")

            completed = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--status-file",
                    str(status_path),
                    "--json",
                    "complete",
                    "--task-id",
                    "1",
                    "--apply",
                ]
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stdout + completed.stderr)
            completed_payload = json.loads(completed.stdout)
            self.assertEqual(completed_payload["recent_results"][0]["status"], "completed")

    def test_build_due_payload_accepts_all_three_modes(self):
        due_string = task_runtime.build_defer_payload(due_string="tomorrow", due_datetime=None, due_date=None)
        self.assertEqual(due_string["due_string"], "tomorrow")

        due_datetime = task_runtime.build_defer_payload(
            due_string=None, due_datetime="2026-03-10T18:00:00-05:00", due_date=None
        )
        self.assertEqual(due_datetime["due_datetime"], "2026-03-10T18:00:00-05:00")

        due_date = task_runtime.build_defer_payload(due_string=None, due_datetime=None, due_date="2026-03-10")
        self.assertEqual(due_date["due_date"], "2026-03-10")


if __name__ == "__main__":
    unittest.main()
