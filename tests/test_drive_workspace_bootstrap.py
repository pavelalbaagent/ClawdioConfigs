import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "drive_workspace_bootstrap.py"
sys.path.insert(0, str(ROOT / "scripts"))
import drive_workspace_bootstrap as drive_runtime  # noqa: E402


class DriveWorkspaceBootstrapTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_inspect_workspace_reports_missing_and_apply_creates(self):
        contract = drive_runtime.ensure_dict(
            drive_runtime.load_yaml(ROOT / "contracts" / "drive" / "shared-workspace.yaml")
        )
        client = drive_runtime.FixtureDriveClient(
            root={"id": "root1", "name": "OpenClaw Shared", "mimeType": drive_runtime.FOLDER_MIME},
            children=[
                {"id": "c1", "name": "00_inbox", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c2", "name": "01_working", "mimeType": drive_runtime.FOLDER_MIME},
            ],
        )

        before = drive_runtime.inspect_workspace(client, root_folder_id="root1", contract=contract, apply=False)
        self.assertFalse(before["ok"])
        self.assertIn("02_outputs", before["missing"])

        after = drive_runtime.inspect_workspace(client, root_folder_id="root1", contract=contract, apply=True)
        self.assertTrue(after["ok"])
        self.assertEqual(after["missing"], [])
        self.assertGreaterEqual(len(after["created"]), 1)
        self.assertIn("11_agents", after["nested"])
        self.assertEqual(after["nested"]["11_agents"]["missing"], [])

    def test_strict_fixture_mode_returns_non_zero_for_incomplete_workspace(self):
        fixture = {
            "root": {"id": "root1", "name": "OpenClaw Shared", "mimeType": drive_runtime.FOLDER_MIME},
            "children": [
                {"id": "c1", "name": "00_inbox", "mimeType": drive_runtime.FOLDER_MIME},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "drive-fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--root-folder-id",
                    "root1",
                    "--strict",
                    "--json",
                ]
            )
            self.assertEqual(proc.returncode, 3, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertIn("01_working", payload["missing"])

    def test_status_file_is_written(self):
        fixture = {
            "root": {"id": "root1", "name": "OpenClaw Shared", "mimeType": drive_runtime.FOLDER_MIME},
            "children": [
                {"id": "c1", "name": "00_inbox", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c2", "name": "01_working", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c3", "name": "02_outputs", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c4", "name": "03_reference", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c5", "name": "04_archive", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c6", "name": "10_projects", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c7", "name": "11_agents", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "c8", "name": "12_shared_sources", "mimeType": drive_runtime.FOLDER_MIME},
                {"id": "a1", "name": "assistant", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c7"]},
                {"id": "a2", "name": "researcher", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c7"]},
                {"id": "a3", "name": "builder", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c7"]},
                {"id": "a4", "name": "fitness_coach", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c7"]},
                {"id": "a5", "name": "ops_guard", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c7"]},
                {"id": "s1", "name": "inbox_attachments", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c8"]},
                {"id": "s2", "name": "ai_tools_reference", "mimeType": drive_runtime.FOLDER_MIME, "parents": ["c8"]},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture_path = tmp_path / "drive-fixture.json"
            status_path = tmp_path / "drive-status.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            proc = self.run_script(
                [
                    "--fixtures-file",
                    str(fixture_path),
                    "--root-folder-id",
                    "root1",
                    "--status-file",
                    str(status_path),
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["summary"]["ok"])
            self.assertIn("nested", payload["summary"])


if __name__ == "__main__":
    unittest.main()
