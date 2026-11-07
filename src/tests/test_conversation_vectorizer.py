"""
Offline unit tests for core/conversation_vectorizer.py.

ConversationVectorizer.__init__ loads the embedding model and connects to
Zilliz, so instances are built with __new__ and fake components instead.
"""

import importlib
import sys
from unittest.mock import MagicMock

import pytest

from models.conversation_chunk import SearchResult


@pytest.fixture(scope="module")
def cv_module():
    saved = sys.modules.pop("core.conversation_vectorizer", None)
    mp = pytest.MonkeyPatch()
    mp.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # don't read the real .env
    try:
        module = importlib.import_module("core.conversation_vectorizer")
    finally:
        mp.undo()
    yield module
    if saved is not None:
        sys.modules["core.conversation_vectorizer"] = saved


def _hit(file_name, chunk_index=0, text="本文", score=0.9):
    return SearchResult(
        text=text, speaker="A", timestamp="00:01", file_name=file_name,
        score=score, similarity=score, search_type="hybrid", title="Video",
        chunk_index=chunk_index,
    )


@pytest.fixture
def make_vectorizer(cv_module):
    def make(hits=None, client=True, reranker=None, context=(0, 0)):
        v = cv_module.ConversationVectorizer.__new__(cv_module.ConversationVectorizer)
        v.dense_generator = MagicMock()
        v.dense_generator.generate_query_embedding.return_value = [0.0]
        if client:
            v.bm25_client = MagicMock()
            # Like Zilliz: never more than the requested number of hits.
            v.bm25_client.hybrid_search.side_effect = lambda dq, q, n, k: list(hits or [])[:n]
        else:
            v.bm25_client = None
        v.reranker = reranker
        v.rerank_candidates = 10
        v.context_before, v.context_after = context
        return v
    return make


SEARCHES = ["search_passages", "hybrid_search_bm25"]


# --- #1: failures are raised, never reported as "no results" ---------------

@pytest.mark.parametrize("method", SEARCHES)
def test_missing_client_raises(cv_module, make_vectorizer, method):
    v = make_vectorizer(client=False)
    with pytest.raises(cv_module.SearchUnavailableError):
        getattr(v, method)("駅そば")


@pytest.mark.parametrize("method", SEARCHES)
def test_zilliz_error_propagates(make_vectorizer, method):
    v = make_vectorizer()
    v.bm25_client.hybrid_search.side_effect = ConnectionError("zilliz down")
    with pytest.raises(ConnectionError, match="zilliz down"):
        getattr(v, method)("駅そば")


@pytest.mark.parametrize("method", SEARCHES)
def test_embedding_error_propagates(make_vectorizer, method):
    v = make_vectorizer()
    v.dense_generator.generate_query_embedding.side_effect = RuntimeError("model")
    with pytest.raises(RuntimeError, match="model"):
        getattr(v, method)("駅そば")


@pytest.mark.parametrize("method", SEARCHES)
def test_reranker_error_propagates(make_vectorizer, method):
    reranker = MagicMock()
    reranker.rerank.side_effect = RuntimeError("reranker")
    v = make_vectorizer(hits=[_hit("a.json")], reranker=reranker)
    with pytest.raises(RuntimeError, match="reranker"):
        getattr(v, method)("駅そば")


@pytest.mark.parametrize("method", SEARCHES)
def test_no_matches_still_returns_empty_list(make_vectorizer, method):
    assert getattr(make_vectorizer(hits=[]), method)("駅そば") == []


# --- behaviour that must not change ----------------------------------------

def test_search_passages_keeps_best_chunk_per_video(make_vectorizer):
    hits = [_hit("a.json", 1, score=0.9), _hit("a.json", 5, score=0.8), _hit("b.json", 2, score=0.7)]
    results = make_vectorizer(hits=hits).search_passages("駅そば", limit=5)
    assert [(r.file_name, r.chunk_index) for r in results] == [("a.json", 1), ("b.json", 2)]


def test_neighbour_fetch_failure_falls_back_to_single_chunks(make_vectorizer):
    v = make_vectorizer(hits=[_hit("a.json", 3, text="単独")], context=(1, 3))
    v.bm25_client.fetch_chunk_ranges.side_effect = ConnectionError("fetch failed")

    results = v.search_passages("駅そば")

    assert [r.text for r in results] == ["単独"]


def test_passages_are_widened_with_neighbours(make_vectorizer):
    v = make_vectorizer(hits=[_hit("a.json", 3)], context=(1, 1))
    v.bm25_client.fetch_chunk_ranges.return_value = {
        "a.json": {2: "前の文章です", 3: "ヒットした文章", 4: "次の文章です"}
    }

    (result,) = v.search_passages("駅そば")

    assert result.text == "前の文章ですヒットした文章次の文章です"
    assert result.search_type == "hybrid+context"


# --- #2: no main() that writes to the live collection ------------------------

