"""agent_tools の3072次元検索限定と送信前防御の単体テスト。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import agent_tools


def _collection(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _collection_info(dimensions):
    return SimpleNamespace(
        points_count=1,
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=dimensions))
        ),
    )


@pytest.fixture(autouse=True)
def reset_collection_cache(monkeypatch):
    monkeypatch.setattr(agent_tools, "_collections_cache", None)
    monkeypatch.setattr(agent_tools, "_collections_cache_time", 0.0)


def test_get_collection_dense_dimension_supports_single_and_named_vectors(monkeypatch):
    qdrant = MagicMock()
    monkeypatch.setattr(agent_tools, "client", qdrant)

    qdrant.get_collection.return_value = _collection_info(3072)
    assert agent_tools.get_collection_dense_dimension("single") == 3072

    named = _collection_info(None)
    named.config.params.vectors = {
        "dense": SimpleNamespace(size=3072),
        "dense_backup": SimpleNamespace(size=3072),
    }
    qdrant.get_collection.return_value = named
    assert agent_tools.get_collection_dense_dimension("named") == 3072

    named.config.params.vectors["legacy"] = SimpleNamespace(size=768)
    assert agent_tools.get_collection_dense_dimension("mixed_named") is None


def test_searchable_collections_exclude_768_and_refresh_dimensions_within_ttl(
    monkeypatch, caplog
):
    qdrant = MagicMock()
    qdrant.get_collections.return_value.collections = [
        _collection("legacy_768"),
        _collection("current_3072"),
    ]
    dimensions = {"legacy_768": 768, "current_3072": 3072}
    qdrant.get_collection.side_effect = lambda name: _collection_info(dimensions[name])
    monkeypatch.setattr(agent_tools, "client", qdrant)

    assert agent_tools.get_searchable_collections_cached() == ["current_3072"]
    assert "legacy_768" in caplog.text
    assert "dim=768" in caplog.text

    # 生の一覧はTTLキャッシュ中でも、次元は毎回再確認する。
    dimensions["current_3072"] = 768
    assert agent_tools.get_searchable_collections_cached() == []
    assert qdrant.get_collections.call_count == 1


def test_all_collection_search_sends_only_3072_collections(monkeypatch):
    qdrant = MagicMock()
    qdrant.get_collections.return_value.collections = [
        _collection("legacy_768"),
        _collection("current_3072"),
    ]
    qdrant.get_collection.side_effect = lambda name: _collection_info(
        768 if name == "legacy_768" else 3072
    )
    monkeypatch.setattr(agent_tools, "client", qdrant)
    embed_query = MagicMock(return_value=[0.1] * 3072)
    monkeypatch.setattr(agent_tools, "embed_query", embed_query)
    monkeypatch.setattr(agent_tools, "embed_sparse_query_unified", MagicMock(return_value=None))
    parallel = MagicMock(return_value=[])
    monkeypatch.setattr(
        agent_tools.parallel_search_engine,
        "search_all_collections",
        parallel,
    )

    result = agent_tools.search_rag_knowledge_base("質問")

    assert "NO_RAG_RESULT" in result
    assert parallel.call_args.kwargs["collections"] == ["current_3072"]
    embed_query.assert_called_once_with("質問")


def test_all_collection_search_does_not_call_parallel_when_only_768_exists(monkeypatch):
    qdrant = MagicMock()
    qdrant.get_collections.return_value.collections = [_collection("legacy_768")]
    qdrant.get_collection.return_value = _collection_info(768)
    monkeypatch.setattr(agent_tools, "client", qdrant)
    monkeypatch.setattr(agent_tools, "embed_query", MagicMock(return_value=[0.1] * 3072))
    monkeypatch.setattr(agent_tools, "embed_sparse_query_unified", MagicMock(return_value=None))
    parallel = MagicMock()
    monkeypatch.setattr(
        agent_tools.parallel_search_engine,
        "search_all_collections",
        parallel,
    )

    result = agent_tools.search_rag_knowledge_base("質問")

    assert "利用可能なコレクションがありません" in result
    parallel.assert_not_called()


def test_structured_search_rejects_768_before_qdrant_search(monkeypatch):
    qdrant = MagicMock()
    qdrant.get_collection.return_value = _collection_info(768)
    monkeypatch.setattr(agent_tools, "client", qdrant)
    monkeypatch.setattr(
        agent_tools,
        "get_existing_collections_cached",
        MagicMock(return_value=["legacy_768"]),
    )
    search_collection = MagicMock()
    monkeypatch.setattr(agent_tools, "search_collection", search_collection)

    result = agent_tools.search_rag_knowledge_base_structured(
        "質問",
        "legacy_768",
        use_hybrid_search=False,
        precomputed_query_vector=[0.1] * 3072,
    )

    assert "RAG_TOOL_UNSUPPORTED_DIMENSION" in result
    assert "768 次元" in result
    search_collection.assert_not_called()


def test_structured_search_rejects_wrong_query_dimension_before_qdrant_search(
    monkeypatch,
):
    qdrant = MagicMock()
    qdrant.get_collection.return_value = _collection_info(3072)
    monkeypatch.setattr(agent_tools, "client", qdrant)
    monkeypatch.setattr(
        agent_tools,
        "get_existing_collections_cached",
        MagicMock(return_value=["current_3072"]),
    )
    search_collection = MagicMock()
    monkeypatch.setattr(agent_tools, "search_collection", search_collection)

    result = agent_tools.search_rag_knowledge_base_structured(
        "質問",
        "current_3072",
        use_hybrid_search=False,
        precomputed_query_vector=[0.1] * 768,
    )

    assert "検索ベクトルは 768 次元" in result
    search_collection.assert_not_called()


def test_cached_search_rejects_explicit_768_without_structured_search(monkeypatch):
    qdrant = MagicMock()
    qdrant.get_collection.return_value = _collection_info(768)
    monkeypatch.setattr(agent_tools, "client", qdrant)
    monkeypatch.setattr(agent_tools, "embed_query", MagicMock(return_value=[0.1] * 3072))
    monkeypatch.setattr(agent_tools, "embed_sparse_query_unified", MagicMock(return_value=None))
    structured = MagicMock()
    monkeypatch.setattr(agent_tools, "search_rag_knowledge_base_structured", structured)

    result = agent_tools.search_rag_knowledge_base_cached(
        "質問",
        session_id="session",
        collection_name="legacy_768",
        use_hybrid_search=False,
    )

    assert "RAG_TOOL_UNSUPPORTED_DIMENSION" in result
    structured.assert_not_called()


def test_cached_768_collection_falls_back_to_3072_full_search(monkeypatch):
    qdrant = MagicMock()
    qdrant.get_collection.side_effect = lambda name: _collection_info(
        768 if name == "legacy_768" else 3072
    )
    monkeypatch.setattr(agent_tools, "client", qdrant)
    monkeypatch.setattr(agent_tools, "embed_query", MagicMock(return_value=[0.1] * 3072))
    monkeypatch.setattr(agent_tools, "embed_sparse_query_unified", MagicMock(return_value=None))
    monkeypatch.setattr(
        agent_tools.collection_cache,
        "get",
        MagicMock(
            return_value=SimpleNamespace(
                collection_name="legacy_768",
                last_score=0.9,
                hit_count=1,
            )
        ),
    )
    monkeypatch.setattr(
        agent_tools,
        "get_searchable_collections_cached",
        MagicMock(return_value=["current_3072"]),
    )
    structured = MagicMock()
    monkeypatch.setattr(agent_tools, "search_rag_knowledge_base_structured", structured)
    parallel = MagicMock(return_value=[])
    monkeypatch.setattr(
        agent_tools.parallel_search_engine,
        "search_all_collections",
        parallel,
    )

    result = agent_tools.search_rag_knowledge_base_cached(
        "質問",
        session_id="session",
        use_hybrid_search=False,
    )

    assert "NO_RAG_RESULT" in result
    structured.assert_not_called()
    assert parallel.call_args.kwargs["collections"] == ["current_3072"]
