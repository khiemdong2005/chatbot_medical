import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import chromadb
from core.rag_service import MedicalRAGService, search_tokens
from scripts.ingest import run_ingestion


def test_rag_distance_metric_and_acceptance_threshold(tmp_path):
    """Kiểm thử 7a: RAG sử dụng L2 distance, minh bạch metric và lọc theo ngưỡng chấp nhận."""
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.create_collection("medical_knowledge", embedding_function=None)

    # Thêm 2 tài liệu: 1 tài liệu khớp cao, 1 tài liệu hoàn toàn không liên quan
    collection.add(
        ids=["doc_relevant", "doc_irrelevant"],
        embeddings=[[0.0, 0.0], [4.0, 4.0]],
        documents=[
            "Bệnh cảm cúm: Triệu chứng sốt, ho, đau họng. Cách chăm sóc: nghỉ ngơi, uống nhiều nước.",
            "Lập trình hướng đối tượng trong Python và cách sử dụng decorator."
        ],
        metadatas=[
            {"title": "Cảm cúm mùa", "category": "Hô hấp", "source": "MedlinePlus", "source_url": "https://medlineplus.gov/flu"},
            {"title": "Tài liệu kỹ thuật", "category": "CNTT", "source": "DevDocs", "source_url": "https://dev.to"}
        ]
    )

    rag = MedicalRAGService(db_dir=tmp_path, acceptance_threshold=1.35, vector_search_enabled=True)
    # Explicit vectors above and a deterministic query result avoid model
    # downloads/network requests in a regression about distance acceptance.
    with patch.object(rag.collection, "query", return_value={
        "documents": [["Bệnh cảm cúm: Triệu chứng sốt, ho, đau họng. Cách chăm sóc: nghỉ ngơi, uống nhiều nước.",
                       "Lập trình hướng đối tượng trong Python và cách sử dụng decorator."]],
        "metadatas": [[{"title": "Cảm cúm mùa", "source_url": "https://medlineplus.gov/flu"}, {"title": "Tài liệu kỹ thuật"}]],
        "distances": [[0.25, 5.0]],
    }) as query:
        docs = rag.retrieve_context("triệu chứng sốt và đau họng", top_k=2)
    query.assert_called_once()

    assert len(docs) == 1  # Tài liệu y khoa phù hợp được nhận, tài liệu CNTT bị loại bỏ do vượt ngưỡng L2
    first_doc = docs[0]
    assert first_doc["distance_metric"] == "l2"
    assert "distance" in first_doc
    assert first_doc["accepted"] is True
    assert first_doc["title"] == "Cảm cúm mùa"


def test_ingestion_failure_does_not_corrupt_active_version(tmp_path):
    """Kiểm thử 7b: Ingestion thất bại không phá phiên bản tri thức đang hoạt động."""
    db_dir = tmp_path / "vectordb"
    db_dir.mkdir(parents=True, exist_ok=True)

    # 1. Khởi tạo một collection đang hoạt động với 5 tài liệu
    client = chromadb.PersistentClient(path=str(db_dir))
    active_col = client.create_collection("medical_knowledge_v1", embedding_function=None)
    active_col.add(
        ids=[f"id_{i}" for i in range(5)],
        embeddings=[[float(i), 0.0] for i in range(5)],
        documents=[f"Nội dung y khoa {i}" for i in range(5)],
        metadatas=[{"title": f"Bài {i}"} for i in range(5)]
    )

    # Đánh dấu medical_knowledge_v1 là active
    meta_file = db_dir / "active_collection.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"active_collection": "medical_knowledge_v1", "document_count": 5}, f)

    assert active_col.count() == 5

    # 2. Giả lập quá trình ingestion mới bị lỗi giữa chừng
    with patch("scripts.ingest.load_curated_medlineplus_documents") as mock_load:
        mock_load.return_value = []  # Giả lập thư mục curated bị trống hoặc lỗi

        success, msg = run_ingestion(custom_db_dir=db_dir)
        assert success is False

    # 3. Kiểm tra collection cũ: Vẫn hoàn toàn nguyên vẹn với 5 tài liệu!
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["active_collection"] == "medical_knowledge_v1"

    recheck_col = client.get_collection("medical_knowledge_v1")
    assert recheck_col.count() == 5


