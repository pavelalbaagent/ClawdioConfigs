import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_agent_md.py"
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "bootstrap_agent_md.py"
BASELINE_DIR = ROOT / "baselines" / "agent_md"
BASELINE_CONFIG = ROOT / "config" / "agent_md_baseline.yaml"


class AgentMarkdownBaselineTests(unittest.TestCase):
    def test_baseline_pack_validates(self):
        proc = subprocess.run(
            [
                "python3",
                str(VALIDATE_SCRIPT),
                "--target",
                str(BASELINE_DIR),
                "--config",
                str(BASELINE_CONFIG),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("Agent markdown validation passed", proc.stdout)

    def test_missing_required_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copytree(BASELINE_DIR, tmp_path / "baseline")
            (tmp_path / "baseline" / "SOUL.md").unlink()

            proc = subprocess.run(
                [
                    "python3",
                    str(VALIDATE_SCRIPT),
                    "--target",
                    str(tmp_path / "baseline"),
                    "--config",
                    str(BASELINE_CONFIG),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("missing required file: SOUL.md", proc.stdout)

    def test_bootstrap_renders_today_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            proc = subprocess.run(
                [
                    "python3",
                    str(BOOTSTRAP_SCRIPT),
                    "--source",
                    str(BASELINE_DIR),
                    "--target",
                    str(tmp_path / "workspace"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            soul = (tmp_path / "workspace" / "SOUL.md").read_text(encoding="utf-8")
            self.assertIn(date.today().isoformat(), soul)
            self.assertNotIn("{{TODAY}}", soul)


if __name__ == "__main__":
    unittest.main()
