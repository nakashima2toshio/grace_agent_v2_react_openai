# tests/grace/test_vertical_scope.py
"""業界プロファイルのコア配線（検索スコープ・方針注入）の単体テスト。

Qdrant・API キー不要。
対象:
- RAGSearchTool._apply_allowed_collections（許可リスト型の検索スコープ制限）
- ReasoningTool._build_prompt（config.llm.prompt_addendum の注入）
- 設定既定値（allowed_collections / prompt_addendum）
- agent_support_example.PROFILES の手動管理OpenAIコレクション名
"""
from unittest.mock import MagicMock, patch

from agent_support_example import PROFILES
from grace.config import GraceConfig, LLMConfig, QdrantConfig
from grace.tools import RAGSearchTool, ReasoningTool


def make_reasoning_tool(config: GraceConfig) -> ReasoningTool:
    """LLM クライアントを生成せずに ReasoningTool を組み立てる（_build_prompt 検証用）。"""
    tool = ReasoningTool.__new__(ReasoningTool)
    tool.config = config
    tool.model_name = config.llm.model
    return tool


class TestApplyAllowedCollections:
    CANDIDATES = ["wikipedia_ja", "livedoor", "cc_news", "gov_faq_anthropic"]
    # 実環境はサフィックス付きコレクション名が多い（ライブ実行ログで確認された実名）
    REAL_CANDIDATES = ["cc_news_2per_anthropic", "wikipedia_ja_5per", "cc_news_2per",
                       "fineweb_edu_ja_5per"]

    def test_empty_allowlist_means_no_restriction(self):
        assert RAGSearchTool._apply_allowed_collections(self.CANDIDATES, []) == self.CANDIDATES

    def test_scopes_to_intersection_preserving_order(self):
        allowed = ["gov_faq_anthropic", "wikipedia_ja"]
        assert RAGSearchTool._apply_allowed_collections(self.CANDIDATES, allowed) == [
            "wikipedia_ja", "gov_faq_anthropic",
        ]

    def test_blocks_out_of_scope_fallback(self):
        # 業界外コレクション（livedoor/cc_news）へのフォールバック漏れを塞ぐ
        scoped = RAGSearchTool._apply_allowed_collections(self.CANDIDATES, ["wikipedia_ja"])
        assert scoped == ["wikipedia_ja"]

    def test_partial_match_scopes_suffixed_collection_names(self):
        # 完全一致だと wikipedia_ja_5per に一致せずスコープが素通りするバグの回帰テスト。
        # search_priority と同じ部分一致（含有）で判定する
        allowed = ["gov_faq_anthropic", "gov_laws_anthropic", "wikipedia_ja"]
        scoped = RAGSearchTool._apply_allowed_collections(self.REAL_CANDIDATES, allowed)
        assert scoped == ["wikipedia_ja_5per"]

    def test_no_match_stops_without_fallback(self):
        # 手動管理collectionが未登録でも、業界外collectionへフォールバックしない。
        allowed = ["saas_docs_anthropic", "saas_api_anthropic"]
        assert RAGSearchTool._apply_allowed_collections(self.CANDIDATES, allowed) == []
        assert RAGSearchTool._apply_allowed_collections(self.REAL_CANDIDATES, allowed) == []

    def test_empty_candidates_stay_empty(self):
        assert RAGSearchTool._apply_allowed_collections([], ["gov_faq_anthropic"]) == []