def local_rag(tmp_path, enabled=False):
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.create_collection("medical_knowledge", embedding_function=None)
    collection.add(ids=["cough", "unrelated"], embeddings=[[0.0, 0.0], [2.0, 2.0]],
                   documents=["Cough guidance: cough can have different causes. Seek assessment for persistent symptoms.",
                              "Software programming python decorators and data classes."],
                   metadatas=[{"title": "Cough", "source": "NLM", "source_url": "https://medlineplus.gov/cough.html"},
                              {"title": "Software"}])
    return MedicalRAGService(db_dir=tmp_path, vector_search_enabled=enabled)


@pytest.mark.parametrize('query', ['đau đầu', 'Đau đầu', 'đau-đầu', 'đau đầu?', 'ĐAU ĐẦU', 'đau đầu', 'dau dau'])
def test_vietnamese_normalization_preserves_headache_expansion(tmp_path, query):
    rag = local_rag(tmp_path)
    assert search_tokens(query) == ['dau', 'dau']
    assert 'headache' in rag.expand_query(query)


def test_expansion_respects_explicit_vietnamese_diacritics(tmp_path):
    rag = local_rag(tmp_path)
    assert 'cough' not in rag.expand_query('Họ đang đi làm')
    assert 'headache' not in rag.expand_query('đau dầu')
    assert 'cough' in rag.expand_query('Tôi bị ho')
    assert 'headache' in rag.expand_query('Tôi bị dau dau')


def test_default_local_lookup_never_calls_embedding_query(tmp_path, monkeypatch):
    monkeypatch.delenv("RAG_VECTOR_SEARCH_ENABLED", raising=False)
    rag = local_rag(tmp_path)
    with patch.object(rag.collection, "query", side_effect=AssertionError("embedding path must not run")) as query:
        docs = rag.retrieve_context("Tôi bị ho", top_k=2)
    query.assert_not_called()
    assert [doc["title"] for doc in docs] == ["Cough"]
    assert docs[0]["retrieval"] == "bm25"
    assert docs[0]["distance"] is None
    assert docs[0]["distance_metric"] is None
    assert docs[0]["source_url"] == "https://medlineplus.gov/cough.html"


def test_optional_vector_failure_keeps_local_sources(tmp_path, caplog):
    rag = local_rag(tmp_path, enabled=True)
    with patch.object(rag.collection, "query", side_effect=RuntimeError("synthetic-private-query-value")) as query:
        docs = rag.retrieve_context("Cough", top_k=2)
    query.assert_called_once()
    assert len(docs) == 1
    assert docs[0]["source_url"] == "https://medlineplus.gov/cough.html"
    assert docs[0]["retrieval"] == "bm25"
    assert "synthetic-private-query-value" not in caplog.text


def test_optional_vector_does_not_invent_missing_distance_or_source(tmp_path):
    rag = local_rag(tmp_path, enabled=True)
    with patch.object(rag, "_bm25_matches", return_value=[]), patch.object(rag.collection, "query", return_value={
        "documents": [["no distance", "real vector match", "invalid distance"]],
        "metadatas": [[{}, {}, {}]], "distances": [[None, 0.2, float("nan")]],
    }):
        docs = rag.retrieve_context("test", top_k=2)
    assert len(docs) == 1
    assert docs[0]["content"] == "real vector match"
    assert docs[0]["distance"] == 0.2
    assert docs[0]["source_url"] == ""
    assert docs[0]["source"] == ""


def test_lexical_index_contains_source_corpus_not_user_query_cache(tmp_path):
    rag = local_rag(tmp_path)
    rag.retrieve_context("Cough synthetic-private-question", top_k=2)
    assert "synthetic-private-question" not in repr(rag._lexical_index)



