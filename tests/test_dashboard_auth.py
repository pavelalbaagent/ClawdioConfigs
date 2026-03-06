import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "dashboard"))

from backend import DashboardBackend  # noqa: E402
from server import DashboardAuthManager  # noqa: E402


class DashboardAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        (self.tmp_path / "config").mkdir(parents=True)
        shutil.copy(ROOT / "config" / "dashboard.yaml", self.tmp_path / "config" / "dashboard.yaml")
        self.backend = DashboardBackend(root=self.tmp_path)
        self.auth = DashboardAuthManager(self.backend)

    def tearDown(self):
        self.tmp.cleanup()

    def _handler(self, **headers):
        return SimpleNamespace(headers=headers)

    def test_missing_required_token_fails_closed(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENCLAW_DASHBOARD_TOKEN", None)
            auth_ok, settings, expected_token, source, _ = self.auth.check_request(self._handler())
            self.assertFalse(auth_ok)
            self.assertTrue(settings["require_token"])
            self.assertEqual(expected_token, "")
            self.assertEqual(source, "missing")

            status = self.auth.status_for_request(self._handler())
            self.assertFalse(status["configured"])

            login = self.auth.login("anything")
            self.assertFalse(login["ok"])
            self.assertIn("dashboard token is not configured", login["error"])

    def test_env_token_login_creates_session(self):
        with mock.patch.dict(os.environ, {"OPENCLAW_DASHBOARD_TOKEN": "secret-token"}, clear=False):
            result = self.auth.login("secret-token")
            self.assertTrue(result["ok"])
            self.assertEqual(result["token_source"], "env")

            cookie = f"openclaw_dash_session={result['session_id']}"
            auth_ok, _, _, _, session_id = self.auth.check_request(self._handler(Cookie=cookie))
            self.assertTrue(auth_ok)
            self.assertEqual(session_id, result["session_id"])

    def test_generated_token_requires_explicit_dev_mode(self):
        self.backend.set_dashboard_flags(auth_allow_generated_token=True)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENCLAW_DASHBOARD_TOKEN", None)
            startup = self.auth.startup_status()
            self.assertTrue(startup["configured"])
            self.assertEqual(startup["token_source"], "generated")
            self.assertTrue(startup["token"])

            login = self.auth.login(startup["token"])
            self.assertTrue(login["ok"])
            self.assertEqual(login["token_source"], "generated")


if __name__ == "__main__":
    unittest.main()
