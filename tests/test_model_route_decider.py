import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "model_route_decider.py"
CONFIG = ROOT / "config" / "models.yaml"


class ModelRouteDeciderTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), "--config", str(CONFIG), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )

    def test_list_modes_includes_balanced_default(self):
        proc = self.run_script(["--list-modes"])
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("balanced_default", proc.stdout)

    def test_coding_and_integration_prefers_l2(self):
        proc = self.run_script(["--situation", "coding_and_integration", "--json"])
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["preferred_lane"], "L2_balanced")
        self.assertIn("openai_subscription_session", data["provider_preference"])
        self.assertNotIn("codex_subscription_cli", data["provider_preference"])
        self.assertEqual(data["provider_candidates"][0]["model"], "gpt-5.3-codex-spark")

    def test_strict_cost_limits_fallback_to_l2(self):
        proc = self.run_script(
            ["--mode", "strict_cost", "--situation", "coding_and_integration", "--json"]
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertNotIn("L3_heavy", data["fallback_lanes"])

    def test_intent_tag_resolves_architecture(self):
        proc = self.run_script(["--intent-tag", "architecture", "--json"])
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["situation"], "architecture_or_high_ambiguity")
        self.assertEqual(data["preferred_lane"], "L3_heavy")
        self.assertTrue(data["approval_required"])
        self.assertEqual(data["provider_candidates"][0]["model"], "gpt-5.4")

    def test_builder_agent_gets_codex_specific_openai_model(self):
        proc = self.run_script(["--agent", "builder", "--situation", "coding_and_integration", "--json"])
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["provider_candidates"][0]["provider"], "openai_subscription_session")
        self.assertEqual(data["provider_candidates"][0]["model"], "gpt-5.1-codex-mini")


if __name__ == "__main__":
    unittest.main()