def test_lexical_search_returns_ranked_metadata_without_vector(tmp_path):
    rag = local_rag(tmp_path)
    with patch.object(rag.collection, "query") as vector_query:
        hits = rag.lexical_search(rag.expand_query("ho"), 6)
    vector_query.assert_not_called()
    assert hits[0]["metadata"]["title"] == "Cough"
    assert hits[0]["rank"] == 1


def test_vector_search_filters_distances_and_respects_opt_in(tmp_path):
    rag = local_rag(tmp_path, enabled=True)
    data = {"documents": [["too far", "valid", "missing", "nan"]],
            "metadatas": [[{}, {"title": "Valid", "extra": "preserved"}, {}, {}]],
            "distances": [[1.36, 0.25, None, float("nan")]]}
    with patch.object(rag.collection, "query", return_value=data) as query:
        hits = rag.vector_search("query", 4)
        assert [(hit["content"], hit["rank"], hit["distance"]) for hit in hits] == [("valid", 2, 0.25)]
        assert hits[0]["metadata"]["extra"] == "preserved"
        rag.vector_search_enabled = False
        assert rag.vector_search("query", 4) == []
        query.assert_called_once()


def test_merge_results_deduplicates_and_preserves_branch_metadata():
    lexical = [{"content": "same", "rank": 1, "metadata": {"title": "Local", "source_url": "https://local", "extra": "L"}}]
    vector = [{"content": "same", "rank": 2, "metadata": {"title": "Vector", "source_url": "https://vector", "extra": "V"}, "distance": .4}]
    results = MedicalRAGService.merge_results(lexical, vector, 5)
    assert len(results) == 1
    result = results[0]
    assert result["retrieval"] == "hybrid"
    assert result["metadata"]["title"] == "Vector"
    assert result["lexical_metadata"]["extra"] == "L"
    assert result["vector_metadata"]["extra"] == "V"
    assert result["lexical_score"] == 1 / 61
    assert result["vector_score"] == 1 / 62
    assert result["fusion_score"] == pytest.approx(1 / 61 + 1 / 62)
    assert result["rerank_score"] is None


def test_candidates_support_twenty_but_context_keeps_legacy_contract(tmp_path):
    rag = local_rag(tmp_path, enabled=True)
    lexical = [{"content": f"doc {i}", "rank": i + 1, "metadata": {"title": str(i), "extra": i}} for i in range(20)]
    with patch.object(rag.collection, "count", return_value=100), \
         patch.object(rag, "lexical_search", return_value=lexical) as local, \
         patch.object(rag, "vector_search", return_value=[]) as vector:
        candidates = rag.retrieve_candidates("query", 20)
        assert len(candidates) == 20
        assert local.call_args.args[1] == 60
        assert vector.call_args.args[1] == 60
        context = rag.retrieve_context("query", 20)
    assert len(context) == 5
    assert set(context[0]) == {"content", "title", "category", "source", "source_url", "distance", "distance_metric", "accepted", "retrieval"}
    assert candidates[0]["metadata"]["extra"] == 0


def test_hybrid_candidates_preserve_missing_vector_metadata_without_changing_context(tmp_path):
    rag = local_rag(tmp_path, enabled=True)
    content = "Cough guidance: cough can have different causes. Seek assessment for persistent symptoms."
    result = {"documents": [[content]], "metadatas": [[{"title": "Vector title"}]], "distances": [[0.2]]}
    with patch.object(rag.collection, "query", return_value=result):
        candidates = rag.retrieve_candidates("Cough", 2)
        context = rag.retrieve_context("Cough", 2)
    assert candidates[0]["metadata"]["source_url"] == "https://medlineplus.gov/cough.html"
    assert candidates[0]["vector_metadata"] == {"title": "Vector title"}
    assert context[0]["title"] == "Vector title"
    assert context[0]["source_url"] == ""  # Original vector-overwrites-lexical behavior.
