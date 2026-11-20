"""
Phase 4 regression tests:
- RAG curated-disk BM25 fallback while keeping /ready & vector is_available() honest
- Query expansion & Interpretation OpenRouter model resolution (no stale Gemini slugs)
- _OpenRouterModels max_tokens preservation (< 2048)
- Chat Vision model routing when image_bytes present
- Nutrition AI isolated 'nutrition' circuit breaker (vs gemini_circuit_breaker)
- Text PDF pipeline preserves pypdf text, avoids binary image_url uploads, redacts text PII
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.circuit_breaker import (
    gemini_circuit_breaker,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)
from core.gemini_service import GeminiMedicalService
from core.interpretation_service import generate_clinical_interpretation
from core.llm_provider import _OpenRouterModels
from core.nutrition_ai import NutritionAIError, select_recipes
from core.pipeline_orchestrator import process_medical_document_pipeline
from core.query_expansion_service import GeminiQueryExpansionProvider
from core.rag_service import MedicalRAGService


def test_rag_bm25_disk_fallback_works_while_is_available_stays_honest(tmp_path):
    # Isolated custom tmp_path with no DB -> must NOT leak default curated corpus
    isolated = MedicalRAGService(db_dir=tmp_path)
    assert isolated.is_available() is False
    assert isolated.lexical_available() is False
    assert isolated.retrieve_context("alcohol use disorder", top_k=2, lang="en") == []

    # Default directory has curated articles even if ChromaDB is unavailable on Py 3.15
    default_rag = MedicalRAGService()
    if default_rag.collection is None:
        assert default_rag.is_available() is False
        assert default_rag.lexical_available() is True
        hits = default_rag.retrieve_context("alcohol use disorder", top_k=2, lang="en")
        assert len(hits) >= 1
        assert any("medlineplus.gov" in (h.get("source_url") or "") for h in hits)
        assert hits[0]["retrieval"] == "bm25"


def test_query_expansion_and_interpretation_use_openrouter_models(monkeypatch):
    monkeypatch.setenv("OPENROUTER_EXPANSION_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    monkeypatch.setenv("OPENROUTER_INTERPRETATION_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    monkeypatch.delenv("RAG_QUERY_EXPANSION_MODEL", raising=False)

    exp_provider = GeminiQueryExpansionProvider(api_key="sk-or-v1-test-key-12345")
    assert not exp_provider.model.startswith("gemini-")
    assert exp_provider.model == "meta-llama/llama-3.1-8b-instruct:free"

    captured = {}

    def fake_generate_text(**kwargs):
        captured["candidate_models"] = kwargs.get("candidate_models")
        return "### 1. Tóm tắt nhanh\nOK"

    with patch("core.llm_provider.llm_provider.generate_text", side_effect=fake_generate_text):
        res = generate_clinical_interpretation(
            {"doc_type": "prescription", "medications": []},
            api_key="sk-or-v1-test-key-12345",
        )
    assert "Tóm tắt" in res["interpretation_md"]
    assert captured["candidate_models"]
    assert all(not m.startswith("gemini-") for m in captured["candidate_models"])


def test_openrouter_models_preserves_small_max_tokens():
    models = _OpenRouterModels(api_key="sk-or-v1-test-key-12345")
    captured = {}

    def fake_post(payload):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "chest pain"}}]}

    with patch.object(models, "_post_completion", side_effect=fake_post):
        resp = models.generate_content(
            model="openrouter/free",
            contents="đau ngực",
            config={"max_output_tokens": 60, "temperature": 0.0},
        )
    assert resp.text == "chest pain"
    assert captured["payload"]["max_tokens"] == 60
    assert captured["payload"]["temperature"] == 0.0


def test_chat_vision_routes_image_away_from_text_only_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    monkeypatch.setenv("OPENROUTER_OCR_MODEL", "nvidia/nemotron-3.5-super-vl:free")
    monkeypatch.delenv("OPENROUTER_VISION_MODEL", raising=False)

    svc = GeminiMedicalService(api_key="sk-or-v1-test-key-12345")
    calls = []

    def fake_gen(*, model, contents, config):
        calls.append({"model": model, "has_list": isinstance(contents, list)})
        return SimpleNamespace(text=json.dumps({"answer": "Đã xem thông tin."}))

    svc.client = SimpleNamespace(models=SimpleNamespace(generate_content=MagicMock(side_effect=fake_gen)))

    svc.generate_clinical_response("Tôi bị ho", [], image_bytes=None)
    svc.generate_clinical_response("Xem vết đỏ trên da", [], image_bytes=b"\xff\xd8\xff\xe0", image_mime_type="image/jpeg")

    assert calls[0]["model"] == "meta-llama/llama-3.1-8b-instruct:free"
    assert calls[0]["has_list"] is False
    assert calls[1]["model"] == "nvidia/nemotron-3.5-super-vl:free"
    assert calls[1]["has_list"] is True


def test_nutrition_ai_uses_nutrition_circuit_breaker(monkeypatch):
    reset_all_circuit_breakers()
    try:
        monkeypatch.setenv("OPENROUTER_NUTRITION_API_KEY", "sk-or-v1-test-key-12345")
        monkeypatch.setenv("OPENROUTER_NUTRITION_MODEL", "mistralai/mistral-7b-instruct:free")
        recipes = [{"id": "r1", "title": "Cháo gà", "ingredients": ["gạo", "thịt gà"], "steps": ["nấu"]}]
        fake_choice = {
            "needs_clarification": False,
            "clarification_question": "",
            "recommendations": [
                {
                    "recipe_id": "r1",
                    "display_title": "Cháo gà",
                    "reason": "Món mềm dễ tiêu hóa cho người mệt.",
                    "caution": "Tránh ăn quá nóng.",
                    "source_ids": [],
                }
            ],
        }

        # Tripping chat/gemini breaker must NOT block nutrition AI
        gemini_circuit_breaker.trip_for_test()
        with patch("core.llm_provider.llm_provider.generate_json", return_value=fake_choice):
            res = select_recipes("mệt mỏi", "food", recipes, [])
            assert res["recipes"][0]["id"] == "r1"

        # Tripping nutrition breaker MUST block nutrition AI
        get_circuit_breaker("nutrition").trip_for_test()
        with pytest.raises(NutritionAIError) as exc:
            select_recipes("mệt mỏi", "food", recipes, [])
        assert str(exc.value) == "unavailable"
    finally:
        reset_all_circuit_breakers()


def test_text_pdf_pipeline_preserves_extracted_text_and_redacts_pii(tmp_path):
    pdf_file = tmp_path / "rx.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n%fake-pdf")

    sample_pdf_text = (
        "PHONG KHAM DA KHOA ABC\n"
        "DON THUOC\n"
        "Ho ten: NGUYEN VAN A  SDT: 0912345678\n"
        "Chan doan: Viem hong cap\n"
        "1. Amoxicillin 500mg  Uong sang 1 vien, chieu 1 vien\n"
    )
    fake_page = SimpleNamespace(extract_text=lambda: sample_pdf_text, images=[])
    fake_reader = SimpleNamespace(pages=[fake_page])
    captured_text = {}

    def fake_text_ai(raw_text, doc_type="prescription", api_key=""):
        captured_text["text"] = raw_text
        captured_text["doc_type"] = doc_type
        return None  # Trigger deterministic local schema parser from PDF lines

    with (
        patch("pypdf.PdfReader", return_value=fake_reader),
        patch("core.pipeline_orchestrator.extract_ocr_parallel") as mock_img_ocr,
        patch("core.pipeline_orchestrator.extract_with_gemini_schema") as mock_img_ai,
        patch("core.pipeline_orchestrator.extract_with_gemini_text", side_effect=fake_text_ai),
    ):
        result = process_medical_document_pipeline(str(pdf_file), original_filename="rx.pdf", mask_pii=True)

    mock_img_ocr.assert_not_called()
    mock_img_ai.assert_not_called()
    assert result["status"] in ("review", "success")
    assert result["pii_protection"]["masked"] is True
    assert result["pii_protection"].get("method") == "text_redaction"
    assert "0912345678" not in captured_text["text"]
    assert "[REDACTED_PHONE]" in captured_text["text"]
    assert "Amoxicillin" in (result.get("raw_text") or json.dumps(result, ensure_ascii=False))
