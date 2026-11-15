"""
tests/test_v4_activation.py
Comprehensive verification test suite for Phase 6.7 V4 Collection Activation:
  1. Active manifest provenance & schema extension
  2. Fresh runtime initialization resolving V4 (725 chunks)
  3. 1:1 BM25 and ChromaDB alignment
  4. Atomic activation, rollback to V2, and restore to V4
  5. Canonical source strategy: 364 symmetric bilingual documents
  6. Rebuild reproducibility & deterministic chunk IDs matching V4
  7. Runtime smoke queries & frozen retrieval policy
  8. Feature flag defaults (expansion/vector/rerank remain False)
"""

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent

from core.settings import get_settings
from core.rag_service import MedicalRAGService
from core.document_chunker import save_manifest_atomic, load_manifest
from scripts.ingest import load_curated_medlineplus_documents

MANIFEST_PATH = ROOT / "medical_vectordb" / "active_collection.json"
READY_DIR = ROOT / "data" / "curated" / "ready_documents"
V2_NAME = "medical_knowledge_shadow_v2_20261114_211653"
V4_NAME = "medical_knowledge_expanded_v4_20261115_005612"


def test_v4_active_manifest_provenance():
    """Verify active manifest records complete provenance and frozen winner config."""
    assert MANIFEST_PATH.exists(), "active_collection.json must exist"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest.get("active_collection") == V4_NAME
    assert manifest.get("document_count") == 725
    assert manifest.get("chunk_count") == 725
    assert manifest.get("source_file_count") == 364
    assert manifest.get("embedding_model") == "all-MiniLM-L6-v2"
    assert manifest.get("embedding_dimension") == 384
    assert manifest.get("chunking_version") == "v2_sentence_contextual"
    assert manifest.get("bilingual_metadata_version") == "v2_symmetric_bilingual"
    assert manifest.get("bm25_df_policy") == "no_df_cutoff"

    frozen = manifest.get("frozen_config", {})
    assert frozen.get("no_df_cutoff") is True
    assert frozen.get("symmetric_bilingual_metadata") is True
    assert frozen.get("source_diversity") is False


def test_fresh_runtime_resolves_v4():
    """Verify fresh MedicalRAGService initializes against active V4 with 725 chunks."""
    rag = MedicalRAGService()
    assert rag.collection_name == V4_NAME
    assert rag.collection is not None
    assert rag.collection.count() == 725
    assert rag.no_df_cutoff is True


def test_bm25_chroma_alignment():
    """Verify BM25 corpus builds with exactly 725 documents aligning with Chroma."""
    rag = MedicalRAGService()
    rag.lexical_search("test query", limit=1)
    assert rag._lexical_index is not None
    key, rows, counts, df, lengths = rag._lexical_index
    assert key == (V4_NAME, 725)
    assert len(rows) == 725


def test_runtime_defaults_preserved():
    """Verify feature flags remain strictly disabled by default."""
    s = get_settings()
    assert s.rag.query_expansion_enabled is False
    assert s.rag.vector_search_enabled is False
    assert s.rag.rerank_enabled is False
    assert s.rag.bm25_no_df_cutoff is True


def test_canonical_source_bilingual_symmetry():
    """Verify all 364 documents in ready_documents have complete symmetric bilingual metadata."""
    files = sorted(list(READY_DIR.glob("*.json")))
    assert len(files) == 364, f"Expected 364 canonical documents, got {len(files)}"

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("title_en") and str(d["title_en"]).strip(), f"Missing title_en in {f.name}"
        assert d.get("title_vi") and str(d["title_vi"]).strip(), f"Missing title_vi in {f.name}"
        assert d.get("category_en") and str(d["category_en"]).strip(), f"Missing category_en in {f.name}"
        assert d.get("category_vi") and str(d["category_vi"]).strip(), f"Missing category_vi in {f.name}"

        kw_en = d.get("keywords_en") or []
        kw_vi = d.get("keywords_vi") or []
        assert isinstance(kw_en, list) and len(kw_en) >= 3, f"Insufficient keywords_en in {f.name}"
        assert isinstance(kw_vi, list) and len(kw_vi) >= 3, f"Insufficient keywords_vi in {f.name}"


def test_rebuild_dry_run_and_id_reproducibility():
    """Verify dry-run on canonical 364 sources produces exact 725 chunks matching V4 IDs."""
    raw_chunks = load_curated_medlineplus_documents(curated_dirs=[READY_DIR])
    assert len(raw_chunks) == 725, f"Expected 725 chunks, got {len(raw_chunks)}"

    rag = MedicalRAGService(collection_name=V4_NAME)
    v4_ids = set(rag.collection.get()["ids"])
    dry_run_ids = set(c["id"] for c in raw_chunks)

    diff = v4_ids.symmetric_difference(dry_run_ids)
    assert len(diff) == 0, f"Chunk ID discrepancy: {len(diff)} IDs differ"


def test_atomic_rollback_and_restore_cycle():
    """Verify atomic pointer rollback to V2 and safe restoration to V4."""
    orig_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    v2_manifest = {
        "active_collection": V2_NAME,
        "document_count": 408,
        "source_file_count": 241,
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "chunking_version": "v2_sentence_contextual"
    }

    try:
        # 1. Rollback to V2
        save_manifest_atomic(v2_manifest, MANIFEST_PATH)
        rag_v2 = MedicalRAGService()
        assert rag_v2.collection_name == V2_NAME
        assert rag_v2.collection.count() == 408

        # 2. Restore to V4
        save_manifest_atomic(orig_manifest, MANIFEST_PATH)
        rag_v4 = MedicalRAGService()
        assert rag_v4.collection_name == V4_NAME
        assert rag_v4.collection.count() == 725
    finally:
        save_manifest_atomic(orig_manifest, MANIFEST_PATH)


def test_representative_smoke_queries():
    """Verify representative clinical queries retrieve expected targets in Top-5 on V4."""
    rag = MedicalRAGService()
    queries = [
        ("Vì sao cần đo huyết áp để phát hiện huyết áp cao?", "https://medlineplus.gov/highbloodpressure.html"),
        ("Dấu hiệu của đột quỵ là gì?", "https://medlineplus.gov/stroke.html"),
        ("What are symptoms of low blood sugar?", "https://medlineplus.gov/hypoglycemia.html"),
        ("Why should antibiotics not be used for viral infections?", "https://medlineplus.gov/antibiotics.html"),
        ("What food groups are part of a balanced eating pattern?", "https://medlineplus.gov/nutrition.html")
    ]

    for q, target in queries:
        hits = rag.retrieve_candidates(q, top_k=5)
        top5_urls = [h.get("metadata", {}).get("source_url", "").rstrip("/") for h in hits]
        assert target.rstrip("/") in top5_urls, f"Target {target} not found in top 5 for '{q}'"
