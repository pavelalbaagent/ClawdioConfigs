import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_configs.py"
CONFIG_DIR = ROOT / "config"
CONFIG_FILES = (
    "core",
    "channels",
    "models",
    "integrations",
    "addons",
    "memory",
    "agents",
    "tasks",
    "security",
    "reminders",
    "session_policy",
    "dashboard",
    "job_search",
    "knowledge_sources",
    "research_flow",
)


class ValidateConfigsTests(unittest.TestCase):
    def test_current_config_passes(self):
        proc = subprocess.run(
            ["python3", str(SCRIPT), "--config-dir", str(CONFIG_DIR)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("Config validation passed", proc.stdout)

    def test_invalid_budget_distribution_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            models_path = tmp_path / "models.yaml"
            text = models_path.read_text()
            text = text.replace("L3_heavy_pct: 5", "L3_heavy_pct: 15")
            models_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("model budget distribution must sum to 100", proc.stdout)

    def test_missing_integration_profile_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            integrations_path = tmp_path / "integrations.yaml"
            text = integrations_path.read_text()
            text = text.replace("active_profile: bootstrap_command_center", "active_profile: missing_profile", 1)
            integrations_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("active integration profile not found", proc.stdout)

    def test_missing_memory_profile_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            memory_path = tmp_path / "memory.yaml"
            text = memory_path.read_text()
            text = text.replace("active_profile: hybrid_124", "active_profile: missing_profile", 1)
            memory_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("active memory profile not found", proc.stdout)

    def test_invalid_dashboard_preset_profile_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            dashboard_path = tmp_path / "dashboard.yaml"
            text = dashboard_path.read_text()
            text = text.replace("integrations_profile: bootstrap_core", "integrations_profile: missing_profile", 1)
            dashboard_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("integrations_profile references unknown profile", proc.stdout)

    def test_missing_gmail_inbox_contract_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            integrations_path = tmp_path / "integrations.yaml"
            text = integrations_path.read_text()
            text = text.replace(
                "contract_file: contracts/gmail/inbox-processing-rules.yaml",
                "contract_file: contracts/gmail/missing-rules.yaml",
                1,
            )
            integrations_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("inbox_processing.contract_file file not found", proc.stdout)

    def test_unknown_model_provider_reference_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            models_path = tmp_path / "models.yaml"
            text = models_path.read_text()
            text = text.replace("google_ai_studio_free: gemini-2.5-flash-lite", "unknown_provider: gemini-2.5-flash-lite", 1)
            models_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("provider_models references unknown provider", proc.stdout)

    def test_invalid_job_search_daily_summary_limit_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            job_search_path = tmp_path / "job_search.yaml"
            text = job_search_path.read_text()
            text = text.replace("max_roles_per_section: 10", "max_roles_per_section: 0", 1)
            job_search_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("job_search.job_search.daily_summary.max_roles_per_section must be integer > 0", proc.stdout)

    def test_invalid_job_search_delivery_time_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            job_search_path = tmp_path / "job_search.yaml"
            text = job_search_path.read_text()
            text = text.replace('delivery_time_local: "18:30"', 'delivery_time_local: "1830"', 1)
            job_search_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("job_search.job_search.schedule.delivery_time_local must be HH:MM", proc.stdout)

    def test_invalid_job_search_discovery_provider_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for name in CONFIG_FILES:
                shutil.copy(CONFIG_DIR / f"{name}.yaml", tmp_path / f"{name}.yaml")

            job_search_path = tmp_path / "job_search.yaml"
            text = job_search_path.read_text()
            text = text.replace("brave_search_api", "unknown_search_provider", 1)
            job_search_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("job_search.job_search.discovery.provider_priority references unknown values", proc.stdout)


if __name__ == "__main__":
    unittest.main()
