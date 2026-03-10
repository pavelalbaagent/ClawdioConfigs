import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import knowledge_source_search as ks  # noqa: E402


class KnowledgeSourceSearchTests(unittest.TestCase):
    def test_search_enabled_sources_returns_ranked_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            corpus_root = tmp_path / "corpus" / "ai_tools"
            corpus_root.mkdir(parents=True)
            (corpus_root / "blog_OpenAI_News_Introducing_GPT-5_3-Codex.md").write_text(
                "# Introducing GPT-5.3 Codex\n\nOpenAI released GPT-5.3 Codex for coding and reasoning workflows.\n",
                encoding="utf-8",
            )
            config_path = tmp_path / "knowledge_sources.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "knowledge_sources:",
                        "  active_profile: default",
                        "  profiles:",
                        "    default:",
                        "      enabled_sources:",
                        "        - ai_tools_db",
                        "  sources:",
                        "    ai_tools_db:",
                        "      enabled: true",
                        "      root_candidates:",
                        f"        - {corpus_root}",
                        "      allowed_agents:",
                        "        - researcher",
                        "      allowed_spaces:",
                        "        - research",
                        "      top_k: 3",
                        "      auto_query:",
                        "        always_for_agents:",
                        "          - researcher",
                    ]
                ),
                encoding="utf-8",
            )

            groups = ks.search_enabled_sources(
                config_path=config_path,
                query="What do we know about GPT-5.3 Codex?",
                agent_id="researcher",
                space_key="research",
                top_k=3,
            )
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["source_id"], "ai_tools_db")
            self.assertIn("GPT-5.3 Codex", groups[0]["results"][0]["title"])

    def test_search_enabled_sources_resolves_relative_roots_from_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            corpus_root = tmp_path / "fitness" / "knowledge"
            corpus_root.mkdir(parents=True)
            (corpus_root / "2026-03-coaching-priors.md").write_text(
                "# Coaching Priors\n\nMild elbow irritation should first reduce myorep density before swapping exercises.\n",
                encoding="utf-8",
            )
            config_dir = tmp_path / "config"
            config_dir.mkdir()
            config_path = config_dir / "knowledge_sources.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "knowledge_sources:",
                        "  active_profile: default",
                        "  profiles:",
                        "    default:",
                        "      enabled_sources:",
                        "        - fitness_grounding",
                        "  sources:",
                        "    fitness_grounding:",
                        "      enabled: true",
                        "      root_candidates:",
                        "        - ../fitness/knowledge",
                        "      allowed_agents:",
                        "        - fitness_coach",
                        "      allowed_spaces:",
                        "        - fitness",
                        "      top_k: 3",
                        "      auto_query:",
                        "        keyword_hints:",
                        "          - elbow",
                    ]
                ),
                encoding="utf-8",
            )

            groups = ks.search_enabled_sources(
                config_path=config_path,
                query="My elbow feels irritated during curls.",
                agent_id="fitness_coach",
                space_key="fitness",
                top_k=3,
            )

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["source_id"], "fitness_grounding")
            self.assertIn("myorep density", groups[0]["results"][0]["excerpt"])


if __name__ == "__main__":
    unittest.main()
