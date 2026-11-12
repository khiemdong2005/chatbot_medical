import threading
from unittest.mock import Mock, patch

import pytest

from core.reranker_service import RerankerService
from core.rag_service import MedicalRAGService


def candidates(n=3):
    return [dict(content=chr(65 + i), metadata={"title": str(i), "extra": i},
                 lexical_metadata={"title": str(i)}, vector_metadata=None,
                 lexical_score=1 / (61 + i), vector_score=None, fusion_score=1 / (61 + i),
                 rerank_score=None, distance=None, distance_metric=None, accepted=True,
                 retrieval="bm25") for i in range(n)]


def test_scores_rank_and_preserve_metadata_and_originals():
    rows = candidates()
    model = Mock()
    model.predict.return_value = [0.3, 0.9, 0.6]
    service = RerankerService(timeout_seconds=1)
    service._model = model
    result = service.rerank("synthetic query", rows, 3)
    assert [r["content"] for r in result] == ["B", "C", "A"]
    assert [r["rerank_score"] for r in result] == [0.9, 0.6, 0.3]
    assert result[0]["metadata"] == rows[1]["metadata"]
    assert result[0]["lexical_score"] == rows[1]["lexical_score"]
    assert result[0]["vector_score"] == rows[1]["vector_score"]
    assert all(r["rerank_score"] is None for r in rows)


def test_top_k_and_reuses_model():
    rows = candidates(20)
    model = Mock()
    model.predict.return_value = list(range(20))
    service = RerankerService(timeout_seconds=1)
    service._model = model
    assert [r["content"] for r in service.rerank("query", rows, 3)] == ["T", "S", "R"]
    service.rerank("query", rows, 3)
    assert model.predict.call_count == 2
    assert service._model is model


@pytest.mark.parametrize("scores", [[float('nan'), 1, 2], [1, 2], [float('inf'), 1, 2]])
def test_invalid_scores_fall_back_without_mutating_candidates(scores):
    rows = candidates()
    service = RerankerService(timeout_seconds=1)
    service._model = Mock()
    service._model.predict.return_value = scores
    assert service.rerank("query", rows, 2) == rows[:2]


def test_inference_failure_does_not_log_query(caplog):
    rows = candidates()
    service = RerankerService(timeout_seconds=1)
    service._model = Mock()
    service._model.predict.side_effect = RuntimeError("synthetic-private-query")
    assert service.rerank("synthetic-private-query", rows, 2) == rows[:2]
    assert "synthetic-private-query" not in caplog.text


def test_loading_failure_cached_and_falls_back(caplog):
    rows = candidates()
    service = RerankerService(timeout_seconds=1)
    with patch.dict('sys.modules', {'sentence_transformers': None}):
        assert service.rerank("private-query", rows, 2) == rows[:2]
        assert service._load_failed
        assert service.rerank("private-query", rows, 2) == rows[:2]
    assert "private-query" not in caplog.text


def test_timeout_preserves_order_and_prevents_overlapping_workers():
    rows = candidates()
    entered, release = threading.Event(), threading.Event()
    model = Mock()
    def predict(*args, **kwargs):
        entered.set()
        release.wait(2)
        return [0.3, 0.9, 0.6]
    model.predict.side_effect = predict
    service = RerankerService(timeout_seconds=.05)
    service._model = model
    try:
        assert service.rerank("query", rows, 2) == rows[:2]
        assert entered.is_set()
        assert service.rerank("query", rows, 2) == rows[:2]
        assert model.predict.call_count == 1
    finally:
        release.set()


def test_disabled_keeps_original_candidate_pool_and_never_calls_reranker(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_RERANK_ENABLED", "false")
    rag = MedicalRAGService(db_dir=tmp_path)
    rows = candidates()
    with patch.object(rag, "retrieve_candidates", return_value=rows) as retrieve, \
         patch('core.rag_service.reranker_service.rerank') as rerank:
        output = rag.retrieve_context("query", top_k=2)
    retrieve.assert_called_once_with("query", 2)
    rerank.assert_not_called()
    assert [r["content"] for r in output] == ["A", "B"]


def test_enabled_reranks_twenty_and_retains_legacy_context(tmp_path):
    rag = MedicalRAGService(db_dir=tmp_path, rerank_enabled=True)
    rows = candidates(20)
    with patch.object(rag, "retrieve_candidates", return_value=rows) as retrieve, \
         patch('core.rag_service.reranker_service.rerank', return_value=[rows[1], rows[2]]) as rerank:
        output = rag.retrieve_context("query", top_k=2)
    retrieve.assert_called_once_with("query", 20)
    rerank.assert_called_once_with("query", rows, 2)
    assert [r["content"] for r in output] == ["B", "C"]
    assert set(output[0]) == {"content", "title", "category", "source", "source_url", "distance", "distance_metric", "accepted", "retrieval"}


def test_enabled_reranker_exception_does_not_break_pipeline(tmp_path, caplog):
    rag = MedicalRAGService(db_dir=tmp_path, rerank_enabled=True)
    rows = candidates()
    with patch.object(rag, "retrieve_candidates", return_value=rows), \
         patch('core.rag_service.reranker_service.rerank', side_effect=TimeoutError("private-query")):
        output = rag.retrieve_context("private-query", top_k=2)
    assert [r["content"] for r in output] == ["A", "B"]
    assert "private-query" not in caplog.text


def test_lazy_model_load_once_uses_local_files_and_no_remote_code(monkeypatch):
    from types import SimpleNamespace
    import sys
    model = Mock()
    model.predict.return_value = [0.3, 0.9, 0.6]
    factory = Mock(return_value=model)
    monkeypatch.delenv("RAG_RERANK_MODEL_PATH", raising=False)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=factory))
    service = RerankerService(model_name="synthetic-model", timeout_seconds=1)
    service.rerank("query", candidates(), 2)
    service.rerank("query", candidates(), 2)
    factory.assert_called_once_with("synthetic-model", local_files_only=True, trust_remote_code=False, max_length=512)
    assert model.predict.call_count == 2
