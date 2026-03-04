import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "scripts" / "reminder_scheduler_adapter.py"


def run_cmd(args):
    proc = subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )
    payload = None
    if proc.stdout.strip():
        payload = json.loads(proc.stdout)
    return proc.returncode, payload, proc.stderr


class ReminderSchedulerAdapterTests(unittest.TestCase):
    def test_translate_enforces_system_event_for_main_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            input_payload = {
                "ok": True,
                "actions": [
                    {
                        "type": "schedule_due",
                        "reminder_id": "r1",
                        "at": "2026-03-04T02:16:03.814773+00:00",
                        "message": "pay bill",
                    }
                ],
            }
            input_path.write_text(json.dumps(input_payload), encoding="utf-8")

            code, payload, _ = run_cmd(
                [
                    "translate",
                    "--input",
                    str(input_path),
                    "--session-target",
                    "main",
                    "--agent-id",
                    "clawdio-main",
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(len(payload["jobs"]), 1)
            job = payload["jobs"][0]
            self.assertEqual(job["payload"]["kind"], "systemEvent")
            self.assertEqual(job["payload"]["text"], "Reminder: pay bill")

    def test_translate_rejects_agent_turn_for_main_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            input_payload = {
                "actions": [
                    {
                        "type": "schedule_due",
                        "reminder_id": "r2",
                        "at": "2026-03-04T03:00:00+00:00",
                        "message": "stretch",
                        "payload_kind": "agentTurn",
                    }
                ]
            }
            input_path.write_text(json.dumps(input_payload), encoding="utf-8")

            code, payload, _ = run_cmd(
                [
                    "translate",
                    "--input",
                    str(input_path),
                    "--session-target",
                    "main",
                ]
            )
            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "invalid_payload_kind_for_main")
            self.assertEqual(payload["required"], "systemEvent")

    def test_validate_job_fails_for_main_agent_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "job.json"
            job_payload = {
                "session_target": "main",
                "payload": {
                    "kind": "agentTurn",
                    "message": "Reminder: do thing",
                },
            }
            input_path.write_text(json.dumps(job_payload), encoding="utf-8")

            code, payload, _ = run_cmd(["validate-job", "--input", str(input_path)])
            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "invalid_payload_kind_for_main")

    def test_validate_job_allows_isolated_agent_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "job.json"
            job_payload = {
                "session_target": "isolated",
                "payload": {
                    "kind": "agentTurn",
                    "message": "Reminder: do thing",
                },
            }
            input_path.write_text(json.dumps(job_payload), encoding="utf-8")

            code, payload, _ = run_cmd(["validate-job", "--input", str(input_path)])
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
