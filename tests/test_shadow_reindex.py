"""
================================================================================
🧪 TEST SUITE: SHADOW REINDEX & SAFE ACTIVATION (PHASE 6.2)
================================================================================
Kiểm thử toàn diện quy trình kiểm thử và chuyển giao Shadow Collection:
  1. Tạo Shadow Collection độc lập và giữ nguyên active collection cũ trước khi duyệt.
  2. Xác thực tính toàn vẹn của metadata và provenance mô hình nhúng.
  3. Bao phủ 100% Ground-Truth URLs cho DEV và HOLDOUT test sets.
  4. Đồng bộ chính xác 1:1 giữa số lượng tài liệu ChromaDB và BM25 corpus.
  5. Cơ chế kích hoạt an toàn nguyên tử (Safe Atomic Pointer Switch via active_collection.json).
  6. Cơ chế rollback an toàn (Safe Rollback to old collection) bảo toàn dữ liệu cả 2 bản.
  7. Runtime smoke queries (VI, EN, Cấp cứu, Dược học) sau khi chuyển đổi.
================================================================================
"""

import os
import json
import pytest
from pathlib import Path

from core.document_chunker import (
    save_manifest_atomic,
    load_manifest,
    validate_manifest,
)
from core.settings import get_settings
from core.rag_service import MedicalRAGService, DEFAULT_COLLECTION_NAME

ROOT = Path(__file__).resolve().parent.parent
DEV_DATASET_PATH = ROOT / "evaluation" / "rag_dev_dataset.json"
HOLDOUT_DATASET_PATH = ROOT / "evaluation" / "rag_test_dataset.json"
SHADOW_COL_NAME = "medical_knowledge_shadow_v2_20261114_211653"

def _has_seeded_vectordb():
    p = ROOT / "medical_vectordb" / "chroma.sqlite3"
    return p.exists() and p.stat().st_size > 1_000_000


pytestmark = pytest.mark.skipif(
    not _has_seeded_vectordb(),
    reason="Requires local pre-built ChromaDB vector database (>1MB)"
)


class TestShadowCollectionIntegrity:
    """Kiểm tra sự tồn tại và tính hợp lệ của Shadow Collection."""

    def test_shadow_collection_exists_and_active_preserved(self):
        """Shadow Collection tồn tại với 408 chunks, và Active Collection cũ (414 chunks) được bảo toàn nguyên vẹn."""
        rag_old = MedicalRAGService(collection_name="medical_knowledge", vector_search_enabled=False)
        rag_shadow = MedicalRAGService(collection_name=SHADOW_COL_NAME, vector_search_enabled=False)

        assert rag_old.collection is not None
        assert rag_old.collection.count() == 414, f"Active collection cũ bị biến đổi: {rag_old.collection.count()}"

        assert rag_shadow.collection is not None
        assert rag_shadow.collection.count() == 408, f"Shadow collection count không đúng: {rag_shadow.collection.count()}"

    def test_shadow_collection_metadata_and_provenance(self):
        """Metadata của Shadow Collection lưu đầy đủ thông tin provenance và cấu hình chunking."""
        rag_shadow = MedicalRAGService(collection_name=SHADOW_COL_NAME, vector_search_enabled=False)
        meta = rag_shadow.collection.metadata

        assert meta["embedding_model"] == "all-MiniLM-L6-v2"
        assert meta["embedding_dimension"] == 384
        assert meta["chunking_version"] == "v2_sentence_contextual"
        assert meta["source_file_count"] == 241
        assert meta["chunk_count"] == 408
        assert meta["chunk_max_chars"] == 2000
        assert meta["chunk_overlap_chars"] == 200
        assert meta["chunk_min_chars"] == 200
        assert "created_at" in meta

    def test_bm25_chroma_alignment(self):
        """Số lượng tài liệu trong ChromaDB và số lượng tài liệu trong BM25 corpus khớp nhau 100%."""
        rag_shadow = MedicalRAGService(collection_name=SHADOW_COL_NAME, vector_search_enabled=False)
        # Kích hoạt BM25 index
        rag_shadow.lexical_search("sốt cao", 5)
        bm25_corpus_count = len(rag_shadow._lexical_index[1])
        chroma_count = rag_shadow.collection.count()

        assert bm25_corpus_count == chroma_count == 408

    def test_ground_truth_url_coverage(self):
        """Shadow Corpus phải bao phủ 100% Ground Truth URLs của cả DEV và HOLDOUT datasets."""
        rag_shadow = MedicalRAGService(collection_name=SHADOW_COL_NAME, vector_search_enabled=False)
        corpus = rag_shadow.collection.get(include=["metadatas"])
        shadow_urls = {m.get("source_url") for m in corpus["metadatas"] if m.get("source_url")}

        dev_cases = json.loads(DEV_DATASET_PATH.read_text(encoding="utf-8"))
        dev_gt = set()
        for c in dev_cases:
            dev_gt.update(c.get("relevant_documents", []))

        holdout_cases = json.loads(HOLDOUT_DATASET_PATH.read_text(encoding="utf-8"))
        holdout_gt = set()
        for c in holdout_cases:
            holdout_gt.update(c.get("relevant_documents", []))

        missing_dev = dev_gt - shadow_urls
        missing_holdout = holdout_gt - shadow_urls

        assert missing_dev == set(), f"Thiếu URLs trong DEV dataset: {missing_dev}"
        assert missing_holdout == set(), f"Thiếu URLs trong HOLDOUT dataset: {missing_holdout}"


