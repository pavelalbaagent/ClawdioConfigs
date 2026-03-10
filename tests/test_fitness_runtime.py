import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))

import fitness_runtime  # noqa: E402


class FitnessRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "contracts" / "fitness").mkdir(parents=True)
        (self.root / "fitness").mkdir(parents=True)
        (self.root / "fitness" / "logs").mkdir(parents=True)
        (self.root / "data").mkdir(parents=True)
        (self.root / ".memory").mkdir(parents=True)

        shutil.copy(ROOT / "config" / "fitness_agent.yaml", self.root / "config" / "fitness_agent.yaml")
        shutil.copy(
            ROOT / "contracts" / "fitness" / "sqlite_schema.sql",
            self.root / "contracts" / "fitness" / "sqlite_schema.sql",
        )
        for name in ("ATHLETE_PROFILE.md", "PROGRAM.md", "EXERCISE_LIBRARY.md", "RULES.md", "SESSION_QUEUE.md"):
            shutil.copy(ROOT / "fitness" / name, self.root / "fitness" / name)

        self.runtime = fitness_runtime.FitnessRuntime(root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_today_returns_next_main_session(self):
        result = self.runtime.today()

        self.assertIn("Today's workout plan", result["reply_text"])
        self.assertEqual(result["status"]["today_plan"]["plan"]["code"], "M1")
        self.assertEqual(result["status"]["today_plan"]["plan"]["title"], "Mon (Bench 1)")

    def test_runtime_reloads_canonical_program_without_reinstantiation(self):
        original = (self.root / "fitness" / "PROGRAM.md").read_text(encoding="utf-8")
        updated = original.replace("### M1: Mon (Bench 1)", "### M1: Mon (Bench 1 Reloaded)", 1)
        (self.root / "fitness" / "PROGRAM.md").write_text(updated, encoding="utf-8")

        result = self.runtime.today()

        self.assertEqual(result["status"]["today_plan"]["plan"]["title"], "Mon (Bench 1 Reloaded)")
        self.assertIn("Mon (Bench 1 Reloaded)", result["reply_text"])

    def test_start_log_and_finish_workout_cycle(self):
        started = self.runtime.start()
        self.assertTrue(started["created"])
        self.assertEqual(started["session"]["training_day_code"], "M1")

        logged = self.runtime.log("bb curl 8 reps 20kg bb total")
        self.assertEqual(len(logged["created_sets"]), 1)
        self.assertEqual(logged["created_sets"][0]["exercise_code"], "barbell_curl")

        finished = self.runtime.finish()
        self.assertIn("Finished workout", finished["reply_text"])
        self.assertEqual(finished["next_main_code"], "M2")
        self.assertTrue(Path(finished["summary_path"]).exists())

    def test_myorep_log_creates_activation_and_minis(self):
        self.runtime.start()

        logged = self.runtime.log("log myoreps hammer curl 7.5kg each activation 18 then 5+4+4")

        self.assertEqual(len(logged["created_sets"]), 4)
        self.assertEqual(logged["created_sets"][0]["set_type"], "myorep_activation")
        self.assertEqual(logged["created_sets"][1]["set_type"], "myorep_mini")

    def test_superset_log_creates_two_linked_sets(self):
        self.runtime.start()

        logged = self.runtime.log(
            "log superset A1 db incline press 12 reps 12.5kg each and A2 hammer curl 15 reps 7.5kg each"
        )

        self.assertEqual(len(logged["created_sets"]), 2)
        self.assertEqual(logged["created_sets"][0]["superset_label"], "A1")
        self.assertEqual(logged["created_sets"][1]["superset_label"], "A2")

    def test_bb_side_requires_known_empty_barbell_weight(self):
        self.runtime.start()

        with self.assertRaises(ValueError):
            self.runtime.log("log bb curl 8 reps 5kg bb side")

        updated = self.runtime.set_barbell_empty(10.0)
        self.assertEqual(updated["barbell_empty_weight_kg"], 10.0)

        logged = self.runtime.log("log bb curl 8 reps 5kg bb side")
        self.assertEqual(logged["created_sets"][0]["weight_kg"], 20.0)


if __name__ == "__main__":
    unittest.main()
