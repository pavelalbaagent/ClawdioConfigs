import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from env_file_utils import dump_env_text, load_env_file, parse_env_text  # noqa: E402


class EnvFileUtilsTests(unittest.TestCase):
    def test_parse_env_text_strips_quotes_and_export(self):
        values = parse_env_text(
            "\n".join(
                [
                    "# comment",
                    "export GEMINI_API_KEY=\"abc123\"",
                    "OPENCLAW_DASHBOARD_TOKEN='secret token'",
                ]
            )
        )
        self.assertEqual(values["GEMINI_API_KEY"], "abc123")
        self.assertEqual(values["OPENCLAW_DASHBOARD_TOKEN"], "secret token")

    def test_dump_env_text_quotes_only_when_needed(self):
        rendered = dump_env_text(
            {
                "SAFE": "abc123",
                "WITH_SPACE": "secret token",
            },
            sort_keys=True,
            header_comment=None,
        )
        self.assertIn("SAFE=abc123", rendered)
        self.assertIn('WITH_SPACE="secret token"', rendered)

    def test_load_env_file_rejects_invalid_lines_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.env"
            path.write_text("GEMINI_API_KEY=abc123\nbarevalue\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_env_file(path, strict=True)


if __name__ == "__main__":
    unittest.main()