class TestSafeActivationAndRollback:
    """Kiểm thử cơ chế chuyển con trỏ an toàn và khả năng Rollback tức thì."""

    def test_safe_activation_and_rollback_cycle(self, tmp_path):
        """Kiểm tra chu trình: Chuyển active pointer sang shadow -> Verify runtime -> Rollback về old -> Verify runtime."""
        # 1. Ban đầu chưa có manifest, RAG runtime trỏ về DEFAULT_COLLECTION_NAME
        rag_fresh = MedicalRAGService(db_dir=tmp_path, vector_search_enabled=False)
        assert rag_fresh.collection_name == DEFAULT_COLLECTION_NAME

        # 2. Thực hiện Safe Activation sang Shadow Collection
        st = get_settings()
        shadow_manifest = {
            "active_collection": SHADOW_COL_NAME,
            "created_at": "2026-11-14T21:16:53",
            "updated_at": "2026-11-14T21:16:53",
            "document_count": 408,
            "source_file_count": 241,
            "embedding_model": st.ingestion.embedding_model,
            "embedding_dimension": st.ingestion.embedding_dimension,
            "chunking_version": st.ingestion.chunking_version,
            "chunk_config": {
                "max_chars": st.ingestion.chunk_max_chars,
                "overlap_chars": st.ingestion.chunk_overlap_chars,
                "min_chunk_chars": st.ingestion.min_chunk_chars,
                "hard_max_chars": st.ingestion.hard_max_chars
            },
            "version": "20261114_211653"
        }
        manifest_path = tmp_path / "active_collection.json"
        save_manifest_atomic(shadow_manifest, manifest_path)

        # Runtime RAG mới phải nhận ngay Shadow Collection
        rag_activated = MedicalRAGService(db_dir=tmp_path, vector_search_enabled=False)
        assert rag_activated.collection_name == SHADOW_COL_NAME

        # 3. Thực hiện Rollback an toàn về collection cũ
        rollback_manifest = {
            "active_collection": "medical_knowledge",
            "created_at": "2026-11-14T21:30:00",
            "document_count": 414,
            "version": "rollback_v1"
        }
        save_manifest_atomic(rollback_manifest, manifest_path)

        # Runtime RAG mới nhận lại collection cũ
        rag_rolled_back = MedicalRAGService(db_dir=tmp_path, vector_search_enabled=False)
        assert rag_rolled_back.collection_name == "medical_knowledge"

        # 4. Tái khôi phục lại Shadow pointer
        save_manifest_atomic(shadow_manifest, manifest_path)
        rag_restored = MedicalRAGService(db_dir=tmp_path, vector_search_enabled=False)
        assert rag_restored.collection_name == SHADOW_COL_NAME


class TestRuntimeSmokeAfterActivation:
    """Smoke test các câu hỏi thực tế trên Shadow Collection."""

    def test_smoke_queries_resolve_meaningful_results(self):
        """Kiểm tra truy xuất thực tế trên Shadow Collection cho VI, EN, Cấp cứu và Dược học."""
        rag = MedicalRAGService(collection_name=SHADOW_COL_NAME, vector_search_enabled=False)

        smoke_cases = [
            ("VI Query", "Triệu chứng của sốt cao và đau đầu dữ dội là gì?"),
            ("EN Query", "What are the common symptoms of high fever?"),
            ("Emergency Query", "Đau ngực dữ dội kèm khó thở và vã mồ hôi"),
            ("Medication Query", "What kinds of infections do antibiotics treat?")
        ]

        for label, query in smoke_cases:
            candidates = rag.retrieve_candidates(query, top_k=5)
            assert len(candidates) > 0, f"Truy vấn {label} không trả về kết quả nào!"
            top_hit = candidates[0]
            assert "content" in top_hit
            assert "metadata" in top_hit
            assert top_hit["metadata"].get("source_url", "").startswith("http")
            assert top_hit["metadata"].get("title")