def test_module_has_no_ingesting_main(cv_module):
    assert not hasattr(cv_module, "main")
    assert not hasattr(cv_module, "S3JsonTextExtractor")


# --- #3: shared candidate/rerank helpers keep the old behaviour --------------

def test_hybrid_search_without_reranker_asks_for_limit(make_vectorizer):
    v = make_vectorizer(hits=[_hit("a.json")])
    v.hybrid_search_bm25("駅そば", limit=3, rerank_k=50)
    v.bm25_client.hybrid_search.assert_called_once_with([0.0], "駅そば", 3, 50)


def test_hybrid_search_with_reranker_reranks_wider_pool(make_vectorizer):
    hits = [_hit(f"{i}.json") for i in range(12)]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda q, results, limit: results[::-1][:limit]
    v = make_vectorizer(hits=hits, reranker=reranker)  # rerank_candidates = 10

    results = v.hybrid_search_bm25("駅そば", limit=3)

    assert v.bm25_client.hybrid_search.call_args.args[2] == 10
    query, candidates, limit = reranker.rerank.call_args.args
    assert (query, len(candidates), limit) == ("駅そば", 10, 3)
    assert len(results) == 3


def test_search_passages_reranks_deduplicated_videos(make_vectorizer):
    hits = [_hit("a.json", 1), _hit("a.json", 2), _hit("b.json", 1)]
    reranker = MagicMock()
    reranker.rerank.side_effect = lambda q, results, limit: results[:limit]
    v = make_vectorizer(hits=hits, reranker=reranker)

    v.search_passages("駅そば", limit=5)

    assert v.bm25_client.hybrid_search.call_args.args[2] == 20  # max(5*4, 10, 20)
    candidates = reranker.rerank.call_args.args[1]
    assert [h.file_name for h in candidates] == ["a.json", "b.json"]


# --- #4/#6: construction (offline, with fake components) --------------------

@pytest.fixture
def fake_components(cv_module, monkeypatch):
    fakes = {
        "TextProcessor": MagicMock(name="TextProcessor"),
        "DenseVectorGenerator": MagicMock(name="DenseVectorGenerator"),
        "ZillizBM25Client": MagicMock(name="ZillizBM25Client"),
        "Reranker": MagicMock(name="Reranker"),
    }
    for name, fake in fakes.items():
        monkeypatch.setattr(cv_module, name, fake)
    monkeypatch.delenv("RERANKER_MODEL", raising=False)
    return fakes


def test_init_uses_dense_generator_directly(cv_module, fake_components):
    v = cv_module.ConversationVectorizer("uri", "token", embedding_model="m",
                                         dense_query_prefix="Q: ", dense_document_prefix="D: ")

    fake_components["DenseVectorGenerator"].assert_called_once_with(
        "m", query_prefix="Q: ", document_prefix="D: "
    )
    assert v.dense_generator is fake_components["DenseVectorGenerator"].return_value
    assert not hasattr(v, "vector_generator")


def test_init_logs_connection_failure_and_keeps_starting(cv_module, fake_components, caplog):
    fake_components["ZillizBM25Client"].side_effect = ConnectionError("unreachable")

    with caplog.at_level("INFO", logger="core.conversation_vectorizer"):
        v = cv_module.ConversationVectorizer("uri", "token")

    assert v.bm25_client is None
    assert any(r.levelname == "ERROR" and "unreachable" in r.getMessage() for r in caplog.records)
    with pytest.raises(cv_module.SearchUnavailableError):
        v.search_passages("駅そば")


def test_init_without_uri_logs_warning(cv_module, fake_components, caplog):
    with caplog.at_level("WARNING", logger="core.conversation_vectorizer"):
        v = cv_module.ConversationVectorizer("", "")

    assert v.bm25_client is None
    fake_components["ZillizBM25Client"].assert_not_called()
    assert any(r.levelname == "WARNING" and "ZILLIZ_URI" in r.getMessage() for r in caplog.records)


def test_neighbour_fetch_failure_is_logged(make_vectorizer, caplog):
    v = make_vectorizer(hits=[_hit("a.json", 3)], context=(1, 1))
    v.bm25_client.fetch_chunk_ranges.side_effect = ConnectionError("fetch failed")

    with caplog.at_level("WARNING", logger="core.conversation_vectorizer"):
        v.search_passages("駅そば")

    assert any("fetch failed" in r.getMessage() for r in caplog.records)


def test_module_does_not_print(cv_module):
    import inspect
    assert "print(" not in inspect.getsource(cv_module)


# --- #5: importing the module has no side effects ----------------------------

def test_import_does_not_load_dotenv(monkeypatch):
    saved = sys.modules.pop("core.conversation_vectorizer", None)
    spy = MagicMock(name="load_dotenv")
    monkeypatch.setattr("dotenv.load_dotenv", spy)
    try:
        importlib.import_module("core.conversation_vectorizer")
    finally:
        if saved is not None:
            sys.modules["core.conversation_vectorizer"] = saved
    spy.assert_not_called()
