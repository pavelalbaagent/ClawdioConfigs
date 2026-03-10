import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import DashboardBackend  # noqa: E402
import telegram_adapter  # noqa: E402


class FakeTelegramClient:
    def __init__(self):
        self.sent_messages: list[dict[str, object]] = []
        self.next_message_id = 900

    def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, object]]:
        return []

    def send_message(self, *, chat_id: str, text: str, reply_to_message_id: int | None = None) -> dict[str, object]:
        self.next_message_id += 1
        row = {
            "message_id": self.next_message_id,
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
        }
        self.sent_messages.append(row)
        return {"message_id": self.next_message_id}


class TelegramAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "contracts" / "braindump").mkdir(parents=True)
        (self.root / "contracts" / "fitness").mkdir(parents=True)
        (self.root / "fitness").mkdir(parents=True)
        (self.root / "fitness" / "logs").mkdir(parents=True)
        (self.root / "telemetry").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)

        for name in (
            "integrations.yaml",
            "memory.yaml",
            "models.yaml",
            "core.yaml",
            "channels.yaml",
            "reminders.yaml",
            "dashboard.yaml",
            "agents.yaml",
            "session_policy.yaml",
            "fitness_agent.yaml",
        ):
            shutil.copy(ROOT / "config" / name, self.root / "config" / name)

        shutil.copy(
            ROOT / "contracts" / "braindump" / "sqlite_schema.sql",
            self.root / "contracts" / "braindump" / "sqlite_schema.sql",
        )
        shutil.copy(
            ROOT / "contracts" / "fitness" / "sqlite_schema.sql",
            self.root / "contracts" / "fitness" / "sqlite_schema.sql",
        )
        shutil.copy(ROOT / "scripts" / "set_active_profiles.py", self.root / "scripts" / "set_active_profiles.py")
        for name in ("ATHLETE_PROFILE.md", "PROGRAM.md", "EXERCISE_LIBRARY.md", "RULES.md", "SESSION_QUEUE.md"):
            shutil.copy(ROOT / "fitness" / name, self.root / "fitness" / name)

        self.backend = DashboardBackend(root=self.root)
        self.client = FakeTelegramClient()
        self.adapter = telegram_adapter.TelegramAdapter(
            root=self.root,
            backend=self.backend,
            client=self.client,
            allowed_chat_id="12345",
            env_values={},
            state_path=self.root / "data" / "telegram-adapter-state.json",
            reminder_state_path=self.root / "data" / "reminders-state.json",
            default_timezone="America/Guayaquil",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _update(self, update_id: int, text: str, *, reply_to_message_id: int | None = None) -> dict[str, object]:
        message: dict[str, object] = {
            "message_id": update_id * 10,
            "date": int(datetime.now(timezone.utc).timestamp()),
            "chat": {"id": 12345, "type": "private"},
            "from": {"id": 12345, "is_bot": False, "first_name": "Pavel"},
            "text": text,
        }
        if reply_to_message_id is not None:
            message["reply_to_message"] = {"message_id": reply_to_message_id}
        return {"update_id": update_id, "message": message}

    def _update_for_chat(self, update_id: int, text: str, *, chat_id: int) -> dict[str, object]:
        message: dict[str, object] = {
            "message_id": update_id * 10,
            "date": int(datetime.now(timezone.utc).timestamp()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "Pavel"},
            "text": text,
        }
        return {"update_id": update_id, "message": message}

    def test_braindump_capture_from_telegram_creates_item(self):
        state = self.adapter.load_adapter_state()
        handled = self.adapter.process_updates([self._update(1, "bd gift perfume sampler")], state=state)

        self.assertEqual(handled, 1)
        self.assertEqual(len(self.client.sent_messages), 1)
        self.assertIn("Braindump captured", str(self.client.sent_messages[0]["text"]))

        snapshot = self.backend._braindump_status()
        self.assertEqual(snapshot["counts_by_status"]["inbox"], 1)
        self.assertEqual(snapshot["recent_items"][0]["category"], "gift_idea_wife")

    def test_project_space_text_becomes_project_task(self):
        project = self.backend.create_project(name="Calendar Cleanup", owner="pavel")
        state = self.adapter.load_adapter_state()
        self.adapter.process_updates([self._update(2, "[project:calendar-cleanup] review recurring conflicts")], state=state)

        workspace = self.backend.load_workspace_data()
        created = [row for row in workspace["tasks"] if row["project_id"] == project["id"] and row["source"] == "telegram"]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"], "review recurring conflicts")
        self.assertIn("Project task captured", str(self.client.sent_messages[-1]["text"]))

    def test_specialist_prefix_uses_researcher_chat(self):
        with mock.patch.object(
            self.adapter.agent_chats["researcher"],
            "reply",
            return_value={
                "reply_text": "Use Gemini as primary and OpenRouter as overflow.",
                "space_key": "research",
                "lane": "L2_balanced",
                "provider": "google_ai_studio_free",
                "model": "gemini-2.5-flash",
            },
        ) as reply:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates(
                [self._update(21, "research: compare gemini and openrouter for low-cost fallback")],
                state=state,
            )

        reply.assert_called_once()
        response = str(self.client.sent_messages[-1]["text"])
        self.assertIn("Gemini as primary", response)
        workspace = self.backend.load_workspace_data()
        created = [row for row in workspace["tasks"] if row["source"] == "telegram" and row["assignees"] == ["researcher"]]
        self.assertEqual(created, [])

        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["agent_id"], "researcher")
        self.assertEqual(last_route["space_key"], "research")
        self.assertEqual(last_route["action"], "agent_chat")

    def test_unknown_project_hint_returns_suggestions(self):
        state = self.adapter.load_adapter_state()
        self.adapter.process_updates(
            [self._update(22, "coding: [project:clawdio] add a runtime status badge")],
            state=state,
        )

        response = str(self.client.sent_messages[-1]["text"])
        self.assertIn("Project space not found", response)
        self.assertIn("OpenClaw V2 Rebuild", response)

    def test_unmatched_text_uses_assistant_general_chat(self):
        with mock.patch.object(
            self.adapter.assistant_chat,
            "reply",
            return_value={
                "reply_text": "Use Gemini free for lightweight work and OpenRouter as overflow.",
                "space_key": "general",
                "lane": "L2_balanced",
                "provider": "google_ai_studio_free",
                "model": "gemini-2.5-flash",
            },
        ) as reply:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates(
                [self._update(23, "what model setup should I prefer for light daily usage?")],
                state=state,
            )

        reply.assert_called_once()
        response = str(self.client.sent_messages[-1]["text"])
        self.assertIn("Gemini free", response)
        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["action"], "agent_chat")
        self.assertEqual(last_route["lane"], "L2_balanced")
        self.assertEqual(last_route["provider"], "google_ai_studio_free")

    def test_long_agent_reply_is_split_into_multiple_telegram_messages(self):
        long_text = ("Section line\n" * 700).strip()
        with mock.patch.object(
            self.adapter.assistant_chat,
            "reply",
            return_value={
                "reply_text": long_text,
                "space_key": "general",
                "lane": "L2_balanced",
                "provider": "google_ai_studio_free",
                "model": "gemini-2.5-flash",
            },
        ):
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates(
                [self._update(29, "give me a detailed breakdown of the whole system")],
                state=state,
            )

        self.assertGreater(len(self.client.sent_messages), 1)
        for row in self.client.sent_messages:
            self.assertLessEqual(len(str(row["text"])), telegram_adapter.TELEGRAM_MESSAGE_CHUNK_LIMIT)

    def test_bound_research_chat_routes_without_prefix(self):
        bound_adapter = telegram_adapter.TelegramAdapter(
            root=self.root,
            backend=self.backend,
            client=self.client,
            chat_bindings={
                "12345": telegram_adapter.TelegramChatBinding(
                    binding_id="assistant_main",
                    label="Assistant Main",
                    chat_id="12345",
                    default_agent="assistant",
                    default_space="general",
                    natural_language_services={
                        "reminders": True,
                        "tasks": True,
                        "calendar": True,
                        "braindump": True,
                        "fitness": True,
                        "cross_agent_routing": True,
                    },
                ),
                "22222": telegram_adapter.TelegramChatBinding(
                    binding_id="researcher_lab",
                    label="Researcher Lab",
                    chat_id="22222",
                    default_agent="researcher",
                    default_space="research",
                    natural_language_services={
                        "reminders": False,
                        "tasks": False,
                        "calendar": False,
                        "braindump": True,
                        "fitness": False,
                        "cross_agent_routing": False,
                    },
                ),
            },
            default_binding_id="assistant_main",
            reminder_binding_id="assistant_main",
            env_values={},
            state_path=self.root / "data" / "telegram-adapter-state.json",
            reminder_state_path=self.root / "data" / "reminders-state.json",
            default_timezone="America/Guayaquil",
        )
        with mock.patch.object(
            bound_adapter.agent_chats["researcher"],
            "reply",
            return_value={
                "reply_text": "Research chat handled the request.",
                "space_key": "research",
                "lane": "L2_balanced",
                "provider": "openai_subscription_session",
                "model": "gpt-5.1",
            },
        ) as reply:
            state = bound_adapter.load_adapter_state()
            bound_adapter.process_updates(
                [self._update_for_chat(60, "compare Gemini and OpenRouter for cheap fallback", chat_id=22222)],
                state=state,
            )

        reply.assert_called_once()
        self.assertIn("Research chat handled", str(self.client.sent_messages[-1]["text"]))
        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["agent_id"], "researcher")
        self.assertEqual(last_route["route_mode"], "bound_chat")

    def test_bound_fitness_chat_uses_conversational_fitness_for_non_command_text(self):
        bound_adapter = telegram_adapter.TelegramAdapter(
            root=self.root,
            backend=self.backend,
            client=self.client,
            chat_bindings={
                "12345": telegram_adapter.TelegramChatBinding(
                    binding_id="assistant_main",
                    label="Assistant Main",
                    chat_id="12345",
                    default_agent="assistant",
                    default_space="general",
                    natural_language_services={
                        "reminders": True,
                        "tasks": True,
                        "calendar": True,
                        "braindump": True,
                        "fitness": True,
                        "cross_agent_routing": True,
                    },
                ),
                "33333": telegram_adapter.TelegramChatBinding(
                    binding_id="fitness_coach",
                    label="Fitness Coach",
                    chat_id="33333",
                    default_agent="fitness_coach",
                    default_space="fitness",
                    natural_language_services={
                        "reminders": False,
                        "tasks": False,
                        "calendar": False,
                        "braindump": False,
                        "fitness": True,
                        "cross_agent_routing": False,
                    },
                ),
            },
            default_binding_id="assistant_main",
            reminder_binding_id="assistant_main",
            env_values={},
            state_path=self.root / "data" / "telegram-adapter-state.json",
            reminder_state_path=self.root / "data" / "reminders-state.json",
            default_timezone="America/Guayaquil",
        )
        with mock.patch.object(
            bound_adapter.agent_chats["fitness_coach"],
            "reply",
            return_value={
                "reply_text": "Keep the planned session and reduce one arm superset if the elbow still feels irritated.",
                "space_key": "fitness",
                "lane": "L2_balanced",
                "provider": "openai_subscription_session",
                "model": "gpt-5.3-codex-spark",
            },
        ) as reply:
            state = bound_adapter.load_adapter_state()
            bound_adapter.process_updates(
                [self._update_for_chat(61, "my elbow feels a bit irritated, should i adjust today's workout?", chat_id=33333)],
                state=state,
            )

        reply.assert_called_once()
        self.assertIn("reduce one arm superset", str(self.client.sent_messages[-1]["text"]))
        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["agent_id"], "fitness_coach")
        self.assertEqual(last_route["action"], "agent_chat")

    def test_switch_to_research_mode_makes_followup_use_researcher_chat(self):
        with mock.patch.object(
            self.adapter.agent_chats["researcher"],
            "reply",
            return_value={
                "reply_text": "Research follow-up handled.",
                "space_key": "research",
                "lane": "L2_balanced",
                "provider": "google_ai_studio_free",
                "model": "gemini-2.5-flash",
            },
        ) as reply:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(24, "switch to research mode")], state=state)
            self.adapter.process_updates([self._update(25, "what should we do next?")], state=state)

        self.assertIn("Conversation focus set", str(self.client.sent_messages[-2]["text"]))
        self.assertIn("Research follow-up handled.", str(self.client.sent_messages[-1]["text"]))
        reply.assert_called_once()
        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["agent_id"], "researcher")
        self.assertEqual(last_route["route_mode"], "focus_mode")

    def test_switch_back_returns_to_assistant(self):
        with mock.patch.object(
            self.adapter.assistant_chat,
            "reply",
            return_value={
                "reply_text": "Assistant took over again.",
                "space_key": "general",
                "lane": "L1_low_cost",
                "provider": "google_ai_studio_free",
                "model": "gemini-2.5-flash-lite",
            },
        ) as reply:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(26, "switch to coding mode")], state=state)
            self.adapter.process_updates([self._update(27, "switch back")], state=state)
            self.adapter.process_updates([self._update(28, "what can you help me with?")], state=state)

        self.assertIn("Switched back", str(self.client.sent_messages[-2]["text"]))
        self.assertIn("Assistant took over again.", str(self.client.sent_messages[-1]["text"]))
        reply.assert_called_once()

    def test_due_reminder_dispatch_and_reply_done(self):
        _, confirmation = self.adapter._create_reminder_from_text("remind me stretch in 1 hour")
        self.assertIn("Reminder created", confirmation)

        reminder_state_path = self.adapter.reminder_state_path
        raw = json.loads(reminder_state_path.read_text(encoding="utf-8"))
        reminder = next(iter(raw["reminders"].values()))
        reminder["remind_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        reminder_state_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")

        state = self.adapter.load_adapter_state()
        sent = self.adapter.scan_and_dispatch_due_reminders(state=state, chat_id="12345", current=datetime.now(timezone.utc))
        self.adapter.save_adapter_state(state)

        self.assertEqual(sent, 1)
        reminder_message = self.client.sent_messages[-1]
        self.assertIn("Reminder:", str(reminder_message["text"]))

        reply_state = self.adapter.load_adapter_state()
        handled = self.adapter.process_updates(
            [self._update(3, "done", reply_to_message_id=int(reminder_message["message_id"]))],
            state=reply_state,
        )
        self.assertEqual(handled, 1)
        updated = json.loads(reminder_state_path.read_text(encoding="utf-8"))
        final_reminder = next(iter(updated["reminders"].values()))
        self.assertEqual(final_reminder["status"], "done")
        self.assertIn("Done. Reminder closed.", str(self.client.sent_messages[-1]["text"]))

    def test_add_task_command_routes_to_personal_task_runtime(self):
        with mock.patch.object(
            self.backend,
            "create_personal_task_runtime",
            return_value={"status": {"recent_results": [{"title": "Buy protein powder"}]}},
        ) as create_task:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(4, "add-task Buy protein powder :: tomorrow 5pm")], state=state)

        create_task.assert_called_once()
        kwargs = create_task.call_args.kwargs
        self.assertEqual(kwargs["title"], "Buy protein powder")
        self.assertEqual(kwargs["due_string"], "tomorrow 5pm")
        self.assertIn("Created personal task", str(self.client.sent_messages[-1]["text"]))

    def test_natural_task_request_routes_to_personal_task_runtime(self):
        with mock.patch.object(
            self.backend,
            "create_personal_task_runtime",
            return_value={"status": {"recent_results": [{"title": "Review syllabus"}]}},
        ) as create_task:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(41, "add review syllabus to my tasks for tomorrow 10am")], state=state)

        kwargs = create_task.call_args.kwargs
        self.assertEqual(kwargs["title"], "review syllabus")
        self.assertEqual(kwargs["due_string"], "tomorrow 10am")
        self.assertIn("Created personal task", str(self.client.sent_messages[-1]["text"]))

    def test_calendar_today_command_uses_calendar_handler(self):
        with mock.patch.object(self.adapter, "_handle_calendar_today", return_value="Calendar today\n- none") as handler:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(5, "calendar today")], state=state)

        handler.assert_called_once()
        self.assertEqual(str(self.client.sent_messages[-1]["text"]), "Calendar today\n- none")

    def test_natural_calendar_tomorrow_request_uses_calendar_handler(self):
        with mock.patch.object(self.adapter, "_handle_calendar_tomorrow", return_value="Calendar tomorrow\n- none") as handler:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(42, "what do i have tomorrow?")], state=state)

        handler.assert_called_once()
        self.assertEqual(str(self.client.sent_messages[-1]["text"]), "Calendar tomorrow\n- none")

    def test_assistant_space_prefix_still_runs_supported_command(self):
        with mock.patch.object(self.adapter, "_handle_calendar_today", return_value="Calendar today\n- none") as handler:
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(51, "calendar: today")], state=state)

        handler.assert_called_once()
        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["space_key"], "calendar")

    def test_calendar_request_gracefully_handles_missing_provider(self):
        with mock.patch.object(self.adapter, "_calendar_client", side_effect=RuntimeError("missing calendar")):
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(6, "calendar today")], state=state)

        self.assertEqual(str(self.client.sent_messages[-1]["text"]), "Calendar is not configured yet.")

    def test_task_request_gracefully_handles_missing_provider(self):
        with mock.patch.object(
            self.backend,
            "create_personal_task_runtime",
            side_effect=RuntimeError("missing task provider"),
        ):
            state = self.adapter.load_adapter_state()
            self.adapter.process_updates([self._update(7, "add-task Buy protein powder")], state=state)

        self.assertEqual(
            str(self.client.sent_messages[-1]["text"]),
            "Personal task provider is not configured yet.",
        )

    def test_fitness_prefix_executes_runtime(self):
        state = self.adapter.load_adapter_state()
        self.adapter.process_updates([self._update(8, "fitness: workout today")], state=state)

        response = str(self.client.sent_messages[-1]["text"])
        self.assertIn("Today's workout plan", response)
        snapshot = self.backend.build_state()
        last_route = snapshot["agent_runtime"]["activity"]["last_route"]
        self.assertEqual(last_route["agent_id"], "fitness_coach")
        self.assertEqual(last_route["space_key"], "fitness")
        self.assertEqual(last_route["action"], "fitness_command")

    def test_unprefixed_workout_commands_execute_fitness_runtime(self):
        state = self.adapter.load_adapter_state()
        self.adapter.process_updates([self._update(9, "start workout")], state=state)
        self.assertIn("Workout started", str(self.client.sent_messages[-1]["text"]))

        state = self.adapter.load_adapter_state()
        self.adapter.process_updates([self._update(10, "log bb curl 8 reps 20kg bb total")], state=state)
        self.assertIn("Logged 1 set(s).", str(self.client.sent_messages[-1]["text"]))

    def test_natural_workout_phrases_execute_fitness_runtime(self):
        state = self.adapter.load_adapter_state()
        self.adapter.process_updates([self._update(43, "what's my workout today?")], state=state)
        self.assertIn("Today's workout plan", str(self.client.sent_messages[-1]["text"]))

    def test_natural_reminder_list_request(self):
        _, _ = self.adapter._create_reminder_from_text("remind me review grades in 2 hours")
        state = self.adapter.load_adapter_state()
        self.adapter.process_updates([self._update(44, "what reminders do i have?")], state=state)
        response = str(self.client.sent_messages[-1]["text"])
        self.assertIn("Pending reminders", response)
        self.assertIn("review grades", response)


if __name__ == "__main__":
    unittest.main()
