import shutil
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "dashboard"))

from backend import DashboardBackend  # noqa: E402


class DashboardBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

        (self.tmp_path / "config").mkdir(parents=True)
        (self.tmp_path / "telemetry").mkdir(parents=True)
        (self.tmp_path / "scripts").mkdir(parents=True)

        for name in (
            "integrations.yaml",
            "memory.yaml",
            "models.yaml",
            "core.yaml",
            "channels.yaml",
            "reminders.yaml",
            "dashboard.yaml",
            "agents.yaml",
        ):
            shutil.copy(ROOT / "config" / name, self.tmp_path / "config" / name)

        shutil.copy(ROOT / "scripts" / "set_active_profiles.py", self.tmp_path / "scripts" / "set_active_profiles.py")
        shutil.copy(ROOT / "telemetry" / "model-calls.example.ndjson", self.tmp_path / "telemetry" / "model-calls.example.ndjson")

        self.backend = DashboardBackend(root=self.tmp_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_state_contains_expected_sections(self):
        state = self.backend.build_state()

        self.assertIn("profiles", state)
        self.assertIn("modules", state)
        self.assertIn("telemetry", state)
        self.assertIn("env", state)
        self.assertIn("routing", state)

        self.assertEqual(state["profiles"]["integrations"]["active"], "lean_manual")
        self.assertEqual(state["profiles"]["memory"]["active"], "hybrid_124")
        self.assertEqual(state["routing"]["active_mode"], "balanced_default")

    def test_set_integration_enabled_updates_yaml(self):
        path = self.tmp_path / "config" / "integrations.yaml"
        before = path.read_text(encoding="utf-8")
        self.assertIn("\n  gmail:\n    enabled: true\n", before)

        self.backend.set_integration_enabled("gmail", False)

        after = path.read_text(encoding="utf-8")
        self.assertIn("\n  gmail:\n    enabled: false\n", after)

    def test_set_memory_module_enabled_updates_yaml(self):
        path = self.tmp_path / "config" / "memory.yaml"
        before = path.read_text(encoding="utf-8")
        self.assertIn("\n  semantic_embeddings:\n    enabled: true\n", before)

        self.backend.set_memory_module_enabled("semantic_embeddings", False)

        after = path.read_text(encoding="utf-8")
        self.assertIn("\n  semantic_embeddings:\n    enabled: false\n", after)

    def test_set_n8n_module_enabled_updates_yaml(self):
        path = self.tmp_path / "config" / "integrations.yaml"
        before = path.read_text(encoding="utf-8")
        self.assertIn("      news_digest: false", before)

        self.backend.set_n8n_module_enabled("news_digest", True)

        after = path.read_text(encoding="utf-8")
        self.assertIn("      news_digest: true", after)

    def test_set_dashboard_flags_persists(self):
        self.backend.set_dashboard_flags(
            codexbar_cost_enabled=True,
            codexbar_provider="openai",
            auto_refresh_seconds=45,
            routing_mode="strict_cost",
        )

        cfg = self.backend.read_dashboard_config()
        adapters = cfg["dashboard"]["adapters"]
        codexbar = cfg["dashboard"]["codexbar"]
        ui = cfg["dashboard"]["ui"]

        self.assertTrue(adapters["codexbar_cost_enabled"])
        self.assertEqual(codexbar["provider"], "openai")
        self.assertEqual(ui["auto_refresh_seconds"], 45)

        agents_text = (self.tmp_path / "config" / "agents.yaml").read_text(encoding="utf-8")
        self.assertIn("routing_overrides:\n  active_mode: strict_cost\n", agents_text)

        state = self.backend.build_state()
        self.assertEqual(state["routing"]["active_mode"], "strict_cost")

    def test_invalid_codexbar_provider_raises(self):
        with self.assertRaises(ValueError):
            self.backend.set_dashboard_flags(codexbar_provider="invalid")

    def test_apply_preset_updates_profiles_and_toggles(self):
        result = self.backend.apply_preset("manual_min_cost")
        self.assertTrue(result["ok"])

        state = self.backend.build_state()
        self.assertEqual(state["profiles"]["integrations"]["active"], "lean_manual")
        self.assertEqual(state["profiles"]["memory"]["active"], "md_only")

        integrations = {row["name"]: row for row in state["modules"]["integrations"]}
        memory = {row["name"]: row for row in state["modules"]["memory"]}
        self.assertFalse(integrations["n8n"]["enabled"])
        self.assertFalse(memory["semantic_embeddings"]["enabled"])
        self.assertFalse(memory["sqlite_state"]["enabled"])

    def test_create_and_update_project(self):
        created = self.backend.create_project(name="Agent KPI Board", owner="pavel")
        self.assertTrue(created["id"].startswith("proj-"))

        updated = self.backend.update_project(project_id=created["id"], status="paused", progress_pct=35)
        self.assertEqual(updated["status"], "paused")
        self.assertEqual(updated["progress_pct"], 35)

    def test_create_task_with_multiple_assignees(self):
        project = self.backend.create_project(name="Execution Test")
        task = self.backend.create_task(
            title="Draft weekly digest",
            assignees=["pavel", "builder"],
            project_id=project["id"],
            priority="high",
        )
        self.assertEqual(task["status"], "todo")
        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["assignees"], ["pavel", "builder"])

        updated = self.backend.update_task(
            task_id=task["id"],
            status="in_progress",
            progress_pct=40,
            assignees=["builder"],
        )
        self.assertEqual(updated["status"], "in_progress")
        self.assertEqual(updated["progress_pct"], 40)
        self.assertEqual(updated["assignees"], ["builder"])

    def test_create_task_from_template(self):
        project = self.backend.create_project(name="Template Project")
        result = self.backend.create_task_from_template(
            template_name="build_feature",
            title="Build: dashboard export panel",
            project_id=project["id"],
        )
        task = result["task"]
        self.assertEqual(result["template"], "build_feature")
        self.assertEqual(task["title"], "Build: dashboard export panel")
        self.assertEqual(task["priority"], "high")
        self.assertIn("builder", task["assignees"])
        self.assertEqual(task["project_id"], project["id"])

    def test_export_reports(self):
        project = self.backend.create_project(name="Reporting")
        self.backend.create_task(
            title="Draft report",
            assignees=["pavel"],
            project_id=project["id"],
            priority="medium",
        )

        md = self.backend.build_weekly_markdown_report(days=7)
        self.assertIn("# Weekly Progress Report", md)
        self.assertIn("## Open Tasks", md)
        self.assertIn("Draft report", md)

        csv_text = self.backend.build_tasks_csv_report()
        self.assertIn("task_id,title,project_id,project_name,status", csv_text)
        self.assertIn("Draft report", csv_text)

    def test_dispatch_requires_approval_then_runs(self):
        project = self.backend.create_project(name="Approval Gate")
        task = self.backend.create_task(
            title="Send weekly digest email",
            assignees=["builder"],
            project_id=project["id"],
            priority="high",
            notes="Send digest to Gmail account",
        )

        first_dispatch = self.backend.dispatch_task(task_id=task["id"], assignee="builder")
        self.assertFalse(first_dispatch["queued"])
        self.assertTrue(first_dispatch["requires_approval"])
        approval_id = first_dispatch["approval"]["id"]

        state = self.backend.build_state()
        self.assertEqual(state["workspace"]["approval_counts"]["pending"], 1)
        self.assertEqual(state["workspace"]["run_counts"]["queued"], 0)

        approved = self.backend.decide_approval(
            approval_id=approval_id,
            decision="approved",
            decided_by="pavel",
        )
        self.assertEqual(approved["status"], "approved")

        second_dispatch = self.backend.dispatch_task(task_id=task["id"], assignee="builder")
        self.assertTrue(second_dispatch["queued"])
        run = second_dispatch["run"]
        self.assertEqual(run["status"], "queued")

        started = self.backend.update_run(run_id=run["id"], status="running", actor="builder")
        self.assertEqual(started["status"], "running")
        finished = self.backend.update_run(
            run_id=run["id"],
            status="succeeded",
            output_summary="Digest sent",
            actor="builder",
        )
        self.assertEqual(finished["status"], "succeeded")

        state_after = self.backend.build_state()
        tasks = {row["id"]: row for row in state_after["workspace"]["tasks"]}
        self.assertEqual(tasks[task["id"]]["status"], "done")
        self.assertEqual(state_after["workspace"]["run_counts"]["succeeded"], 1)

    def test_dispatch_without_external_write_queues_immediately(self):
        project = self.backend.create_project(name="Internal Work")
        task = self.backend.create_task(
            title="Refactor parser module",
            assignees=["builder"],
            project_id=project["id"],
            priority="medium",
            notes="No external write operation",
        )

        dispatch = self.backend.dispatch_task(task_id=task["id"])
        self.assertTrue(dispatch["queued"])
        self.assertFalse(dispatch["requires_approval"])

        state = self.backend.build_state()
        self.assertEqual(state["workspace"]["approval_counts"]["pending"], 0)
        self.assertEqual(state["workspace"]["run_counts"]["queued"], 1)

    def test_pending_reminders_are_exposed(self):
        reminder_path = self.tmp_path / "data" / "reminders-state.json"
        reminder_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        reminder_path.write_text(
            (
                '{\n'
                '  "reminders": {\n'
                '    "r-1": {\n'
                '      "id": "r-1",\n'
                '      "message": "Submit report",\n'
                '      "status": "pending",\n'
                '      "timezone": "America/Guayaquil",\n'
                f'      "remind_at": "{now}",\n'
                '      "next_followup_at": null,\n'
                '      "last_reminded_at": null,\n'
                '      "followup_count": 0\n'
                '    },\n'
                '    "r-2": {\n'
                '      "id": "r-2",\n'
                '      "message": "Done item",\n'
                '      "status": "done",\n'
                '      "timezone": "America/Guayaquil"\n'
                '    }\n'
                '  }\n'
                '}\n'
            ),
            encoding="utf-8",
        )

        state = self.backend.build_state()
        pending = state["reminders"]["pending_items"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], "r-1")
        self.assertEqual(state["reminders"]["counts"]["pending"], 1)


if __name__ == "__main__":
    unittest.main()
