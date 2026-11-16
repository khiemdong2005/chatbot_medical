"""
Tests for Phase 6.5: Expanded Corpus Verification & Activation Gate.
Validates shadow collection integrity, safety metadata, ground truth coverage,
active pointer invariant, atomic activation & rollback cycle, and smoke queries.
"""

import json
from pathlib import Path
import pytest

from core.rag_service import MedicalRAGService
from core.document_chunker import save_manifest_atomic

ROOT = Path(__file__).resolve().parent.parent
READY_DIR = ROOT / "data" / "curated" / "ready_documents"
TIER_A_DIR = ROOT / "data" / "curated" / "tier_a_candidates"
ACTIVE_CONFIG = ROOT / "medical_vectordb" / "active_collection.json"
DEV_DATASET_PATH = ROOT / "evaluation" / "rag_dev_dataset.json"
HOLDOUT_DATASET_PATH = ROOT / "evaluation" / "rag_test_dataset.json"

SHADOW_COLLECTION = "medical_knowledge_expanded_v3_20261115_000308"
ACTIVE_V2_COLLECTION = "medical_knowledge_shadow_v2_20261114_211653"

def _has_seeded_vectordb():
    p = ROOT / "medical_vectordb" / "chroma.sqlite3"
    return p.exists() and p.stat().st_size > 1_000_000


requires_chromadb = pytest.mark.skipif(
    not _has_seeded_vectordb(),
    reason="Requires local pre-built ChromaDB vector database (>1MB)"
)


def test_merged_source_counts():
    """Verify source files in ready_documents and tier_a_candidates equal 364 total."""
    ready_files = list(READY_DIR.glob("*.json"))
    tier_a_files = [f for f in TIER_A_DIR.glob("*.json") if not f.name.startswith("_")]

    assert len(ready_files) in (241, 364), f"Expected 241 or 364 ready documents, got {len(ready_files)}"
    assert len(tier_a_files) == 123, f"Expected 123 Tier-A documents, got {len(tier_a_files)}"
    if len(ready_files) == 241:
        assert len(ready_files) + len(tier_a_files) == 364
    else:
        assert len(ready_files) == 364


@requires_chromadb
def test_shadow_collection_integrity():
    """Verify expanded v3 collection chunk count, length boundaries, and provenance."""
    rag = MedicalRAGService(collection_name=SHADOW_COLLECTION)
    assert rag.collection is not None, "Shadow collection must be accessible"
    assert rag.collection.count() == 687, f"Expected 687 chunks, got {rag.collection.count()}"

    corpus = rag.collection.get(include=["documents", "metadatas"])
    documents = corpus.get("documents") or []
    metadatas = corpus.get("metadatas") or []

    assert len(documents) == 687
    for doc, meta in zip(documents, metadatas):
        assert len(doc) >= 200, f"Tiny chunk detected: {len(doc)} chars in {meta.get('chunk_id')}"
        assert meta.get("chunking_version") == "v2_sentence_contextual"
        assert meta.get("source_url") and meta["source_url"].startswith("https://medlineplus.gov/")
        assert meta.get("document_id")
        assert meta.get("chunk_id")
        assert meta.get("content_sha256")
        assert not doc.startswith(" ")


@requires_chromadb
def test_safety_flag_preservation():
    """Verify all 4 approved-with-flag documents retain their safety flags in the collection."""
    rag = MedicalRAGService(collection_name=SHADOW_COLLECTION)
    flagged = rag.collection.get(
        where={"qa_status": "APPROVED_WITH_SAFETY_FLAG"},
        include=["metadatas"]
    )
    metadatas = flagged.get("metadatas") or []
    assert len(metadatas) == 10, f"Expected 10 flagged chunks, got {len(metadatas)}"

    flagged_urls = {m.get("source_url") for m in metadatas}
    expected_urls = {
        "https://medlineplus.gov/howtolowercholesterolwithdiet.html",
        "https://medlineplus.gov/overthecountermedicines.html",
        "https://medlineplus.gov/chlamydiainfections.html",
        "https://medlineplus.gov/tetanusdiphtheriaandpertussisvaccines.html",
    }
    assert flagged_urls == expected_urls, f"Expected {expected_urls}, got {flagged_urls}"


