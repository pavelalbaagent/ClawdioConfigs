import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gmail_inbox_processor.py"
sys.path.insert(0, str(ROOT / "scripts"))
import gmail_inbox_processor as gmail_runtime  # noqa: E402


class GmailInboxProcessorTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def make_message(self, *, message_id: str, thread_id: str, from_value: str, subject: str, body: str, extra_headers=None):
        headers = [
            {"name": "From", "value": from_value},
            {"name": "Subject", "value": subject},
            {"name": "Message-Id", "value": f"<{message_id}@example.test>"},
        ]
        for name, value in (extra_headers or []):
            headers.append({"name": name, "value": value})
        encoded = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8").rstrip("=")
        return {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": ["INBOX"],
            "internalDate": "1710000000000",
            "snippet": body[:80],
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": headers,
                "parts": [
                    {
                        "partId": "0",
                        "mimeType": "text/plain",
                        "filename": "",
                        "body": {"size": len(body), "data": encoded},
                    }
                ],
            },
        }

    def test_extract_message_record_classifies_low_and_high_value_messages(self):
        newsletter = self.make_message(
            message_id="m1",
            thread_id="t1",
            from_value="Digest <newsletter@example.com>",
            subject="Weekly newsletter digest",
            body="This week newsletter digest with unsubscribe links.",
            extra_headers=[("List-Unsubscribe", "<mailto:unsubscribe@example.com>")],
        )
        human = self.make_message(
            message_id="m2",
            thread_id="t2",
            from_value="Alex <alex@example.com>",
            subject="Can you review this today?",
            body="Please review this today and let me know. https://example.com/doc",
        )

        low = gmail_runtime.extract_message_record(newsletter, keep_raw_headers=True)
        high = gmail_runtime.extract_message_record(human, keep_raw_headers=True)

        self.assertEqual(low["action"]["primary_action"], "archive_message")
        self.assertIn("newsletter", low["intent_tags"])
        self.assertEqual(high["action"]["primary_action"], "mark_for_manual_review")
        self.assertIn("promote_task_candidate", high["action"]["secondary_actions"])
        self.assertIn("draft_reply", high["action"]["secondary_actions"])

    def test_run_with_fixture_persists_sqlite_and_skips_processed_messages(self):
        messages = [
            self.make_message(
                message_id="m1",
                thread_id="t1",
                from_value="Digest <newsletter@example.com>",
                subject="Weekly newsletter digest",
                body="This week newsletter digest with unsubscribe links.",
                extra_headers=[("List-Unsubscribe", "<mailto:unsubscribe@example.com>")],
            ),
            self.make_message(
                message_id="m2",
                thread_id="t2",
                from_value="Alex <alex@example.com>",
                subject="Can you review this today?",
                body="Please review this today and let me know.",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "gmail-fixture.json"
            state_db = tmp_path / "inbox.db"
            fixture_path.write_text(json.dumps({"messages": messages}), encoding="utf-8")

            first = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--state-db",
                    str(state_db),
                    "--json",
                ]
            )
            self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
            payload = json.loads(first.stdout)
            self.assertEqual(payload["summary"]["processed_count"], 2)
            self.assertTrue(state_db.exists())

            second = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--state-db",
                    str(state_db),
                    "--json",
                ]
            )
            self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)
            payload_second = json.loads(second.stdout)
            self.assertEqual(payload_second["summary"]["processed_count"], 0)
            self.assertEqual(payload_second["summary"]["skipped_existing_count"], 2)

            conn = sqlite3.connect(state_db)
            stored = conn.execute("SELECT COUNT(*) FROM gmail_messages").fetchone()[0]
            decisions = conn.execute("SELECT COUNT(*) FROM gmail_decisions").fetchone()[0]
            conn.close()
            self.assertEqual(stored, 2)
            self.assertEqual(decisions, 2)

    def test_promote_candidates_writes_workspace_calendar_and_status_files(self):
        messages = [
            self.make_message(
                message_id="m4",
                thread_id="t4",
                from_value="Alex <alex@example.com>",
                subject="Can you join this meeting tomorrow?",
                body="Please join this meeting tomorrow. Zoom link inside.",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "gmail-fixture.json"
            state_db = tmp_path / "inbox.db"
            workspace_path = tmp_path / "dashboard-workspace.json"
            calendar_path = tmp_path / "calendar-candidates.json"
            status_path = tmp_path / "gmail-status.json"
            fixture_path.write_text(json.dumps({"messages": messages}), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--state-db",
                    str(state_db),
                    "--workspace-file",
                    str(workspace_path),
                    "--calendar-candidates-file",
                    str(calendar_path),
                    "--status-file",
                    str(status_path),
                    "--promote-task-candidates",
                    "--promote-calendar-candidates",
                    "--json",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

            workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
            tasks = workspace["tasks"]
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["source"], "gmail_inbox")

            calendar = json.loads(calendar_path.read_text(encoding="utf-8"))
            self.assertEqual(len(calendar["items"]), 1)
            self.assertEqual(calendar["items"][0]["status"], "proposed")

            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertIn("summary", status)
            self.assertIn("promotions", status)

    def test_placeholder_draft_creation_is_explicit(self):
        message = self.make_message(
            message_id="m3",
            thread_id="t3",
            from_value="Alex <alex@example.com>",
            subject="Can you review this?",
            body="Please review this and let me know.",
        )
        record = gmail_runtime.extract_message_record(message, keep_raw_headers=True)
        client = gmail_runtime.FixtureGmailClient([message])

        applied, error_text = gmail_runtime.maybe_apply_actions(
            client,
            record=record,
            apply=True,
            create_placeholder_drafts=True,
        )

        self.assertFalse(applied)
        self.assertIsNone(error_text)
        self.assertEqual(len(client.drafts), 1)


if __name__ == "__main__":
    unittest.main()
