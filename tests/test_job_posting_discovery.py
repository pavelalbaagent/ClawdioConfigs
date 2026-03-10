import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "job_posting_discovery.py"
CONFIG = ROOT / "config" / "job_search.yaml"

sys.path.insert(0, str(ROOT / "scripts"))

import job_posting_discovery as discovery  # noqa: E402


class JobPostingDiscoveryTests(unittest.TestCase):
    def test_canonicalize_url_removes_tracking_query(self):
        value = discovery.canonicalize_url("https://www.linkedin.com/jobs/view/123456789/?trackingId=abc#fragment")
        self.assertEqual(value, "https://www.linkedin.com/jobs/view/123456789")

    def test_discover_with_fixtures_writes_inbox_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            inbox_dir = tmp_path / "inbox"
            status_path = tmp_path / "job-discovery-status.json"
            state_path = tmp_path / "job-discovery-state.json"
            config_path = tmp_path / "job_search.yaml"
            fixtures_path = tmp_path / "fixtures.json"

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("saved_postings_dir: data/job-search/inbox", f"saved_postings_dir: {inbox_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-discovery-status.json",
                f"latest_status_file: {status_path}",
                1,
            )
            config_text = config_text.replace("state_file: data/job-search-discovery-state.json", f"state_file: {state_path}", 1)
            config_path.write_text(config_text, encoding="utf-8")

            fixtures_path.write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "query": 'site:linkedin.com/jobs/view ("ai enablement") remote',
                                "results": [
                                    {
                                        "url": "https://www.linkedin.com/jobs/view/123456789/",
                                        "title": "AI Enablement Consultant",
                                        "snippet": "Global remote across LATAM including Ecuador.",
                                        "content_text": "AI Enablement Consultant Global remote across LATAM including Ecuador. Workflow automation and stakeholder alignment.",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--config",
                    str(config_path),
                    "--fixtures-file",
                    str(fixtures_path),
                    "--json",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["summary"]["saved_count"], 1)
            self.assertTrue(status_path.exists())
            self.assertTrue(state_path.exists())
            saved_file = Path(payload["saved_postings"][0]["saved_path"])
            self.assertTrue(saved_file.exists())
            self.assertIn("Source URL: https://www.linkedin.com/jobs/view/123456789", saved_file.read_text(encoding="utf-8"))

    def test_second_run_skips_duplicate_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            inbox_dir = tmp_path / "inbox"
            status_path = tmp_path / "job-discovery-status.json"
            state_path = tmp_path / "job-discovery-state.json"
            config_path = tmp_path / "job_search.yaml"
            fixtures_path = tmp_path / "fixtures.json"

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("saved_postings_dir: data/job-search/inbox", f"saved_postings_dir: {inbox_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-discovery-status.json",
                f"latest_status_file: {status_path}",
                1,
            )
            config_text = config_text.replace("state_file: data/job-search-discovery-state.json", f"state_file: {state_path}", 1)
            config_path.write_text(config_text, encoding="utf-8")

            fixtures_path.write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "query": 'site:linkedin.com/jobs/view ("ai enablement") remote',
                                "results": [
                                    {
                                        "url": "https://www.linkedin.com/jobs/view/999999/",
                                        "title": "AI Workflow Consultant",
                                        "snippet": "Remote-first role.",
                                        "content_text": "AI Workflow Consultant Remote-first role with automation and Python.",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            first = discovery.discover(config_path=config_path, fixtures_file=fixtures_path)
            second = discovery.discover(config_path=config_path, fixtures_file=fixtures_path)

            self.assertEqual(first["summary"]["saved_count"], 1)
            self.assertEqual(second["summary"]["saved_count"], 0)
            self.assertEqual(second["summary"]["duplicate_count"], 1)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("https://www.linkedin.com/jobs/view/999999", state["seen_urls"])


if __name__ == "__main__":
    unittest.main()
