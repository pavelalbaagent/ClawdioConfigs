import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))

from space_router import parse_space_hint, route_text  # noqa: E402


class SpaceRouterTests(unittest.TestCase):
    def test_parse_specialist_prefix_sets_agent_and_space(self):
        parsed = parse_space_hint("research: compare openrouter and gemini")

        self.assertTrue(parsed["matched"])
        self.assertTrue(parsed["explicit_agent"])
        self.assertEqual(parsed["agent_id"], "researcher")
        self.assertEqual(parsed["kind"], "core")
        self.assertEqual(parsed["space_key"], "research")
        self.assertEqual(parsed["stripped_text"], "compare openrouter and gemini")

    def test_parse_project_hint_strips_body(self):
        parsed = parse_space_hint("[project:calendar-review] remind me tomorrow")

        self.assertTrue(parsed["matched"])
        self.assertEqual(parsed["kind"], "project")
        self.assertEqual(parsed["space_key"], "projects/calendar-review")
        self.assertEqual(parsed["agent_id"], "assistant")
        self.assertEqual(parsed["stripped_text"], "remind me tomorrow")

    def test_parse_prefix_and_project_hint_keeps_specialist_agent(self):
        parsed = parse_space_hint("coding: [project:calendar-review] implement dashboard route view")

        self.assertTrue(parsed["matched"])
        self.assertEqual(parsed["kind"], "project")
        self.assertEqual(parsed["agent_id"], "builder")
        self.assertEqual(parsed["space_key"], "projects/calendar-review")
        self.assertEqual(parsed["stripped_text"], "implement dashboard route view")

    def test_route_text_resolves_known_project_space(self):
        routed = route_text(
            "[project:calendar-review] review the conflict queue",
            [
                {
                    "id": "space-1",
                    "key": "projects/calendar-review",
                    "project_id": "proj-1",
                    "name": "Calendar Review",
                }
            ],
        )

        self.assertTrue(routed["resolved"])
        self.assertEqual(routed["space_id"], "space-1")
        self.assertEqual(routed["project_id"], "proj-1")
        self.assertEqual(routed["project_name"], "Calendar Review")

    def test_route_text_resolves_core_specialist_without_project_lookup(self):
        routed = route_text("fitness: start today", [])

        self.assertTrue(routed["resolved"])
        self.assertEqual(routed["agent_id"], "fitness_coach")
        self.assertEqual(routed["space_key"], "fitness")
        self.assertEqual(routed["project_id"], None)

    def test_route_text_marks_unknown_project_space_unresolved(self):
        routed = route_text("[project:missing] review the conflict queue", [])

        self.assertFalse(routed["resolved"])
        self.assertEqual(routed["space_id"], None)
        self.assertEqual(routed["space_key"], "projects/missing")


if __name__ == "__main__":
    unittest.main()
