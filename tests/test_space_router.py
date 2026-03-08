import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "scripts"))

from space_router import parse_space_hint, route_text  # noqa: E402


class SpaceRouterTests(unittest.TestCase):
    def test_parse_project_hint_strips_body(self):
        parsed = parse_space_hint("[project:calendar-review] remind me tomorrow")

        self.assertTrue(parsed["matched"])
        self.assertEqual(parsed["kind"], "project")
        self.assertEqual(parsed["space_key"], "projects/calendar-review")
        self.assertEqual(parsed["stripped_text"], "remind me tomorrow")

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

    def test_route_text_marks_unknown_project_space_unresolved(self):
        routed = route_text("[project:missing] review the conflict queue", [])

        self.assertFalse(routed["resolved"])
        self.assertEqual(routed["space_id"], None)
        self.assertEqual(routed["space_key"], "projects/missing")


if __name__ == "__main__":
    unittest.main()
