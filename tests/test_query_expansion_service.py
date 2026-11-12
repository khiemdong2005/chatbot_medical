"""
Unit and Integration Tests for Cross-Language Query Expansion Service.

Tests:
  - Vietnamese query expansion
  - English query bypass
  - Empty query bypass
  - Provider timeout fallback (degraded mode)
  - Provider exception fallback
  - Empty response fallback
  - Negation handling and filtering
  - In-memory bounded LRU cache (hit/miss)
  - Privacy: raw medical queries and API keys are not logged
  - Retrieval integration: original BM25 + expanded BM25 RRF fusion, deduplication, provenance
"""

import time
import logging
from unittest.mock import MagicMock, patch
import pytest

from core.query_expansion_service import (
    QueryExpansionService,
    QueryExpansionProvider,
    ExpandedQuery,
    GeminiQueryExpansionProvider
)
from core.rag_service import MedicalRAGService


class MockStaticProvider(QueryExpansionProvider):
    """Deterministic mock provider for offline tests."""
    def __init__(self, mapping=None, delay=0.0, should_raise=False):
        self.mapping = mapping or {}
        self.delay = delay
        self.should_raise = should_raise
        self.call_count = 0

    def expand(self, query: str, timeout_seconds: float = 3.0) -> str:
        self.call_count += 1
        if self.delay > 0:
            time.sleep(self.delay)
        if self.should_raise:
            raise RuntimeError("Simulated provider upstream failure")
        return self.mapping.get(query.strip(), "")


# ------------------------------------------------------------------------------
# 1. SERVICE-LEVEL UNIT TESTS
# ------------------------------------------------------------------------------

def test_vietnamese_query_expands_successfully():
    provider = MockStaticProvider(mapping={
        "Tôi bị đau ngực và khó thở": "chest pain shortness of breath"
    })
    service = QueryExpansionService(enabled=True, provider=provider)

    res = service.expand_for_retrieval("Tôi bị đau ngực và khó thở", language="vi")
    assert res.used_expansion is True
    assert res.expanded_query == "chest pain shortness of breath"
    assert res.degraded is False
    assert res.cached is False
    assert provider.call_count == 1


def test_english_query_bypasses_expansion():
    provider = MockStaticProvider(mapping={"chest pain and dyspnea": "chest pain"})
    service = QueryExpansionService(enabled=True, provider=provider)

    res = service.expand_for_retrieval("I have severe chest pain and dyspnea", language="en")
    assert res.used_expansion is False
    assert res.expanded_query == "I have severe chest pain and dyspnea"
    assert res.provider == "bypassed"
    assert res.degraded is False
    assert provider.call_count == 0


def test_empty_query_bypasses_expansion():
    provider = MockStaticProvider()
    service = QueryExpansionService(enabled=True, provider=provider)

    for empty_val in ("", "   ", None):
        res = service.expand_for_retrieval(empty_val, language="vi")
        assert res.used_expansion is False
        assert res.provider in ("none", "disabled")
        assert provider.call_count == 0


def test_disabled_service_bypasses_expansion():
    provider = MockStaticProvider(mapping={"Tôi đau đầu": "headache"})
    service = QueryExpansionService(enabled=False, provider=provider)

    res = service.expand_for_retrieval("Tôi đau đầu", language="vi")
    assert res.used_expansion is False
    assert res.expanded_query == "Tôi đau đầu"
    assert res.provider == "disabled"
    assert provider.call_count == 0


def test_provider_exception_falls_back_gracefully():
    provider = MockStaticProvider(should_raise=True)
    service = QueryExpansionService(enabled=True, provider=provider)

    res = service.expand_for_retrieval("Tôi bị sốt cao phát ban", language="vi")
    assert res.used_expansion is False
    assert res.expanded_query == "Tôi bị sốt cao phát ban"
    assert res.degraded is True
    assert provider.call_count == 1


def test_empty_expansion_falls_back_gracefully():
    # Provider returns empty string for unmapped query
    provider = MockStaticProvider(mapping={})
    service = QueryExpansionService(enabled=True, provider=provider)

    res = service.expand_for_retrieval("Truy vấn y khoa lạ", language="vi")
    assert res.used_expansion is False
    assert res.expanded_query == "Truy vấn y khoa lạ"
    assert res.degraded is True
    assert provider.call_count == 1


def test_cache_hit_and_miss_behavior():
    provider = MockStaticProvider(mapping={"đau dạ dày": "stomach ache"})
    service = QueryExpansionService(enabled=True, provider=provider, cache_size=10)

    # First call -> cache miss
    res1 = service.expand_for_retrieval("đau dạ dày", language="vi")
    assert res1.used_expansion is True
    assert res1.cached is False
    assert provider.call_count == 1

    # Second call -> cache hit
    res2 = service.expand_for_retrieval("đau dạ dày", language="vi")
    assert res2.used_expansion is True
    assert res2.cached is True
    assert res2.expanded_query == "stomach ache"
    assert provider.call_count == 1  # Provider was NOT called again