class TestReadOnlyCollectionValidation:
    def make_tool(self, *, points: int = 1, dimensions: int = 3072):
        config = GraceConfig()
        config.embedding.dimensions = 3072
        tool = RAGSearchTool(config=config)
        client = MagicMock()
        info = MagicMock()
        info.points_count = points
        info.config.params.vectors.size = dimensions
        client.get_collection.return_value = info
        tool._client = client
        return tool, client

    def test_valid_collection_is_searchable_without_writes(self):
        tool, client = self.make_tool()

        assert tool._is_collection_searchable("gov_faq_ollama") is True
        client.create_collection.assert_not_called()
        client.recreate_collection.assert_not_called()
        client.upsert.assert_not_called()
        client.delete_collection.assert_not_called()

    def test_empty_collection_stops_without_registration(self):
        tool, client = self.make_tool(points=0)

        assert tool._is_collection_searchable("gov_faq_ollama") is False
        client.upsert.assert_not_called()
        client.create_collection.assert_not_called()

    def test_dimension_mismatch_stops_without_recreate(self):
        tool, client = self.make_tool(dimensions=768)

        assert tool._is_collection_searchable("gov_faq_ollama") is False
        client.recreate_collection.assert_not_called()
        client.delete_collection.assert_not_called()

    def test_missing_collection_stops_without_create(self):
        tool, client = self.make_tool()
        client.get_collection.side_effect = RuntimeError("not found")

        assert tool._is_collection_searchable("gov_faq_ollama") is False
        client.create_collection.assert_not_called()

    @patch("agent_tools.search_rag_knowledge_base_structured")
    def test_broken_collection_is_skipped_and_next_collection_is_searched(self, mock_search):
        config = GraceConfig()
        config.qdrant.restrict_to_collection = False
        config.qdrant.allowed_collections = []
        tool = RAGSearchTool(config=config)
        tool._get_all_collections_dynamic = MagicMock(
            return_value=["broken_collection", "saas_docs_ollama"]
        )
        tool._is_collection_searchable = MagicMock(
            side_effect=lambda name: name == "saas_docs_ollama"
        )
        mock_search.return_value = [{"score": 0.9, "payload": {"answer": "ok"}}]

        result = tool.execute("APIの使い方")

        assert result.success is True
        mock_search.assert_called_once_with("APIの使い方", "saas_docs_ollama")


class TestPromptAddendumInjection:
    def test_addendum_is_injected_into_prompt(self):
        config = GraceConfig()
        config.llm.prompt_addendum = "断定を避け、該当ページ・担当課を明示。個人情報は尋ねない。"
        tool = make_reasoning_tool(config)
        prompt = tool._build_prompt("住民票の取り方は？", context=None, sources=None)
        assert "【業務方針（遵守）】" in prompt
        assert "断定を避け" in prompt
        # 方針はシステム指示の直後（参照情報・質問より前）に入る
        assert prompt.index("【業務方針（遵守）】") < prompt.index("【ユーザーの質問】")

    def test_no_addendum_no_section(self):
        tool = make_reasoning_tool(GraceConfig())
        prompt = tool._build_prompt("住民票の取り方は？", context=None, sources=None)
        assert "【業務方針（遵守）】" not in prompt

    def test_addendum_coexists_with_context_and_sources(self):
        config = GraceConfig()
        config.llm.prompt_addendum = "製品バージョンを明示する。"
        tool = make_reasoning_tool(config)
        sources = [{"score": 0.9, "collection": "saas_docs_anthropic",
                    "payload": {"question": "Q", "answer": "A", "source": "doc.md"}}]
        prompt = tool._build_prompt("APIのレート制限は？", context="補足", sources=sources)
        assert "【業務方針（遵守）】" in prompt
        assert "【参照情報】" in prompt
        assert "【補足コンテキスト】" in prompt


class TestConfigDefaults:
    def test_allowed_collections_default_empty(self):
        assert QdrantConfig().allowed_collections == []

    def test_prompt_addendum_default_empty(self):
        assert LLMConfig().prompt_addendum == ""


class TestProfileCollections:
    """全プロファイルが手動管理OpenAIコレクションだけを参照すること。"""

    def test_collection_names_follow_convention(self):
        assert PROFILES["gov"].collections == ["gov_faq_ollama"]
        assert PROFILES["saas"].collections == ["saas_api_ollama", "saas_docs_ollama"]
        assert PROFILES["ec"].collections == ["ec_faq_ollama"]

    def test_profiles_use_only_manually_managed_collections(self):
        expected = {
            "gov_faq_ollama", "saas_api_ollama", "saas_docs_ollama", "ec_faq_ollama"
        }
        for key, profile in PROFILES.items():
            assert set(profile.collections) <= expected, key
