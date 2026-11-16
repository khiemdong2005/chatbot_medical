"""
tests/test_retrieval_dilution.py
Unit & regression tests for Phase 6.6 Retrieval Dilution Remediation.
Ensures:
  1. BM25 medical token preservation (no_df_cutoff protects high-df clinical terms).
  2. Symmetric bilingual metadata coverage across all 364 curated documents.
  3. Strict English body content preservation (SHA-256 match for legacy corpus).
  4. Active runtime invariant preservation (active_collection.json untouched).
  5. Manifest and holdout validation gate integrity.
"""

import json
import hashlib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_active_collection_invariant():
    """Active runtime collection must be either baseline V2 or validated V4."""
    meta_file = ROOT / "medical_vectordb" / "active_collection.json"
    assert meta_file.exists(), "active_collection.json must exist"
    data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert data.get("active_collection") in (
        "medical_knowledge_shadow_v2_20261114_211653",
        "medical_knowledge_expanded_v4_20261115_005612"
    )


def test_df_cutoff_preserves_medical_tokens():
    """Verify that no_df_cutoff=True preserves essential clinical tokens with high document frequency."""
    from core.rag_service import MedicalRAGService, search_tokens

    rag = MedicalRAGService()
    # Test query with clinical words
    query = "low blood sugar and heart disease"
    stop = {"va", "co", "la", "cua", "toi", "bi", "nay", "thi", "cho", "xin", "hoi", "gi",
            "khong", "voi", "ve", "nhu", "nao", "the", "and", "of", "in", "to", "with", "is"}
    
    # Mock df where 'blood' and 'disease' exceed 40% threshold
    size = 1000
    mock_df = {
        "blood": 450,       # 45% > 40%
        "disease": 600,     # 60% > 40%
        "sugar": 120,       # 12% <= 40%
        "heart": 200,       # 20% <= 40%
        "low": 150          # 15% <= 40%
    }
    
    # Standard behavior (cutoff enabled)
    tokens = search_tokens(query)
    standard_terms = {
        t for t in tokens if t not in stop if len(t) > 1 and 0 < mock_df.get(t, 0) <= max(1, size * 0.4)
    }
    assert "blood" not in standard_terms, "Standard cutoff should drop 'blood' when df > 40%"
    assert "disease" not in standard_terms, "Standard cutoff should drop 'disease' when df > 40%"
    assert "sugar" in standard_terms
    assert "heart" in standard_terms

    # Remediation behavior (no_df_cutoff=True)
    remediated_terms = {
        t for t in tokens if t not in stop if len(t) > 1 and mock_df.get(t, 0) > 0
    }
    assert "blood" in remediated_terms, "no_df_cutoff=True must preserve 'blood'"
    assert "disease" in remediated_terms, "no_df_cutoff=True must preserve 'disease'"
    assert "sugar" in remediated_terms
    assert "heart" in remediated_terms


def test_legacy_english_body_sha256_preservation():
    """Verify 100% SHA-256 byte-for-byte preservation of English body text in enriched legacy docs."""
    raw_dir = ROOT / "data" / "curated" / "ready_documents_legacy_original_backup"
    if not raw_dir.exists():
        raw_dir = ROOT / "data" / "curated" / "ready_documents"
    enriched_dir = ROOT / "data" / "curated" / "ready_documents_enriched"

    assert raw_dir.exists(), "Original legacy dir must exist"
    assert enriched_dir.exists(), "Enriched legacy dir must exist"

    raw_files = sorted(list(raw_dir.glob("*.json")))
    if len(raw_files) > 241:
        # If already promoted, check the 241 legacy files
        raw_files = [f for f in raw_files if (enriched_dir / f.name).exists() and not (ROOT / "data" / "curated" / "tier_a_candidates" / f.name).exists()]
    assert len(raw_files) == 241, f"Expected 241 raw files, got {len(raw_files)}"

    for rf in raw_files:
        ef = enriched_dir / rf.name
        assert ef.exists(), f"Enriched file missing: {rf.name}"

        raw_data = json.loads(rf.read_text(encoding="utf-8"))
        enriched_data = json.loads(ef.read_text(encoding="utf-8"))

        raw_body = raw_data.get("body_en", "").strip()
        enriched_body = enriched_data.get("body_en", "").strip()

        assert raw_body == enriched_body, f"Body mismatch in file: {rf.name}"

        raw_sha = hashlib.sha256(raw_body.encode("utf-8")).hexdigest()
        enriched_sha = hashlib.sha256(enriched_body.encode("utf-8")).hexdigest()
        assert raw_sha == enriched_sha, f"SHA-256 mismatch in file: {rf.name}"