@requires_chromadb
def test_ground_truth_url_coverage():
    """Verify 100% of ground-truth URLs in DEV and HOLDOUT exist in the expanded shadow collection."""
    rag = MedicalRAGService(collection_name=SHADOW_COLLECTION)
    corpus = rag.collection.get(include=["metadatas"])
    indexed_urls = {m.get("source_url").rstrip("/") for m in corpus["metadatas"] if m.get("source_url")}

    dev_cases = json.loads(DEV_DATASET_PATH.read_text(encoding="utf-8"))
    holdout_cases = json.loads(HOLDOUT_DATASET_PATH.read_text(encoding="utf-8"))

    dev_missing = [u for c in dev_cases for u in c["relevant_documents"] if u.rstrip("/") not in indexed_urls]
    holdout_missing = [u for c in holdout_cases for u in c["relevant_documents"] if u.rstrip("/") not in indexed_urls]

    assert len(dev_missing) == 0, f"Missing DEV ground truth URLs: {dev_missing}"
    assert len(holdout_missing) == 0, f"Missing HOLDOUT ground truth URLs: {holdout_missing}"


@requires_chromadb
def test_active_pointer_invariant():
    """Verify active_collection.json maintains a verified active collection."""
    assert ACTIVE_CONFIG.exists(), "active_collection.json must exist"
    data = json.loads(ACTIVE_CONFIG.read_text(encoding="utf-8"))
    assert data["active_collection"] in (ACTIVE_V2_COLLECTION, "medical_knowledge_expanded_v4_20261115_005612")
    assert data["document_count"] in (408, 725)

    rag = MedicalRAGService()
    assert rag.collection_name in (ACTIVE_V2_COLLECTION, "medical_knowledge_expanded_v4_20261115_005612")
    assert rag.collection.count() in (408, 725)


@requires_chromadb
def test_safe_activation_and_rollback_cycle():
    """Verify atomic activation of shadow collection and instant rollback restore."""
    orig_content = ACTIVE_CONFIG.read_text(encoding="utf-8")
    orig_data = json.loads(orig_content)

    temp_data = dict(orig_data)
    temp_data["active_collection"] = SHADOW_COLLECTION
    temp_data["document_count"] = 687
    temp_data["source_file_count"] = 364

    try:
        # 1. Switch to shadow
        save_manifest_atomic(temp_data, ACTIVE_CONFIG)
        rag_shadow = MedicalRAGService()
        assert rag_shadow.collection_name == SHADOW_COLLECTION
        assert rag_shadow.collection.count() == 687

        # 2. Rollback to original
        save_manifest_atomic(orig_data, ACTIVE_CONFIG)
        rag_restored = MedicalRAGService()
        assert rag_restored.collection_name == orig_data["active_collection"]
        assert rag_restored.collection.count() == orig_data["document_count"]
    finally:
        # Guarantee restore
        save_manifest_atomic(orig_data, ACTIVE_CONFIG)


@requires_chromadb
def test_smoke_queries_on_expanded_collection():
    """Verify 5 representative queries return valid results on expanded collection."""
    rag = MedicalRAGService(collection_name=SHADOW_COLLECTION)
    queries = [
        "tôi bị đau đầu và chóng mặt",
        "symptoms of type 2 diabetes",
        "đau ngực dữ dội lan ra sau lưng khó thở",
        "liều dùng paracetamol",
        "làm sao để phòng ngừa bệnh tim mạch",
    ]
    for q in queries:
        hits = rag.retrieve_context(q, top_k=2)
        assert len(hits) > 0, f"No hits for query: {q}"
        for h in hits:
            assert h.get("content") and len(h["content"]) > 0
            assert h.get("source_url") and h["source_url"].startswith("https://medlineplus.gov/")


@requires_chromadb
def test_privacy_and_phi_absence():
    """Verify no PHI or patient identifier in collection chunk metadatas."""
    rag = MedicalRAGService(collection_name=SHADOW_COLLECTION)
    corpus = rag.collection.get(include=["metadatas"])
    for meta in corpus["metadatas"]:
        assert "patient_id" not in meta
        assert "ssn" not in meta
        assert "mrn" not in meta
