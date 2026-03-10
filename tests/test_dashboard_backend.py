import json
import os
import sqlite3
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
        (self.tmp_path / "contracts" / "braindump").mkdir(parents=True)
        (self.tmp_path / "contracts" / "fitness").mkdir(parents=True)
        (self.tmp_path / "fitness").mkdir(parents=True)
        (self.tmp_path / "fitness" / "logs").mkdir(parents=True)
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
            "fitness_agent.yaml",
        ):
            shutil.copy(ROOT / "config" / name, self.tmp_path / "config" / name)

        shutil.copy(
            ROOT / "contracts" / "braindump" / "sqlite_schema.sql",
            self.tmp_path / "contracts" / "braindump" / "sqlite_schema.sql",
        )
        shutil.copy(
            ROOT / "contracts" / "fitness" / "sqlite_schema.sql",
            self.tmp_path / "contracts" / "fitness" / "sqlite_schema.sql",
        )
        shutil.copy(ROOT / "scripts" / "set_active_profiles.py", self.tmp_path / "scripts" / "set_active_profiles.py")
        shutil.copy(ROOT / "telemetry" / "model-calls.example.ndjson", self.tmp_path / "telemetry" / "model-calls.example.ndjson")
        for name in ("ATHLETE_PROFILE.md", "PROGRAM.md", "EXERCISE_LIBRARY.md", "RULES.md", "SESSION_QUEUE.md"):
            shutil.copy(ROOT / "fitness" / name, self.tmp_path / "fitness" / name)

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
        self.assertIn("braindump", state)
        self.assertIn("calendar_runtime", state)
        self.assertIn("personal_tasks", state)
        self.assertIn("provider_health", state)
        self.assertIn("agent_runtime", state)
        self.assertIn("telegram_adapter", state)
        self.assertIn("agent_chats", state)
        self.assertIn("continuous_improvement_status", state)
        self.assertIn("memory_sync_status", state)

        self.assertEqual(state["profiles"]["integrations"]["active"], "bootstrap_command_center")
        self.assertEqual(state["profiles"]["memory"]["active"], "hybrid_124")
        self.assertEqual(state["routing"]["active_mode"], "balanced_default")
        self.assertEqual(state["agent_runtime"]["default_user_facing_agent"], "assistant")

    def test_build_state_exposes_telegram_focus(self):
        (self.tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (self.tmp_path / "data" / "telegram-adapter-state.json").write_text(
            json.dumps(
                {
                    "conversation_focus": {"agent_id": "researcher", "space_key": "research", "set_at": "2026-03-09T12:00:00+00:00"},
                    "last_update_id": 42,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        state = self.backend.build_state()
        telegram = state["telegram_adapter"]
        self.assertTrue(telegram["available"])
        self.assertEqual(telegram["focus"]["agent_id"], "researcher")
        self.assertEqual(telegram["focus"]["space_key"], "research")
        binding_ids = [row["binding_id"] for row in telegram["bindings"]]
        self.assertIn("assistant_main", binding_ids)
        self.assertIn("fitness_coach", binding_ids)

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

    def test_set_dashboard_flags_persists_generated_token_toggle(self):
        self.backend.set_dashboard_flags(auth_allow_generated_token=True)
        cfg = self.backend.read_dashboard_config()
        self.assertTrue(cfg["dashboard"]["auth"]["allow_generated_token"])

    def test_run_provider_smoke_check_writes_snapshot(self):
        result = self.backend.run_provider_smoke_check(live=False)
        self.assertIn("providers", result)
        self.assertTrue((self.tmp_path / "data" / "provider-smoke-status.json").exists())
        google = next(row for row in result["providers"] if row["provider"] == "google_ai_studio_free")
        self.assertEqual(google["local_status"], "missing_env")

    def test_apply_preset_updates_profiles_and_toggles(self):
        result = self.backend.apply_preset("manual_min_cost")
        self.assertTrue(result["ok"])

        state = self.backend.build_state()
        self.assertEqual(state["profiles"]["integrations"]["active"], "bootstrap_core")
        self.assertEqual(state["profiles"]["memory"]["active"], "md_only")

        integrations = {row["name"]: row for row in state["modules"]["integrations"]}
        memory = {row["name"]: row for row in state["modules"]["memory"]}
        self.assertFalse(integrations["n8n"]["enabled"])
        self.assertFalse(memory["semantic_embeddings"]["enabled"])
        self.assertFalse(memory["sqlite_state"]["enabled"])

    def test_create_and_update_project(self):
        created = self.backend.create_project(name="Agent KPI Board", owner="pavel")
        self.assertTrue(created["id"].startswith("proj-"))

        workspace = self.backend.load_workspace_data()
        spaces = workspace.get("spaces", [])
        project_space = next((row for row in spaces if row.get("project_id") == created["id"]), None)
        self.assertIsNotNone(project_space)
        self.assertEqual(project_space["session_strategy"], "separate_session")
        self.assertEqual(project_space["agent_strategy"], "spawn_on_demand")

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

    def test_promote_task_to_project_creates_project_space_and_reassigns_task(self):
        task = self.backend.create_task(
            title="Design calendar conflict review flow",
            assignees=["pavel"],
            priority="high",
            notes="Needs its own ongoing workstream",
        )

        result = self.backend.promote_task_to_project(task_id=task["id"], name="Calendar Conflict Review")
        project = result["project"]
        promoted_task = result["task"]
        space = result["space"]

        self.assertEqual(promoted_task["project_id"], project["id"])
        self.assertEqual(space["project_id"], project["id"])
        self.assertEqual(space["key"], "projects/calendar-conflict-review")
        self.assertEqual(space["source_task_id"], task["id"])

        state = self.backend.build_state()
        project_row = next(row for row in state["workspace"]["projects"] if row["id"] == project["id"])
        self.assertEqual(project_row["space_key"], "projects/calendar-conflict-review")
        self.assertEqual(project_row["space_session_strategy"], "separate_session")
        self.assertEqual(state["workspace"]["space_counts"]["project"], len(state["workspace"]["spaces"]))

    def test_route_text_to_space_resolves_project_hint(self):
        project = self.backend.create_project(name="Calendar Conflict Review", owner="pavel")

        route = self.backend.route_text_to_space(
            text="[project:calendar-conflict-review] remind me to review the calendar queue"
        )

        self.assertTrue(route["matched"])
        self.assertTrue(route["resolved"])
        self.assertEqual(route["kind"], "project")
        self.assertEqual(route["project_id"], project["id"])
        self.assertEqual(route["space_key"], "projects/calendar-conflict-review")
        self.assertEqual(route["stripped_text"], "remind me to review the calendar queue")
        self.assertEqual(route["space"]["entry_command_hint"], "[project:calendar-conflict-review]")

    def test_route_text_to_space_suggests_close_project_matches(self):
        route = self.backend.route_text_to_space(text="[project:clawdio] add a runtime status badge")

        self.assertTrue(route["matched"])
        self.assertFalse(route["resolved"])
        suggestions = route["suggested_projects"]
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0]["space_key"], "projects/openclaw-v2-rebuild")

    def test_route_text_to_space_resolves_specialist_core_space(self):
        route = self.backend.route_text_to_space(
            text="research: compare openrouter and gemini for fallback routing"
        )

        self.assertTrue(route["matched"])
        self.assertTrue(route["resolved"])
        self.assertEqual(route["agent_id"], "researcher")
        self.assertEqual(route["space_key"], "research")
        self.assertEqual(route["kind"], "core")
        self.assertEqual(route["space"]["entry_command_hint"], "research: <text>")

    def test_create_agent_routed_task_keeps_non_project_request_outside_default_project(self):
        result = self.backend.create_agent_routed_task(
            text="coding: tighten provider routing panel",
            source="telegram",
        )

        task = result["task"]
        self.assertEqual(task["assignees"], ["builder"])
        self.assertEqual(task["project_id"], None)
        self.assertEqual(result["route"]["space_key"], "coding")

        state = self.backend.build_state()
        last_route = state["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["agent_id"], "builder")
        self.assertEqual(last_route["space_key"], "coding")

    def test_assign_task_to_project_space_moves_existing_task(self):
        source = self.backend.create_project(name="Inbox Ops", owner="pavel")
        target = self.backend.create_project(name="Calendar Conflict Review", owner="pavel")
        task = self.backend.create_task(
            title="Review candidate",
            assignees=["pavel"],
            project_id=source["id"],
            priority="medium",
        )

        moved = self.backend.assign_task_to_project_space(task_id=task["id"], project_id=target["id"])

        self.assertEqual(moved["task"]["project_id"], target["id"])
        self.assertEqual(moved["project"]["name"], "Calendar Conflict Review")
        self.assertEqual(moved["space"]["key"], "projects/calendar-conflict-review")

    def test_assign_calendar_candidate_to_project_space_updates_candidate(self):
        project = self.backend.create_project(name="Calendar Conflict Review", owner="pavel")
        data_dir = self.tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "calendar-candidates.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "cal-1",
                            "title": "Review conflict",
                            "from_email": "alex@example.com",
                            "status": "proposed",
                            "updated_at": "2026-03-07T12:00:00+00:00",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        assigned = self.backend.assign_calendar_candidate_to_project(candidate_id="cal-1", project_id=project["id"])

        self.assertEqual(assigned["item"]["project_id"], project["id"])
        self.assertEqual(assigned["item"]["space_key"], "projects/calendar-conflict-review")
        state = self.backend.build_state()
        item = state["calendar_candidates"]["items"][0]
        self.assertEqual(item["project_name"], "Calendar Conflict Review")
        self.assertEqual(item["space_key"], "projects/calendar-conflict-review")

    def test_update_calendar_candidate_schedule_marks_ready(self):
        data_dir = self.tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "calendar-candidates.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "cal-2",
                            "title": "Parent teacher meeting",
                            "status": "proposed",
                            "updated_at": "2026-03-07T12:00:00+00:00",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        updated = self.backend.update_calendar_candidate(
            candidate_id="cal-2",
            status="ready",
            timezone_name="America/Guayaquil",
            start_at="2026-03-10T18:00:00-05:00",
            end_at="2026-03-10T18:30:00-05:00",
            location="School",
            attendees=["parent@example.com"],
        )

        self.assertEqual(updated["item"]["status"], "ready")
        self.assertEqual(updated["item"]["location"], "School")
        self.assertEqual(updated["item"]["attendees"], ["parent@example.com"])

        state = self.backend.build_state()
        item = next(row for row in state["calendar_candidates"]["items"] if row["id"] == "cal-2")
        self.assertEqual(item["status"], "ready")
        self.assertEqual(item["start_at"], "2026-03-10T18:00:00-05:00")

    def test_update_calendar_candidate_ready_requires_valid_schedule(self):
        data_dir = self.tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "calendar-candidates.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "cal-3",
                            "title": "Incomplete event",
                            "status": "proposed",
                            "updated_at": "2026-03-07T12:00:00+00:00",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError):
            self.backend.update_calendar_candidate(
                candidate_id="cal-3",
                status="approved",
                start_at="2026-03-10T18:00:00-05:00",
            )

    def test_apply_calendar_candidates_runtime_updates_status_and_candidate(self):
        data_dir = self.tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = self.tmp_path / "calendar-fixture.json"
        fixture_path.write_text(json.dumps({"events": []}), encoding="utf-8")
        (data_dir / "calendar-candidates.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "cal-apply-1",
                            "title": "Review syllabus",
                            "status": "approved",
                            "start_at": "2026-03-10T09:00:00-05:00",
                            "end_at": "2026-03-10T09:30:00-05:00",
                            "timezone": "America/Guayaquil",
                            "updated_at": "2026-03-07T12:00:00+00:00",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        previous_calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
        os.environ["GOOGLE_CALENDAR_ID"] = "primary"
        try:
            result = self.backend.apply_calendar_candidates_runtime(
                apply=True,
                fixtures_file=fixture_path,
            )
        finally:
            if previous_calendar_id is None:
                os.environ.pop("GOOGLE_CALENDAR_ID", None)
            else:
                os.environ["GOOGLE_CALENDAR_ID"] = previous_calendar_id

        self.assertEqual(result["status"]["summary"]["created_count"], 1)
        self.assertTrue((data_dir / "calendar-runtime-status.json").exists())

        updated = json.loads((data_dir / "calendar-candidates.json").read_text(encoding="utf-8"))
        self.assertEqual(updated["items"][0]["status"], "scheduled")
        self.assertTrue(updated["items"][0]["event_id"])

    def test_personal_task_runtime_methods_and_status(self):
        data_dir = self.tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = self.tmp_path / "todoist-fixture.json"
        fixture_path.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "1",
                            "content": "Pay insurance",
                            "priority": 3,
                            "due": {"date": "2026-03-10"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        sync_result = self.backend.sync_personal_tasks_runtime(fixtures_file=fixture_path)
        self.assertEqual(sync_result["status"]["summary"]["open_count"], 1)

        create_result = self.backend.create_personal_task_runtime(
            title="Buy gift",
            due_string="tomorrow 6pm",
            priority=2,
            apply=True,
            fixtures_file=fixture_path,
        )
        self.assertEqual(create_result["status"]["summary"]["action"], "create_task")

        defer_result = self.backend.defer_personal_task_runtime(
            task_id="1",
            due_date="2026-03-15",
            apply=True,
            fixtures_file=fixture_path,
        )
        self.assertEqual(defer_result["status"]["summary"]["action"], "defer_task")

        complete_result = self.backend.complete_personal_task_runtime(
            task_id="1",
            apply=True,
            fixtures_file=fixture_path,
        )
        self.assertEqual(complete_result["status"]["summary"]["action"], "complete_task")

        state = self.backend.build_state()
        self.assertTrue(state["personal_tasks"]["available"])
        self.assertEqual(state["personal_tasks"]["provider"], "todoist")

    def test_run_fitness_command_updates_status_and_summary(self):
        start_result = self.backend.run_fitness_command(command_text="start workout")
        self.assertIn("Workout started", start_result["reply_text"])

        log_result = self.backend.run_fitness_command(command_text="log bb curl 8 reps 20kg bb total")
        self.assertEqual(len(log_result["created_sets"]), 1)

        finish_result = self.backend.run_fitness_command(command_text="finish workout")
        self.assertIn("Finished workout", finish_result["reply_text"])

        state = self.backend.build_state()
        self.assertTrue(state["fitness_runtime"]["available"])
        self.assertEqual(state["fitness_runtime"]["last_session"]["training_day_code"], "M1")
        self.assertTrue(state["fitness_runtime"]["last_session_summary"])
        self.assertTrue((self.tmp_path / "fitness" / "logs").exists())

    def test_build_state_exposes_fitness_runtime(self):
        state = self.backend.build_state()
        self.assertIn("fitness_runtime", state)
        self.assertTrue(state["fitness_runtime"]["available"])
        self.assertEqual(state["fitness_runtime"]["today_plan"]["plan"]["code"], "M1")

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

    def test_structured_side_effects_require_approval(self):
        project = self.backend.create_project(name="Structured Approval")
        task = self.backend.create_task(
            title="Handle outreach queue",
            assignees=["builder"],
            project_id=project["id"],
            priority="medium",
            side_effects=["github:create_issue"],
        )

        dispatch = self.backend.dispatch_task(task_id=task["id"])
        self.assertFalse(dispatch["queued"])
        self.assertTrue(dispatch["requires_approval"])
        self.assertEqual(dispatch["approval"]["status"], "pending")

    def test_unknown_side_effects_are_rejected(self):
        project = self.backend.create_project(name="Bad Effects")
        with self.assertRaises(ValueError):
            self.backend.create_task(
                title="Unsafe task",
                assignees=["builder"],
                project_id=project["id"],
                priority="medium",
                side_effects=["bad:thing"],
            )

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

    def test_capture_braindump_text_supports_aliases(self):
        result = self.backend.capture_braindump_text(
            text="bd gift perfume sampler #birthday @monthly",
            source="telegram",
        )

        item = result["item"]
        self.assertEqual(item["category"], "gift_idea_wife")
        self.assertEqual(item["review_bucket"], "monthly")
        self.assertEqual(item["tags"], ["birthday"])
        self.assertEqual(item["source"], "telegram")

        state = self.backend.build_state()
        self.assertTrue(state["braindump"]["available"])
        self.assertEqual(state["braindump"]["counts_by_category"]["gift_idea_wife"], 1)
        self.assertIn("gift", state["braindump"]["category_catalog"]["aliases"])

    def test_capture_braindump_text_routes_project_hint(self):
        self.backend.create_project(name="Calendar Conflict Review", owner="pavel")

        result = self.backend.capture_braindump_text(
            text="[project:calendar-conflict-review] bd tool test agentmail #email",
            source="telegram",
        )

        self.assertTrue(result["route"]["resolved"])
        self.assertEqual(result["parsed"]["category"], "tool_to_test")
        self.assertEqual(result["item"]["short_text"], "test agentmail")
        self.assertIn("space=projects/calendar-conflict-review", result["item"]["notes"])

    def test_capture_braindump_text_rejects_unknown_project_hint(self):
        with self.assertRaises(ValueError):
            self.backend.capture_braindump_text(
                text="[project:missing-space] bd tool test agentmail",
                source="telegram",
            )

    def test_braindump_create_promote_archive_and_custom_category(self):
        created = self.backend.create_braindump_item(
            category="book_series",
            text="track stormlight reread",
            review_bucket="seasonal",
            source="dashboard",
        )
        item = created["item"]
        self.assertEqual(item["category"], "book_series")
        self.assertEqual(item["review_bucket"], "seasonal")

        conn = sqlite3.connect(self.tmp_path / ".memory" / "braindump.db")
        default_row = conn.execute(
            "SELECT review_bucket FROM braindump_category_defaults WHERE category = ?",
            ("book_series",),
        ).fetchone()
        conn.close()
        self.assertEqual(default_row[0], "seasonal")

        promoted = self.backend.promote_braindump_item(item_id=item["id"], target="task")
        self.assertEqual(promoted["item"]["status"], "promoted")
        workspace = self.backend.load_workspace_data()
        self.assertEqual(len([row for row in workspace["tasks"] if row.get("source") == "braindump"]), 1)

        second = self.backend.create_braindump_item(
            category="personal_note",
            text="remember camping stove dimensions",
            source="dashboard",
        )["item"]
        parked = self.backend.park_braindump_item(item_id=second["id"], review_bucket="monthly")
        self.assertEqual(parked["item"]["status"], "parked")
        with self.assertRaises(ValueError):
            self.backend.park_braindump_item(item_id=second["id"], review_bucket="nonsense")
        archived = self.backend.archive_braindump_item(item_id=second["id"])
        self.assertEqual(archived["item"]["status"], "archived")

    def test_gmail_drive_calendar_and_braindump_runtime_status_are_exposed(self):
        data_dir = self.tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (self.tmp_path / ".memory").mkdir(parents=True, exist_ok=True)

        (data_dir / "gmail-inbox-last-run.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-07T12:00:00+00:00",
                    "run_id": 7,
                    "dry_run": False,
                    "state_db": str(self.tmp_path / ".memory" / "inbox_processing.db"),
                    "summary": {"processed_count": 3, "candidate_counts": {"task": 1, "calendar": 1}},
                    "promotions": {"tasks": {"created": 1, "updated": 0}, "calendar": {"created": 1, "updated": 0}},
                    "recent_results": [
                        {
                            "from_email": "alex@example.com",
                            "subject": "Meeting change",
                            "primary_action": "keep_in_inbox",
                            "reason": "calendar or deadline candidate",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (data_dir / "calendar-candidates.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "cal-gmail-m1",
                            "title": "Meeting change",
                            "from_email": "alex@example.com",
                            "status": "proposed",
                            "updated_at": "2026-03-07T12:00:00+00:00",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (data_dir / "calendar-runtime-status.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-07T12:10:00+00:00",
                    "calendar_id": "primary",
                    "summary": {
                        "action": "apply_candidates",
                        "dry_run": False,
                        "upcoming_count": 2,
                        "created_count": 1,
                        "updated_count": 0,
                        "skipped_count": 1,
                        "pending_candidate_count": 1,
                    },
                    "recent_results": [
                        {
                            "candidate_id": "cal-gmail-m1",
                            "title": "Meeting change",
                            "action": "create_event",
                            "status": "scheduled",
                        }
                    ],
                    "upcoming_events": [
                        {
                            "id": "evt-1",
                            "summary": "Meeting change",
                            "start_value": "2026-03-08T16:00:00+00:00",
                            "end_value": "2026-03-08T16:30:00+00:00",
                            "all_day": False,
                        },
                        {
                            "id": "evt-2",
                            "summary": "Holiday",
                            "start_value": "2026-03-09",
                            "end_value": "2026-03-10",
                            "all_day": True,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (data_dir / "personal-task-runtime-status.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-07T12:15:00+00:00",
                    "provider": "todoist",
                    "summary": {
                        "action": "snapshot",
                        "dry_run": False,
                        "open_count": 2,
                        "overdue_count": 1,
                    },
                    "recent_results": [],
                    "tasks": [
                        {
                            "id": "pt-1",
                            "title": "Pay insurance",
                            "priority": 3,
                            "due_value": "2026-03-07",
                            "due_mode": "date",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (data_dir / "drive-workspace-status.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-07T12:00:00+00:00",
                    "summary": {
                        "ok": False,
                        "root": {"id": "root1", "name": "OpenClaw Shared"},
                        "missing": ["02_outputs"],
                        "extra": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        (data_dir / "braindump-snapshot.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-07T12:30:00+00:00",
                    "db_path": str(self.tmp_path / ".memory" / "braindump.db"),
                    "counts_by_status": {"inbox": 2, "parked": 1},
                    "counts_by_bucket": {"weekly": 2, "monthly": 1},
                    "counts_by_category": {"gift_idea_wife": 2, "tool_to_test": 1},
                    "due_count": 1,
                    "due_items": [
                        {
                            "id": "bd-gift-1",
                            "short_text": "Check perfume sampler",
                            "category": "gift_idea_wife",
                            "status": "inbox",
                            "review_bucket": "weekly",
                            "next_review_at": "2026-03-07T11:30:00+00:00",
                        }
                    ],
                    "recent_items": [
                        {
                            "id": "bd-tool-1",
                            "short_text": "Test AgentMail",
                            "category": "tool_to_test",
                            "status": "parked",
                            "review_bucket": "monthly",
                            "updated_at": "2026-03-07T12:20:00+00:00",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        state = self.backend.build_state()
        self.assertTrue(state["gmail_inbox"]["available"])
        self.assertEqual(state["gmail_inbox"]["summary"]["processed_count"], 3)
        self.assertTrue(state["calendar_runtime"]["available"])
        self.assertEqual(state["calendar_runtime"]["summary"]["created_count"], 1)
        self.assertEqual(len(state["calendar_runtime"]["upcoming_events"]), 2)
        self.assertTrue(state["calendar_candidates"]["available"])
        self.assertEqual(state["calendar_candidates"]["count"], 1)
        self.assertTrue(state["personal_tasks"]["available"])
        self.assertEqual(state["personal_tasks"]["summary"]["open_count"], 2)
        self.assertTrue(state["drive_workspace"]["available"])
        self.assertEqual(state["drive_workspace"]["summary"]["missing"], ["02_outputs"])
        self.assertTrue(state["braindump"]["available"])
        self.assertEqual(state["braindump"]["due_count"], 1)
        self.assertEqual(state["braindump"]["counts_by_status"]["inbox"], 2)


if __name__ == "__main__":
    unittest.main()