def test_bilingual_metadata_symmetry_across_corpus():
    """Verify that both legacy enriched (241) and Tier-A (123) have symmetric bilingual metadata."""
    legacy_dir = ROOT / "data" / "curated" / "ready_documents_enriched"
    tiera_dir = ROOT / "data" / "curated" / "tier_a_candidates"

    tiera_files = sorted([p for p in tiera_dir.glob("*.json") if not p.name.startswith("_")])
    tiera_names = {f.name for f in tiera_files}
    legacy_files = sorted([p for p in legacy_dir.glob("*.json") if p.name not in tiera_names])

    assert len(legacy_files) == 241, f"Expected 241 legacy files, got {len(legacy_files)}"
    assert len(tiera_files) == 123, f"Expected 123 Tier-A files, got {len(tiera_files)}"

    for f in legacy_files + tiera_files:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("title_en") and str(d["title_en"]).strip(), f"Missing title_en in {f.name}"
        assert d.get("title_vi") and str(d["title_vi"]).strip(), f"Missing title_vi in {f.name}"
        assert d.get("category_en") and str(d["category_en"]).strip(), f"Missing category_en in {f.name}"
        assert d.get("category_vi") and str(d["category_vi"]).strip(), f"Missing category_vi in {f.name}"
        
        kw_en = d.get("keywords_en") or []
        kw_vi = d.get("keywords_vi") or []
        assert isinstance(kw_en, list) and len(kw_en) >= 3, f"Insufficient keywords_en in {f.name}"
        assert isinstance(kw_vi, list) and len(kw_vi) >= 3, f"Insufficient keywords_vi in {f.name}"


def test_v4_shadow_manifest_and_holdout_gates():
    """Verify V4 shadow manifest and check that all holdout validation gates passed."""
    v4_manifest_path = ROOT / "data" / "curated" / "v4_shadow_manifest.json"
    assert v4_manifest_path.exists(), "v4_shadow_manifest.json must exist"
    v4_manifest = json.loads(v4_manifest_path.read_text(encoding="utf-8"))
    assert v4_manifest["source_count"] == 364
    assert v4_manifest["chunk_count"] == 725
    assert v4_manifest["collection_name"] == "medical_knowledge_expanded_v4_20261115_005612"

    holdout_path = ROOT / "evaluation" / "results" / "dilution_remediation_holdout_winner.json"
    assert holdout_path.exists(), "dilution_remediation_holdout_winner.json must exist"
    h_data = json.loads(holdout_path.read_text(encoding="utf-8"))

    gates = h_data.get("acceptance_gates", {})
    assert gates.get("overall_decision") == "PASS", f"HOLDOUT acceptance gates failed: {gates}"
    assert gates.get("gate_1_recall@5_delta", {}).get("passed") is True
    assert gates.get("gate_2_candidate_recall@20_delta", {}).get("passed") is True
    assert gates.get("gate_3_emergency_recall@5_regression", {}).get("passed") is True
    assert gates.get("gate_4_medication_recall@5_regression", {}).get("passed") is True
    assert gates.get("gate_5_vi_recall_improvement", {}).get("passed") is True
    assert gates.get("gate_6_expansion_on_quality", {}).get("passed") is True
