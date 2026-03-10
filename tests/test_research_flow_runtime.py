import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research_flow_runtime.py"


class ResearchFlowRuntimeTests(unittest.TestCase):
    def run_script(self, args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_status_aggregates_workflow_status_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            job_status = tmp_path / "job-status.json"
            ai_status = tmp_path / "ai-status.json"
            aggregate_status = tmp_path / "research-flow-status.json"

            job_status.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-10T00:30:00+00:00",
                        "processed_count": 4,
                        "delivered": True,
                    }
                ),
                encoding="utf-8",
            )
            ai_status.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-10T02:00:00+00:00",
                        "item_count": 6,
                        "delivered": True,
                    }
                ),
                encoding="utf-8",
            )

            config_path = tmp_path / "research_flow.yaml"
            config_path.write_text(
                textwrap.dedent(
                    f"""\
                    research_flow:
                      enabled: true
                      owner_agent: researcher
                      default_space: research
                      delivery_chat_env: TELEGRAM_RESEARCH_CHAT_ID
                      shared_dropzones:
                        - data/researchflow/inbox
                      workflows:
                        job_search_digest:
                          enabled: true
                          kind: scheduled_digest
                          status_file: {job_status}
                          output_label: Job search digest
                          schedule:
                            enabled: true
                            timezone: America/Guayaquil
                            delivery_time_local: "18:30"
                          command:
                            script: {ROOT / "scripts" / "job_search_assistant.py"}
                            args:
                              - publish-report
                        ai_tools_watch:
                          enabled: true
                          kind: scheduled_digest
                          status_file: {ai_status}
                          output_label: AI tools digest
                          schedule:
                            enabled: true
                            timezone: America/Guayaquil
                            delivery_time_local: "20:00"
                          command:
                            script: {ROOT / "scripts" / "ai_tools_digest.py"}
                            args: []
                    """
                ),
                encoding="utf-8",
            )

            proc = self.run_script(
                [
                    "--config",
                    str(config_path),
                    "--status-file",
                    str(aggregate_status),
                    "--json",
                    "status",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["owner_agent"], "researcher")
            self.assertEqual(len(payload["workflows"]), 2)
            self.assertEqual(payload["workflows"][0]["name"], "ai_tools_watch")
            self.assertTrue(aggregate_status.exists())

    def test_run_all_executes_configured_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            aggregate_status = tmp_path / "research-flow-status.json"
            env_path = tmp_path / "openclaw.env"
            env_path.write_text("TELEGRAM_BOT_TOKEN=test\n", encoding="utf-8")

            fake_job = tmp_path / "fake_job.py"
            fake_job.write_text(
                textwrap.dedent(
                    """\
                    import argparse
                    import json
                    from pathlib import Path

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--env-file")
                    parser.add_argument("--apply", action="store_true")
                    parser.add_argument("--json", action="store_true")
                    parser.add_argument("args", nargs="*")
                    parsed = parser.parse_args()
                    root = Path(__file__).resolve().parent
                    summary_json = root / "job-report.json"
                    summary_markdown = root / "job-report.md"
                    summary_json.write_text("{}", encoding="utf-8")
                    summary_markdown.write_text("# Job report\\n", encoding="utf-8")
                    print(json.dumps({
                        "generated_at": "2026-03-10T03:00:00+00:00",
                        "processed_count": 3,
                        "delivered": parsed.apply,
                        "args": parsed.args,
                        "summary_json": str(summary_json),
                        "summary_markdown": str(summary_markdown),
                        "latest_status": str(root / "job-status.json"),
                    }))
                    """
                ),
                encoding="utf-8",
            )

            fake_ai = tmp_path / "fake_ai.py"
            fake_ai.write_text(
                textwrap.dedent(
                    """\
                    import argparse
                    import json
                    from pathlib import Path

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--env-file")
                    parser.add_argument("--apply", action="store_true")
                    parser.add_argument("--json", action="store_true")
                    parser.add_argument("args", nargs="*")
                    parsed = parser.parse_args()
                    root = Path(__file__).resolve().parent
                    digest_json = root / "ai-digest.json"
                    digest_markdown = root / "ai-digest.md"
                    digest_json.write_text("{}", encoding="utf-8")
                    digest_markdown.write_text("# AI digest\\n", encoding="utf-8")
                    print(json.dumps({
                        "generated_at": "2026-03-10T04:00:00+00:00",
                        "item_count": 5,
                        "delivered": parsed.apply,
                        "args": parsed.args,
                        "digest_json": str(digest_json),
                        "digest_markdown": str(digest_markdown),
                        "status_file": str(root / "ai-status.json"),
                    }))
                    """
                ),
                encoding="utf-8",
            )

            config_path = tmp_path / "research_flow.yaml"
            config_path.write_text(
                textwrap.dedent(
                    f"""\
                    research_flow:
                      enabled: true
                      owner_agent: researcher
                      default_space: research
                      delivery_chat_env: TELEGRAM_RESEARCH_CHAT_ID
                      shared_dropzones:
                        - data/researchflow/inbox
                        - data/researchflow/notes
                      workflows:
                        job_search_digest:
                          enabled: true
                          kind: scheduled_digest
                          status_file: {tmp_path / "job-status.json"}
                          output_label: Job search digest
                          schedule:
                            enabled: true
                            timezone: America/Guayaquil
                            delivery_time_local: "18:30"
                          command:
                            script: {fake_job}
                            args:
                              - publish-report
                        ai_tools_watch:
                          enabled: true
                          kind: scheduled_digest
                          status_file: {tmp_path / "ai-status.json"}
                          output_label: AI tools digest
                          schedule:
                            enabled: true
                            timezone: America/Guayaquil
                            delivery_time_local: "20:00"
                          command:
                            script: {fake_ai}
                            args: []
                    """
                ),
                encoding="utf-8",
            )

            proc = self.run_script(
                [
                    "--config",
                    str(config_path),
                    "--status-file",
                    str(aggregate_status),
                    "--env-file",
                    str(env_path),
                    "--json",
                    "run",
                    "--workflow",
                    "all",
                    "--apply",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)

            payload = json.loads(proc.stdout)
            results = payload["last_run"]["results"]
            self.assertEqual(len(results), 2)
            self.assertTrue(all(row["ok"] for row in results))
            self.assertEqual(results[0]["workflow"], "job_search_digest")
            self.assertTrue(results[0]["artifact_paths"])
            self.assertTrue(results[1]["artifact_paths"])
            self.assertTrue(all(Path(path).exists() for path in results[0]["dropzone_records"]))
            self.assertTrue(aggregate_status.exists())

    def test_run_workflow_skips_json_flag_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            aggregate_status = tmp_path / "research-flow-status.json"

            fake_job = tmp_path / "fake_job_no_json.py"
            fake_job.write_text(
                textwrap.dedent(
                    """\
                    import argparse
                    import json

                    parser = argparse.ArgumentParser()
                    parser.add_argument("--env-file")
                    parser.add_argument("--apply", action="store_true")
                    parser.add_argument("args", nargs="*")
                    parsed = parser.parse_args()
                    print(json.dumps({
                        "generated_at": "2026-03-10T05:00:00+00:00",
                        "processed_count": 2,
                        "delivered": parsed.apply,
                        "args": parsed.args,
                    }))
                    """
                ),
                encoding="utf-8",
            )

            config_path = tmp_path / "research_flow.yaml"
            config_path.write_text(
                textwrap.dedent(
                    f"""\
                    research_flow:
                      enabled: true
                      owner_agent: researcher
                      default_space: research
                      delivery_chat_env: TELEGRAM_RESEARCH_CHAT_ID
                      shared_dropzones: []
                      workflows:
                        job_search_digest:
                          enabled: true
                          kind: scheduled_digest
                          status_file: {tmp_path / "job-status.json"}
                          output_label: Job search digest
                          schedule:
                            enabled: true
                            timezone: America/Guayaquil
                            delivery_time_local: "18:30"
                          command:
                            script: {fake_job}
                            supports_json_flag: false
                            args:
                              - publish-report
                    """
                ),
                encoding="utf-8",
            )

            proc = self.run_script(
                [
                    "--config",
                    str(config_path),
                    "--status-file",
                    str(aggregate_status),
                    "--json",
                    "run",
                    "--workflow",
                    "job_search_digest",
                ]
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["last_run"]["results"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
