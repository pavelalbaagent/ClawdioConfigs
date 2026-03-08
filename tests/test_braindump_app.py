import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "braindump_app.py"


class BraindumpAppTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_add_writes_snapshot_with_category_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "braindump.db"
            snapshot_path = tmp_path / "braindump-snapshot.json"

            proc = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "--snapshot-file",
                    str(snapshot_path),
                    "add",
                    "gift_idea_wife",
                    "perfume",
                    "sampler",
                    "--tags",
                    "gift,wife",
                    "--notes",
                    "birthday candidate",
                    "--json",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)

            item = payload["item"]
            snapshot = payload["snapshot"]
            self.assertEqual(item["category"], "gift_idea_wife")
            self.assertEqual(item["status"], "inbox")
            self.assertEqual(item["review_bucket"], "weekly")
            self.assertEqual(item["tags"], ["gift", "wife"])
            self.assertTrue(item["next_review_at"])
            self.assertEqual(snapshot["counts_by_status"]["inbox"], 1)
            self.assertEqual(snapshot["counts_by_bucket"]["weekly"], 1)
            self.assertEqual(snapshot["counts_by_category"]["gift_idea_wife"], 1)
            self.assertEqual(Path(snapshot["db_path"]), db_path.resolve())
            self.assertEqual(Path(snapshot["snapshot_path"]), snapshot_path.resolve())

    def test_capture_supports_aliases_tags_and_review_bucket(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "braindump.db"

            proc = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "capture",
                    "bd",
                    "gift",
                    "perfume",
                    "sampler",
                    "#birthday",
                    "@monthly",
                    "--json",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            item = json.loads(proc.stdout)["item"]
            self.assertEqual(item["category"], "gift_idea_wife")
            self.assertEqual(item["review_bucket"], "monthly")
            self.assertEqual(item["tags"], ["birthday"])

    def test_review_and_park_reschedules_due_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "braindump.db"
            snapshot_path = tmp_path / "braindump-snapshot.json"

            add = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "--snapshot-file",
                    str(snapshot_path),
                    "add",
                    "tool_to_test",
                    "agentmail",
                    "--json",
                ]
            )
            self.assertEqual(add.returncode, 0, msg=add.stdout + add.stderr)
            item_id = json.loads(add.stdout)["item"]["id"]

            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE braindump_items SET next_review_at = ?, updated_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", item_id),
            )
            conn.commit()
            conn.close()

            review = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "review",
                    "--json",
                ]
            )
            self.assertEqual(review.returncode, 0, msg=review.stdout + review.stderr)
            review_payload = json.loads(review.stdout)
            self.assertEqual(review_payload["count"], 1)
            self.assertEqual(review_payload["items"][0]["id"], item_id)

            park = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "--snapshot-file",
                    str(snapshot_path),
                    "park",
                    "--id",
                    item_id,
                    "--review-bucket",
                    "monthly",
                    "--note",
                    "keep for later",
                    "--json",
                ]
            )
            self.assertEqual(park.returncode, 0, msg=park.stdout + park.stderr)
            park_payload = json.loads(park.stdout)
            parked_item = park_payload["item"]
            self.assertEqual(parked_item["status"], "parked")
            self.assertEqual(parked_item["review_bucket"], "monthly")
            self.assertNotEqual(parked_item["next_review_at"], "2000-01-01T00:00:00+00:00")

            review_after = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "review",
                    "--json",
                ]
            )
            self.assertEqual(review_after.returncode, 0, msg=review_after.stdout + review_after.stderr)
            self.assertEqual(json.loads(review_after.stdout)["count"], 0)

    def test_promote_to_task_and_calendar_updates_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "braindump.db"
            workspace_path = tmp_path / "dashboard-workspace.json"
            calendar_path = tmp_path / "calendar-candidates.json"

            add_task = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "add",
                    "project_idea",
                    "build",
                    "calendar",
                    "bridge",
                    "--json",
                ]
            )
            self.assertEqual(add_task.returncode, 0, msg=add_task.stdout + add_task.stderr)
            task_item_id = json.loads(add_task.stdout)["item"]["id"]

            promote_task = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "promote",
                    "--id",
                    task_item_id,
                    "--to",
                    "task",
                    "--workspace-file",
                    str(workspace_path),
                    "--json",
                ]
            )
            self.assertEqual(promote_task.returncode, 0, msg=promote_task.stdout + promote_task.stderr)
            task_payload = json.loads(promote_task.stdout)
            self.assertEqual(task_payload["item"]["status"], "promoted")
            self.assertEqual(task_payload["item"]["promoted_to_type"], "task")
            self.assertIsNone(task_payload["item"]["next_review_at"])

            workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
            self.assertEqual(len(workspace["tasks"]), 1)
            self.assertEqual(workspace["tasks"][0]["source"], "braindump")

            add_calendar = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "add",
                    "personal_note",
                    "buy",
                    "anniversary",
                    "flowers",
                    "--json",
                ]
            )
            self.assertEqual(add_calendar.returncode, 0, msg=add_calendar.stdout + add_calendar.stderr)
            calendar_item_id = json.loads(add_calendar.stdout)["item"]["id"]

            promote_calendar = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "promote",
                    "--id",
                    calendar_item_id,
                    "--to",
                    "calendar",
                    "--calendar-candidates-file",
                    str(calendar_path),
                    "--json",
                ]
            )
            self.assertEqual(promote_calendar.returncode, 0, msg=promote_calendar.stdout + promote_calendar.stderr)
            calendar_payload = json.loads(promote_calendar.stdout)
            self.assertEqual(calendar_payload["item"]["promoted_to_type"], "calendar")

            calendar_data = json.loads(calendar_path.read_text(encoding="utf-8"))
            self.assertEqual(len(calendar_data["items"]), 1)
            self.assertEqual(calendar_data["items"][0]["source"], "braindump")

    def test_promote_to_project_creates_workspace_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "braindump.db"
            workspace_path = tmp_path / "dashboard-workspace.json"

            add = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "add",
                    "project_idea",
                    "fitness",
                    "logging",
                    "app",
                    "--json",
                ]
            )
            self.assertEqual(add.returncode, 0, msg=add.stdout + add.stderr)
            item_id = json.loads(add.stdout)["item"]["id"]

            promote = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "promote",
                    "--id",
                    item_id,
                    "--to",
                    "project",
                    "--workspace-file",
                    str(workspace_path),
                    "--json",
                ]
            )
            self.assertEqual(promote.returncode, 0, msg=promote.stdout + promote.stderr)
            workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
            project_ids = [row["id"] for row in workspace["projects"]]
            self.assertIn(f"proj-braindump-{item_id}", project_ids)

    def test_archive_marks_item_archived_and_clears_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "braindump.db"

            add = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "add",
                    "someday_maybe",
                    "try",
                    "new",
                    "game",
                    "--json",
                ]
            )
            self.assertEqual(add.returncode, 0, msg=add.stdout + add.stderr)
            item_id = json.loads(add.stdout)["item"]["id"]

            archive = self.run_script(
                [
                    "--db",
                    str(db_path),
                    "archive",
                    "--id",
                    item_id,
                    "--json",
                ]
            )
            self.assertEqual(archive.returncode, 0, msg=archive.stdout + archive.stderr)
            item = json.loads(archive.stdout)["item"]
            self.assertEqual(item["status"], "archived")
            self.assertTrue(item["archived_at"])
            self.assertIsNone(item["next_review_at"])


if __name__ == "__main__":
    unittest.main()
