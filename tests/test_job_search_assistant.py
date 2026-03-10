import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "job_search_assistant.py"
CONFIG = ROOT / "config" / "job_search.yaml"

sys.path.insert(0, str(ROOT / "scripts"))

import job_search_assistant as jobs  # noqa: E402


class JobSearchAssistantTests(unittest.TestCase):
    def test_split_telegram_text_chunks_long_reports(self):
        text = ("Apply Today\n" + ("Role line\n" * 900)).strip()
        parts = jobs.split_telegram_text(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= jobs.TELEGRAM_MESSAGE_CHUNK_LIMIT for part in parts))

    def test_telegram_report_client_send_long_message_sends_all_chunks(self):
        sent_texts: list[str] = []

        def fake_send(self, *, chat_id: str, text: str):
            sent_texts.append(text)
            return {"message_id": len(sent_texts)}

        text = ("Apply Today\n" + ("Role line\n" * 900)).strip()
        client = jobs.TelegramReportClient("test-token")
        with mock.patch.object(jobs.TelegramReportClient, "send_message", autospec=True, side_effect=fake_send):
            responses = client.send_long_message(chat_id="12345", text=text)

        self.assertEqual(len(responses), len(sent_texts))
        self.assertGreater(len(sent_texts), 1)
        self.assertTrue(all(len(part) <= jobs.TELEGRAM_MESSAGE_CHUNK_LIMIT for part in sent_texts))

    def test_triage_posting_recommends_apply_for_strong_latam_fit(self):
        config = jobs.load_config(CONFIG)
        posting = """
        AI Enablement Consultant

        Global remote across LATAM including Ecuador. We need AI adoption, workflow automation,
        stakeholder alignment, cross-functional execution, process improvement, and Python.
        """

        result = jobs.triage_posting(posting, "inline-text", config)

        self.assertEqual(result.recommendation, "apply")
        self.assertEqual(result.eligibility, "direct_yes")
        self.assertGreaterEqual(result.fit_score, 70)
        self.assertIn("Apply now.", result.next_step)

    def test_daily_summary_cli_ranks_saved_postings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "postings"
            triage_dir = tmp_path / "triage"
            summary_dir = tmp_path / "daily"
            latest_status = tmp_path / "job-search-status.json"
            discovery_status = tmp_path / "job-discovery-status.json"
            discovery_state = tmp_path / "job-discovery-state.json"
            config_path = tmp_path / "job_search.yaml"

            input_dir.mkdir()
            (input_dir / "latam_apply.txt").write_text(
                """
                AI Adoption Lead

                Global remote role across LATAM including Ecuador. Looking for AI adoption,
                workflow automation, stakeholder alignment, process improvement, and Python.
                """,
                encoding="utf-8",
            )
            (input_dir / "manual_review.txt").write_text(
                """
                Solutions Consultant

                Remote-first role with U.S. time zone overlap. You will lead implementation,
                technical enablement, client-facing automation, and cross-functional delivery.
                """,
                encoding="utf-8",
            )
            (input_dir / "pass.txt").write_text(
                """
                Principal ML Engineer

                Remote in the United States only. Must be based in the U.S. We need a machine learning
                engineer focused on research scientist work, computer vision, and pure research.
                """,
                encoding="utf-8",
            )

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("triage_dir: output/jobs/triage", f"triage_dir: {triage_dir}", 1)
            config_text = config_text.replace("daily_summary_dir: output/jobs/daily", f"daily_summary_dir: {summary_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-daily-summary.json",
                f"latest_status_file: {latest_status}",
                1,
            )
            config_text = config_text.replace(
                "latest_status_file: data/job-search-discovery-status.json",
                f"latest_status_file: {discovery_status}",
                1,
            )
            config_text = config_text.replace(
                "state_file: data/job-search-discovery-state.json",
                f"state_file: {discovery_state}",
                1,
            )
            config_path.write_text(config_text, encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "daily-summary",
                    "--config",
                    str(config_path),
                    "--input-dir",
                    str(input_dir),
                    "--day-label",
                    "2026-03-09",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            cli_payload = json.loads(proc.stdout)
            self.assertEqual(cli_payload["processed_count"], 3)

            summary_json = Path(cli_payload["summary_json"])
            self.assertTrue(summary_json.exists())
            self.assertTrue(Path(cli_payload["summary_markdown"]).exists())
            self.assertTrue(Path(cli_payload["latest_status"]).exists())

            payload = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["apply_count"], 1)
            self.assertEqual(payload["summary"]["manual_review_count"], 1)
            self.assertEqual(payload["summary"]["pass_count"], 1)
            self.assertEqual(payload["recommendations"][0]["title"], "AI Adoption Lead")
            self.assertEqual(payload["sections"]["apply"][0]["title"], "AI Adoption Lead")
            self.assertEqual(payload["sections"]["manual_review"][0]["title"], "Solutions Consultant")
            self.assertEqual(payload["sections"]["pass"][0]["title"], "Principal ML Engineer")

    def test_publish_report_preview_returns_telegram_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "postings"
            triage_dir = tmp_path / "triage"
            summary_dir = tmp_path / "daily"
            latest_status = tmp_path / "job-search-status.json"
            config_path = tmp_path / "job_search.yaml"

            input_dir.mkdir()
            (input_dir / "apply.txt").write_text(
                """
                AI Enablement Consultant

                Global remote across LATAM including Ecuador. Looking for AI adoption,
                workflow automation, stakeholder alignment, and Python.
                """,
                encoding="utf-8",
            )

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("saved_postings_dir: data/job-search/inbox", f"saved_postings_dir: {input_dir}", 1)
            config_text = config_text.replace("triage_dir: output/jobs/triage", f"triage_dir: {triage_dir}", 1)
            config_text = config_text.replace("daily_summary_dir: output/jobs/daily", f"daily_summary_dir: {summary_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-daily-summary.json",
                f"latest_status_file: {latest_status}",
                1,
            )
            config_path.write_text(config_text, encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "publish-report",
                    "--config",
                    str(config_path),
                    "--day-label",
                    "2026-03-09",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["delivery"]["sent"])
            self.assertEqual(payload["delivery"]["channel"], "telegram")
            self.assertIn("Apply Today", payload["delivery"]["preview"])
            self.assertIn("AI Enablement Consultant", payload["delivery"]["preview"])

    def test_publish_report_can_run_discovery_before_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "postings"
            triage_dir = tmp_path / "triage"
            summary_dir = tmp_path / "daily"
            latest_status = tmp_path / "job-search-status.json"
            discovery_status = tmp_path / "job-discovery-status.json"
            discovery_state = tmp_path / "job-discovery-state.json"
            config_path = tmp_path / "job_search.yaml"
            fixtures_path = tmp_path / "fixtures.json"

            input_dir.mkdir()
            fixtures_path.write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "query": 'site:linkedin.com/jobs/view ("ai adoption") remote',
                                "results": [
                                    {
                                        "url": "https://www.linkedin.com/jobs/view/555555/",
                                        "title": "AI Adoption Manager",
                                        "snippet": "Global remote across LATAM including Ecuador.",
                                        "content_text": "AI Adoption Manager Global remote across LATAM including Ecuador. AI adoption, workflow automation, stakeholder alignment, Python.",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("saved_postings_dir: data/job-search/inbox", f"saved_postings_dir: {input_dir}", 1)
            config_text = config_text.replace("triage_dir: output/jobs/triage", f"triage_dir: {triage_dir}", 1)
            config_text = config_text.replace("daily_summary_dir: output/jobs/daily", f"daily_summary_dir: {summary_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-daily-summary.json",
                f"latest_status_file: {latest_status}",
                1,
            )
            config_text = config_text.replace(
                "latest_status_file: data/job-search-discovery-status.json",
                f"latest_status_file: {discovery_status}",
                1,
            )
            config_text = config_text.replace(
                "state_file: data/job-search-discovery-state.json",
                f"state_file: {discovery_state}",
                1,
            )
            config_path.write_text(config_text, encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "publish-report",
                    "--config",
                    str(config_path),
                    "--discovery-fixtures-file",
                    str(fixtures_path),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["processed_count"], 1)
            self.assertEqual(payload["discovery"]["summary"]["saved_count"], 1)
            self.assertTrue(Path(payload["summary_json"]).exists())
            self.assertTrue(discovery_status.exists())
            self.assertIn("AI Adoption Manager", payload["delivery"]["preview"])

    def test_publish_report_allow_empty_creates_missing_inbox_and_writes_zero_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "postings-missing"
            triage_dir = tmp_path / "triage"
            summary_dir = tmp_path / "daily"
            latest_status = tmp_path / "job-search-status.json"
            discovery_status = tmp_path / "job-discovery-status.json"
            discovery_state = tmp_path / "job-discovery-state.json"
            config_path = tmp_path / "job_search.yaml"

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("saved_postings_dir: data/job-search/inbox", f"saved_postings_dir: {input_dir}", 1)
            config_text = config_text.replace("triage_dir: output/jobs/triage", f"triage_dir: {triage_dir}", 1)
            config_text = config_text.replace("daily_summary_dir: output/jobs/daily", f"daily_summary_dir: {summary_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-daily-summary.json",
                f"latest_status_file: {latest_status}",
                1,
            )
            config_text = config_text.replace(
                "latest_status_file: data/job-search-discovery-status.json",
                f"latest_status_file: {discovery_status}",
                1,
            )
            config_text = config_text.replace(
                "state_file: data/job-search-discovery-state.json",
                f"state_file: {discovery_state}",
                1,
            )
            config_path.write_text(config_text, encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "publish-report",
                    "--config",
                    str(config_path),
                    "--day-label",
                    "2026-03-10",
                    "--allow-empty",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(input_dir.exists())
            self.assertEqual(payload["processed_count"], 0)
            self.assertEqual(payload["input_dir"], str(input_dir))
            self.assertIn("No saved postings found", payload["delivery"]["preview"])
            self.assertTrue(Path(payload["summary_json"]).exists())
            self.assertTrue(Path(payload["summary_markdown"]).exists())

    def test_publish_report_apply_prefers_research_chat_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "postings"
            triage_dir = tmp_path / "triage"
            summary_dir = tmp_path / "daily"
            latest_status = tmp_path / "job-search-status.json"
            discovery_status = tmp_path / "job-discovery-status.json"
            discovery_state = tmp_path / "job-discovery-state.json"
            config_path = tmp_path / "job_search.yaml"
            env_path = tmp_path / "openclaw.env"

            input_dir.mkdir()
            (input_dir / "apply.txt").write_text(
                """
                AI Enablement Consultant

                Global remote across LATAM including Ecuador. Looking for AI adoption,
                workflow automation, stakeholder alignment, and Python.
                """,
                encoding="utf-8",
            )

            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("saved_postings_dir: data/job-search/inbox", f"saved_postings_dir: {input_dir}", 1)
            config_text = config_text.replace("triage_dir: output/jobs/triage", f"triage_dir: {triage_dir}", 1)
            config_text = config_text.replace("daily_summary_dir: output/jobs/daily", f"daily_summary_dir: {summary_dir}", 1)
            config_text = config_text.replace(
                "latest_status_file: data/job-search-daily-summary.json",
                f"latest_status_file: {latest_status}",
                1,
            )
            config_text = config_text.replace(
                "latest_status_file: data/job-search-discovery-status.json",
                f"latest_status_file: {discovery_status}",
                1,
            )
            config_text = config_text.replace(
                "state_file: data/job-search-discovery-state.json",
                f"state_file: {discovery_state}",
                1,
            )
            config_path.write_text(config_text, encoding="utf-8")
            env_path.write_text(
                "\n".join(
                    [
                        "TELEGRAM_BOT_TOKEN=test-token",
                        "TELEGRAM_ALLOWED_CHAT_ID=11111",
                        "TELEGRAM_RESEARCH_CHAT_ID=22222",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            sent_chat_ids: list[str] = []
            argv = [
                str(SCRIPT),
                "publish-report",
                "--config",
                str(config_path),
                "--env-file",
                str(env_path),
                "--day-label",
                "2026-03-09",
                "--apply",
            ]
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(jobs.TelegramReportClient, "send_long_message", autospec=True) as send_long:
                    send_long.side_effect = lambda self, *, chat_id, text: sent_chat_ids.append(chat_id) or [{"message_id": 1}]
                    exit_code = jobs.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(sent_chat_ids, ["22222"])


if __name__ == "__main__":
    unittest.main()
