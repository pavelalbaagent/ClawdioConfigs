import json
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "scripts" / "reminder_state_machine.py"


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


class ReminderStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_followup_only(self):
        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "create",
                "--id",
                "r1",
                "--message",
                "Pay bill",
                "--when",
                "2026-03-02 20:00",
                "--timezone",
                "America/Guayaquil",
            ]
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])

        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "due",
                "--id",
                "r1",
                "--now",
                "2026-03-03T01:00:01+00:00",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["reminder"]["status"], "awaiting_reply")
        self.assertIsNotNone(payload["reminder"]["next_followup_at"])

        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "followup",
                "--id",
                "r1",
                "--now",
                "2026-03-03T02:00:02+00:00",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["reminder"]["followup_count"], 1)
        self.assertIsNone(payload["reminder"]["next_followup_at"])

        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "followup",
                "--id",
                "r1",
                "--now",
                "2026-03-03T03:00:02+00:00",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload.get("reason"), "not_waiting_reply")

    def test_handle_reply_done_without_id(self):
        run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "create",
                "--id",
                "r2",
                "--message",
                "Call mom",
                "--when",
                "2026-03-02 20:00",
                "--timezone",
                "America/Guayaquil",
            ]
        )
        run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "due",
                "--id",
                "r2",
                "--now",
                "2026-03-03T01:00:01+00:00",
            ]
        )

        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "handle-reply",
                "--text",
                "done",
                "--now",
                "2026-03-03T01:01:00+00:00",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["reminder"]["status"], "done")

    def test_handle_reply_defer_without_id(self):
        run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "create",
                "--id",
                "r3",
                "--message",
                "Send email",
                "--when",
                "2026-03-02 20:00",
                "--timezone",
                "America/Guayaquil",
            ]
        )
        run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "due",
                "--id",
                "r3",
                "--now",
                "2026-03-03T01:00:01+00:00",
            ]
        )

        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "handle-reply",
                "--text",
                "defer until 2026-03-03 09:30",
                "--now",
                "2026-03-03T01:05:00+00:00",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["reminder"]["status"], "pending")
        self.assertEqual(payload["reminder"]["followup_count"], 0)

    def test_handle_reply_ambiguous(self):
        for rid in ("r4", "r5"):
            run_cmd(
                [
                    "--state-file",
                    str(self.state_file),
                    "create",
                    "--id",
                    rid,
                    "--message",
                    f"Task {rid}",
                    "--when",
                    "2026-03-02 20:00",
                    "--timezone",
                    "America/Guayaquil",
                ]
            )
            run_cmd(
                [
                    "--state-file",
                    str(self.state_file),
                    "due",
                    "--id",
                    rid,
                    "--now",
                    "2026-03-03T01:00:01+00:00",
                ]
            )

        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "handle-reply",
                "--text",
                "done",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error"], "ambiguous_open_reminders")
        self.assertEqual(len(payload["candidate_ids"]), 2)

    def test_create_from_text(self):
        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "create-from-text",
                "--id",
                "r6",
                "--text",
                "remind me review plan at 20:00",
                "--timezone",
                "America/Guayaquil",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["reminder"]["id"], "r6")
        self.assertEqual(payload["reminder"]["message"], "review plan")

    def test_create_from_text_relative_time(self):
        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "create-from-text",
                "--id",
                "r7",
                "--text",
                "remind me stretch in 1 hour",
                "--timezone",
                "America/Guayaquil",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["reminder"]["id"], "r7")
        self.assertEqual(payload["reminder"]["message"], "stretch")

        created_at = datetime.fromisoformat(payload["reminder"]["created_at"])
        remind_at = datetime.fromisoformat(payload["reminder"]["remind_at"])
        delta_seconds = (remind_at - created_at).total_seconds()
        self.assertGreaterEqual(delta_seconds, 3500)
        self.assertLessEqual(delta_seconds, 3700)

    def test_create_invalid_time_returns_structured_error(self):
        code, payload, _ = run_cmd(
            [
                "--state-file",
                str(self.state_file),
                "create",
                "--id",
                "r8",
                "--message",
                "test",
                "--when",
                "in someday",
                "--timezone",
                "America/Guayaquil",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"], "invalid_time")


if __name__ == "__main__":
    unittest.main()
