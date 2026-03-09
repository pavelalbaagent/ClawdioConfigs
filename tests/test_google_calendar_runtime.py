import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "google_calendar_runtime.py"
sys.path.insert(0, str(ROOT / "scripts"))
import google_calendar_runtime as calendar_runtime  # noqa: E402


class GoogleCalendarRuntimeTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_snapshot_with_fixture_writes_status_file(self):
        base = datetime.now(timezone.utc) + timedelta(days=1)
        next_day = base + timedelta(days=1)
        fixture = {
            "events": [
                {
                    "id": "evt-1",
                    "status": "confirmed",
                    "summary": "Advising call",
                    "start": {"dateTime": base.replace(hour=15, minute=0, second=0, microsecond=0).isoformat()},
                    "end": {"dateTime": base.replace(hour=16, minute=0, second=0, microsecond=0).isoformat()},
                },
                {
                    "id": "evt-2",
                    "status": "confirmed",
                    "summary": "School holiday",
                    "start": {"date": next_day.date().isoformat()},
                    "end": {"date": (next_day.date() + timedelta(days=1)).isoformat()},
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "calendar-fixture.json"
            status_path = tmp_path / "calendar-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--calendar-id",
                    "primary",
                    "--status-file",
                    str(status_path),
                    "--json",
                    "snapshot",
                    "--window-days",
                    "30",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["action"], "snapshot")
            self.assertEqual(payload["summary"]["upcoming_count"], 2)
            self.assertTrue(status_path.exists())

    def test_create_event_apply_with_fixture_adds_upcoming_event(self):
        fixture = {"events": []}

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "calendar-fixture.json"
            status_path = tmp_path / "calendar-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--calendar-id",
                    "primary",
                    "--status-file",
                    str(status_path),
                    "--json",
                    "create",
                    "--title",
                    "Doctor appointment",
                    "--start-at",
                    "2026-03-10T09:00:00-05:00",
                    "--end-at",
                    "2026-03-10T09:30:00-05:00",
                    "--apply",
                    "--window-days",
                    "30",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["created_count"], 1)
            self.assertEqual(payload["recent_results"][0]["status"], "scheduled")
            self.assertEqual(payload["summary"]["upcoming_count"], 1)

    def test_update_event_apply_with_fixture_updates_existing_event(self):
        fixture = {
            "events": [
                {
                    "id": "evt-1",
                    "status": "confirmed",
                    "summary": "Old title",
                    "start": {"dateTime": "2026-03-10T15:00:00+00:00"},
                    "end": {"dateTime": "2026-03-10T16:00:00+00:00"},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "calendar-fixture.json"
            status_path = tmp_path / "calendar-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--calendar-id",
                    "primary",
                    "--status-file",
                    str(status_path),
                    "--json",
                    "update",
                    "--event-id",
                    "evt-1",
                    "--title",
                    "Updated title",
                    "--apply",
                    "--window-days",
                    "30",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["updated_count"], 1)
            self.assertEqual(payload["recent_results"][0]["event_id"], "evt-1")
            self.assertEqual(payload["upcoming_events"][0]["summary"], "Updated title")

    def test_apply_candidates_creates_event_and_updates_candidate_file(self):
        fixture = {"events": []}
        candidates = {
            "items": [
                {
                    "id": "cal-1",
                    "title": "Parent teacher meeting",
                    "status": "approved",
                    "start_at": "2026-03-11T18:00:00-05:00",
                    "end_at": "2026-03-11T18:30:00-05:00",
                    "timezone": "America/Guayaquil",
                },
                {
                    "id": "cal-2",
                    "title": "Unscheduled idea",
                    "status": "proposed",
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "calendar-fixture.json"
            candidates_path = tmp_path / "calendar-candidates.json"
            status_path = tmp_path / "calendar-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--calendar-id",
                    "primary",
                    "--status-file",
                    str(status_path),
                    "--json",
                    "apply-candidates",
                    "--candidates-file",
                    str(candidates_path),
                    "--apply",
                    "--window-days",
                    "30",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["created_count"], 1)
            self.assertEqual(payload["summary"]["skipped_count"], 1)
            self.assertEqual(payload["summary"]["pending_candidate_count"], 1)

            updated_candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            first = updated_candidates["items"][0]
            second = updated_candidates["items"][1]
            self.assertEqual(first["status"], "scheduled")
            self.assertTrue(first["event_id"])
            self.assertEqual(second["status"], "proposed")
            self.assertEqual(second["last_apply_status"], "skipped")

    def test_build_event_payload_supports_all_day_default_end(self):
        spec = calendar_runtime.build_event_payload(
            title="Holiday",
            description=None,
            location=None,
            attendees=[],
            start_at=None,
            end_at=None,
            start_date="2026-03-15",
            end_date=None,
            timezone_name="America/Guayaquil",
        )

        self.assertEqual(spec.time_mode, "all_day")
        self.assertEqual(spec.payload["start"]["date"], "2026-03-15")
        self.assertEqual(spec.payload["end"]["date"], "2026-03-16")


if __name__ == "__main__":
    unittest.main()
