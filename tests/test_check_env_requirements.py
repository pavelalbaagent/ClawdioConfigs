import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_env_requirements.py"


class CheckEnvRequirementsTests(unittest.TestCase):
    def run_script(self, args):
        proc = subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )
        return proc

    def test_env_file_strict_passes_with_required_values(self):
        env_text = "\n".join(
            [
                "GOOGLE_CLIENT_ID=test_google_client_id",
                "GOOGLE_CLIENT_SECRET=test_google_client_secret",
                "GOOGLE_REFRESH_TOKEN=test_google_refresh_token",
                "GMAIL_USER_EMAIL=test@example.com",
                "GOOGLE_DRIVE_ROOT_FOLDER_ID=test_drive_folder",
                "GITHUB_TOKEN=test_github_token",
                "GITHUB_OWNER=test_owner",
                "PERSONAL_TASK_PROVIDER=todoist",
                "TODOIST_API_TOKEN=test_todoist_token",
                "AGENT_TASK_PROVIDER=asana",
                "ASANA_PERSONAL_ACCESS_TOKEN=test_asana_token",
                "ASANA_WORKSPACE_GID=test_workspace_gid",
                "N8N_BASE_URL=https://n8n.example.com",
                "N8N_API_KEY=test_n8n_api_key",
                "N8N_WEBHOOK_SECRET=test_n8n_webhook_secret",
                "OPENAI_API_KEY=test_openai_api_key",
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "runtime.env"
            env_path.write_text(env_text + "\n", encoding="utf-8")

            proc = self.run_script(["--env-file", str(env_path), "--strict"])
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertIn("All required vars for enabled modules are set", proc.stdout)

    def test_include_optional_prints_brave_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "runtime.env"
            env_path.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

            proc = self.run_script(["--env-file", str(env_path), "--include-optional"])
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertIn("BRAVE_SEARCH_API_KEY=", proc.stdout)

    def test_addons_profile_reports_missing_required_vars_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "runtime.env"
            env_path.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

            proc = self.run_script(
                [
                    "--env-file",
                    str(env_path),
                    "--addons-profile",
                    "addons_search_brave",
                    "--strict",
                ]
            )
            self.assertNotEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertIn("Add-ons:", proc.stdout)
            self.assertIn("brave_search", proc.stdout)
            self.assertIn("BRAVE_SEARCH_API_KEY=MISSING", proc.stdout)


if __name__ == "__main__":
    unittest.main()
