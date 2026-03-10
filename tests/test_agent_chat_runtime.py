import json
import subprocess as real_subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "scripts"))

import assistant_chat_runtime  # noqa: E402
from assistant_chat_runtime import AgentChatRuntime  # noqa: E402
from backend import DashboardBackend  # noqa: E402

REAL_SUBPROCESS_RUN = real_subprocess.run


class AgentChatRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True)
        (self.root / "contracts" / "braindump").mkdir(parents=True)
        (self.root / "contracts" / "fitness").mkdir(parents=True)
        (self.root / "telemetry").mkdir(parents=True)
        (self.root / "baselines" / "agent_md").mkdir(parents=True)
        (self.root / "fitness").mkdir(parents=True)
        (self.root / "fitness" / "logs").mkdir(parents=True)
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
            "knowledge_sources.yaml",
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
        for name in ("ATHLETE_PROFILE.md", "PROGRAM.md", "EXERCISE_LIBRARY.md", "RULES.md", "SESSION_QUEUE.md"):
            shutil.copy(ROOT / "fitness" / name, self.root / "fitness" / name)
        for name in ("MEMORY.md", "USER.md", "SOUL.md", "SESSION.md", "TODO.md"):
            (self.root / "baselines" / "agent_md" / name).write_text(f"# {name}\n\n## Notes\nExisting context for {name}.\n", encoding="utf-8")

        self.backend = DashboardBackend(root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_researcher_chat_uses_agent_specific_state_and_memory(self):
        runtime = AgentChatRuntime(
            root=self.root,
            backend=self.backend,
            env_values={"GEMINI_API_KEY": "test-key", "OPENAI_API_KEY": "emb-key"},
            agent_id="researcher",
        )
        route = {"agent_id": "researcher", "space_key": "research", "route_mode": "explicit_agent_prefix"}

        memory_payload = {
            "mode": "semantic",
            "results": [
                {
                    "source_path": str(self.root / "baselines" / "agent_md" / "MEMORY.md"),
                    "heading": "Notes",
                    "content": "Previous research context about provider tradeoffs.",
                }
            ],
        }

        def fake_run(cmd, cwd=None, capture_output=None, text=None, env=None):
            joined = " ".join(str(part) for part in cmd)
            if "memory_search.py" in joined:
                return mock.Mock(returncode=0, stdout=json.dumps(memory_payload), stderr="")
            return REAL_SUBPROCESS_RUN(cmd, cwd=cwd, capture_output=capture_output, text=text, env=env)

        with mock.patch(
            "assistant_chat_runtime.resolve_chat_route",
            return_value={
                "lane": "L2_balanced",
                "requested_lane": "L2_balanced",
                "downgraded_from_lane": None,
                "provider": "google_ai_studio_free",
                "provider_cfg": {"transport": "google_generative_language"},
                "model": "gemini-2.5-flash",
            },
        ), mock.patch("assistant_chat_runtime.subprocess.run", side_effect=fake_run) as run_mock, mock.patch(
            "assistant_chat_runtime.invoke_chat_provider",
            return_value={
                "text": "Recommendation: keep Gemini first and OpenRouter as overflow.",
                "prompt_tokens": 120,
                "completion_tokens": 40,
                "latency_ms": 80,
            },
        ) as provider_mock:
            result = runtime.reply(text="Compare Gemini and OpenRouter for fallback routing.", route=route)

        provider_mock.assert_called_once()
        self.assertTrue(
            any("memory_search.py" in " ".join(str(part) for part in call.args[0]) for call in run_mock.call_args_list),
            msg=f"memory_search.py not invoked: {run_mock.call_args_list}",
        )
        self.assertEqual(result["agent_id"], "researcher")
        self.assertEqual(result["space_key"], "research")
        self.assertTrue(result["memory_context_used"])
        self.assertTrue((self.root / "data" / "researcher-chat-state.json").exists())

    def test_builder_chat_persists_project_space(self):
        runtime = AgentChatRuntime(
            root=self.root,
            backend=self.backend,
            env_values={"GEMINI_API_KEY": "test-key"},
            agent_id="builder",
        )
        route = {
            "agent_id": "builder",
            "space_key": "projects/openclaw-v2-rebuild",
            "project_name": "OpenClaw V2 Rebuild",
            "route_mode": "explicit_agent_prefix",
        }

        def fake_run(cmd, cwd=None, capture_output=None, text=None, env=None):
            joined = " ".join(str(part) for part in cmd)
            if "memory_search.py" in joined:
                return mock.Mock(returncode=0, stdout=json.dumps({"mode": "keyword", "results": []}), stderr="")
            return REAL_SUBPROCESS_RUN(cmd, cwd=cwd, capture_output=capture_output, text=text, env=env)

        with mock.patch(
            "assistant_chat_runtime.resolve_chat_route",
            return_value={
                "lane": "L2_balanced",
                "requested_lane": "L2_balanced",
                "downgraded_from_lane": None,
                "provider": "google_ai_studio_free",
                "provider_cfg": {"transport": "google_generative_language"},
                "model": "gemini-2.5-flash",
            },
        ), mock.patch("assistant_chat_runtime.subprocess.run", side_effect=fake_run) as run_mock, mock.patch(
            "assistant_chat_runtime.invoke_chat_provider",
            return_value={
                "text": "Start with the dashboard badge in the runtime panel and add a small backend field for status.",
                "prompt_tokens": 110,
                "completion_tokens": 36,
                "latency_ms": 70,
            },
        ):
            result = runtime.reply(text="Plan a runtime status badge implementation.", route=route)

        self.assertTrue(
            any("memory_search.py" in " ".join(str(part) for part in call.args[0]) for call in run_mock.call_args_list),
            msg=f"memory_search.py not invoked: {run_mock.call_args_list}",
        )
        self.assertEqual(result["space_key"], "projects/openclaw-v2-rebuild")
        raw = json.loads((self.root / "data" / "builder-chat-state.json").read_text(encoding="utf-8"))
        self.assertIn("projects/openclaw-v2-rebuild", raw["spaces"])

    def test_fitness_chat_uses_dedicated_state_and_provider_preference(self):
        runtime = AgentChatRuntime(
            root=self.root,
            backend=self.backend,
            env_values={"GEMINI_API_KEY": "test-key", "OPENAI_API_KEY": "emb-key"},
            agent_id="fitness_coach",
        )
        route = {"agent_id": "fitness_coach", "space_key": "fitness", "route_mode": "bound_chat"}

        memory_payload = {
            "mode": "semantic",
            "results": [
                {
                    "source_path": str(self.root / "fitness" / "PROGRAM.md"),
                    "heading": "Program",
                    "content": "Recent notes mention arm specialization, incline bias, and no-bench Saturday.",
                }
            ],
        }

        def fake_run(cmd, cwd=None, capture_output=None, text=None, env=None):
            joined = " ".join(str(part) for part in cmd)
            if "memory_search.py" in joined:
                return mock.Mock(returncode=0, stdout=json.dumps(memory_payload), stderr="")
            return REAL_SUBPROCESS_RUN(cmd, cwd=cwd, capture_output=capture_output, text=text, env=env)

        with mock.patch(
            "assistant_chat_runtime.resolve_chat_route",
            return_value={
                "lane": "L2_balanced",
                "requested_lane": "L2_balanced",
                "downgraded_from_lane": None,
                "provider": "openai_subscription_session",
                "provider_cfg": {"required_command": "codex", "transport": "codex_exec_session"},
                "model": "gpt-5.3-codex-spark",
                "max_output_tokens": 2000,
            },
        ), mock.patch("assistant_chat_runtime.subprocess.run", side_effect=fake_run) as run_mock, mock.patch(
            "assistant_chat_runtime.invoke_chat_provider",
            return_value={
                "text": "Keep today's M1 structure and swap only if elbow discomfort shows up again.",
                "prompt_tokens": 140,
                "completion_tokens": 34,
                "latency_ms": 95,
            },
        ) as provider_mock:
            result = runtime.reply(text="Should I keep today's arm work or swap anything because my elbows feel a bit off?", route=route)

        self.assertTrue(
            any("memory_search.py" in " ".join(str(part) for part in call.args[0]) for call in run_mock.call_args_list),
            msg=f"memory_search.py not invoked: {run_mock.call_args_list}",
        )
        self.assertEqual(result["agent_id"], "fitness_coach")
        self.assertEqual(result["provider"], "openai_subscription_session")
        self.assertEqual(result["space_key"], "fitness")
        self.assertTrue((self.root / "data" / "fitness-coach-chat-state.json").exists())
        provider_kwargs = provider_mock.call_args.kwargs
        system_prompt = provider_kwargs["system_prompt"]
        self.assertEqual(provider_kwargs["max_output_tokens"], 2000)
        self.assertIn("Canonical fitness program context:", system_prompt)
        self.assertIn("M1: Mon (Bench 1)", system_prompt)
        self.assertIn("A1 DB Incline Press: 4 x 10-15", system_prompt)
        self.assertIn("Session queue pointer:", system_prompt)

    def test_resolve_chat_route_applies_agent_provider_model_override(self):
        with mock.patch("assistant_chat_runtime.shutil.which", return_value="/usr/local/bin/codex"):
            plan = assistant_chat_runtime.resolve_chat_route(
                agent_id="builder",
                situation="coding_and_integration",
                models_path=self.root / "config" / "models.yaml",
                agents_path=self.root / "config" / "agents.yaml",
                env_values={},
            )

        self.assertEqual(plan["provider"], "openai_subscription_session")
        self.assertEqual(plan["model"], "gpt-5.1-codex-mini")

    def test_researcher_chat_can_use_local_knowledge_source_context(self):
        corpus_root = self.root / "aitoolsdb" / "corpus" / "ai_tools"
        corpus_root.mkdir(parents=True)
        (corpus_root / "blog_OpenAI_News_Introducing_GPT-5_3-Codex.md").write_text(
            "# Introducing GPT-5.3 Codex\n\nOpenAI released GPT-5.3 Codex for coding and reasoning workflows.\n",
            encoding="utf-8",
        )
        knowledge_cfg = self.root / "config" / "knowledge_sources.yaml"
        text = knowledge_cfg.read_text(encoding="utf-8")
        text = text.replace("/opt/aitoolsdb/corpus/ai_tools", str(corpus_root), 1)
        knowledge_cfg.write_text(text, encoding="utf-8")

        runtime = AgentChatRuntime(
            root=self.root,
            backend=self.backend,
            env_values={"GEMINI_API_KEY": "test-key"},
            agent_id="researcher",
        )
        route = {"agent_id": "researcher", "space_key": "research", "route_mode": "bound_chat"}

        with mock.patch(
            "assistant_chat_runtime.resolve_chat_route",
            return_value={
                "lane": "L2_balanced",
                "requested_lane": "L2_balanced",
                "downgraded_from_lane": None,
                "provider": "google_ai_studio_free",
                "provider_cfg": {"transport": "google_generative_language"},
                "model": "gemini-2.5-flash",
                "max_output_tokens": 1200,
            },
        ), mock.patch(
            "assistant_chat_runtime.invoke_chat_provider",
            return_value={
                "text": "Use GPT-5.3 Codex only when the coding workload justifies it.",
                "prompt_tokens": 160,
                "completion_tokens": 30,
                "latency_ms": 70,
            },
        ) as provider_mock:
            result = runtime.reply(text="What do we know about GPT-5.3 Codex?", route=route)

        system_prompt = provider_mock.call_args.kwargs["system_prompt"]
        self.assertIn("Relevant local knowledge sources:", system_prompt)
        self.assertIn("GPT-5.3 Codex", system_prompt)
        self.assertTrue(result["knowledge_context_used"])


if __name__ == "__main__":
    unittest.main()
