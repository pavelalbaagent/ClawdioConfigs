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
            text = text.replace("active_profile: lean_manual", "active_profile: missing_profile")
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
            text = text.replace("active_profile: hybrid_124", "active_profile: missing_profile")
            memory_path.write_text(text)

            proc = subprocess.run(
                ["python3", str(SCRIPT), "--config-dir", str(tmp_path)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("active memory profile not found", proc.stdout)


if __name__ == "__main__":
    unittest.main()