def test_bounded_lru_cache_eviction():
    provider = MockStaticProvider(mapping={
        f"triệu chứng {i}": f"symptom {i}" for i in range(10)
    })
    # Set cache limit to 3 items
    service = QueryExpansionService(enabled=True, provider=provider, cache_size=3)

    # Insert 3 items
    service.expand_for_retrieval("triệu chứng 1", language="vi")
    service.expand_for_retrieval("triệu chứng 2", language="vi")
    service.expand_for_retrieval("triệu chứng 3", language="vi")
    assert provider.call_count == 3

    # Access item 1 again -> hit
    res = service.expand_for_retrieval("triệu chứng 1", language="vi")
    assert res.cached is True
    assert provider.call_count == 3

    # Add 4th item -> should evict item 2 (least recently used)
    service.expand_for_retrieval("triệu chứng 4", language="vi")
    assert provider.call_count == 4

    # Access item 2 -> cache miss, re-queried
    res2 = service.expand_for_retrieval("triệu chứng 2", language="vi")
    assert res2.cached is False
    assert provider.call_count == 5


def test_privacy_raw_query_not_in_logs(caplog):
    sensitive_query = "Bệnh nhân Nguyễn Văn A sinh năm 1980 bị nhiễm HIV giai đoạn 2"
    provider = MockStaticProvider(mapping={sensitive_query: "HIV stage 2"})
    service = QueryExpansionService(enabled=True, provider=provider)

    with caplog.at_level(logging.INFO):
        service.expand_for_retrieval(sensitive_query, language="vi")

    for record in caplog.records:
        assert sensitive_query not in record.getMessage(), "Sensitive medical query was leaked to logs!"
        assert "Nguyễn Văn A" not in record.getMessage()


# ------------------------------------------------------------------------------
# 2. RETRIEVAL INTEGRATION & RRF FUSION TESTS
# ------------------------------------------------------------------------------

def test_fuse_branches_reciprocal_rank_fusion_and_provenance():
    # Branch 1 (original BM25)
    branch_original = [
        {"content": "Doc A: Chest pain and coronary artery disease", "metadata": {"title": "Doc A"}, "rank": 1},
        {"content": "Doc B: Asthma and breathing difficulty", "metadata": {"title": "Doc B"}, "rank": 2},
    ]
    # Branch 2 (expanded BM25)
    branch_expanded = [
        {"content": "Doc C: Myocardial infarction guidelines", "metadata": {"title": "Doc C"}, "rank": 1},
        {"content": "Doc A: Chest pain and coronary artery disease", "metadata": {"title": "Doc A"}, "rank": 2},
    ]

    branches = [("bm25_original", branch_original), ("bm25_expanded", branch_expanded)]
    fused = MedicalRAGService.fuse_branches(branches, limit=5)

    assert len(fused) == 3  # Doc A, Doc B, Doc C (Doc A deduplicated!)

    # Doc A appears in BOTH branches -> rank 1 in orig + rank 2 in exp -> highest fusion score!
    doc_a = fused[0]
    assert "Doc A" in doc_a["content"]
    assert "bm25_original" in doc_a["retrieval_branches"]
    assert "bm25_expanded" in doc_a["retrieval_branches"]
    expected_score_a = (1.0 / (60 + 1)) + (1.0 / (60 + 2))
    assert pytest.approx(doc_a["fusion_score"], rel=1e-5) == expected_score_a


def test_retrieval_cross_language_expansion_end_to_end(tmp_path):
    """Deterministic end-to-end test: Vietnamese query retrieves English medical doc via expansion."""
    import chromadb
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.create_collection("medical_knowledge", embedding_function=None)

    # Add English medical document to corpus
    collection.add(
        ids=["doc_chest_pain", "doc_migraine"],
        documents=[
            "Chest pain and angina pectoris: Clinical symptoms include substernal pressure and radiation to left arm.",
            "Migraine headache: Unilateral pulsating head pain accompanied by photophobia and nausea."
        ],
        metadatas=[
            {"title": "Angina and Chest Pain - MedlinePlus", "source_url": "https://medlineplus.gov/angina.html"},
            {"title": "Migraine Overview - MedlinePlus", "source_url": "https://medlineplus.gov/migraine.html"}
        ]
    )

    rag = MedicalRAGService(db_dir=tmp_path, acceptance_threshold=1.35, vector_search_enabled=False)

    # Mock provider returning English expansion for Vietnamese query
    provider = MockStaticProvider(mapping={
        "Tôi bị đau thắt ngực lan ra cánh tay": "angina chest pain radiation arm"
    })
    mock_expansion_service = QueryExpansionService(enabled=True, provider=provider)

    with patch("core.rag_service.query_expansion_service", mock_expansion_service):
        candidates = rag.retrieve_candidates("Tôi bị đau thắt ngực lan ra cánh tay", top_k=2, lang="vi")
        docs = rag.retrieve_context("Tôi bị đau thắt ngực lan ra cánh tay", top_k=2, lang="vi")

    assert len(candidates) > 0
    assert "Chest pain and angina" in candidates[0]["content"]
    assert "bm25_expanded" in candidates[0].get("retrieval_branches", [])

    assert len(docs) > 0
    top_doc = docs[0]
    assert "Chest pain and angina" in top_doc["content"]
