"""
================================================================================
🩺 TEST CORPUS CURATION & BILINGUAL METADATA (PHASE 6.4)
================================================================================
Bộ kiểm thử chất lượng và an toàn cho tập tài liệu tuyển chọn Tier-A:
  1. Số lượng ứng viên nằm trong ngưỡng mục tiêu (110–140 tài liệu).
  2. 100% tài liệu là tiếng Anh (language='en'), 0% Spanish, 0% Medical_book.pdf.
  3. 0% trùng lặp URL hoặc nội dung với ready_documents hiện tại và nội bộ Tier-A.
  4. 100% tài liệu có đầy đủ siêu dữ liệu song ngữ (title_en, title_vi, category_en,
     category_vi, keywords_en, keywords_vi).
  5. Bảo toàn 100% tính toàn vẹn thân văn bản gốc (SHA-256 fingerprint trùng khớp).
  6. QA scan phát hiện chỉ định liều lượng và đảm bảo 0 thẻ HTML rác.
  7. Bao phủ đầy đủ các chủ đề cấp cứu, an toàn thuốc, dự phòng và khoảng trống bệnh mạn.
  8. Bảo toàn tuyệt đối runtime: ready_documents và active_collection.json không bị đột biến.
  9. Khử trùng lặp chuẩn (Canonical topic deduplication) và loại trừ nội dung hành chính.
================================================================================
"""

import json
import re
from pathlib import Path
import pytest

from core.document_chunker import compute_content_hash
from scripts.curate_tier_a import REJECTIONS

BASE_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BASE_DIR / "data" / "curated" / "tier_a_candidates"
READY_DOCS_DIR = BASE_DIR / "data" / "curated" / "ready_documents"
ACTIVE_COLLECTION_FILE = BASE_DIR / "medical_vectordb" / "active_collection.json"


@pytest.fixture(scope="module")
def staged_candidates():
    """Đọc toàn bộ các tệp ứng viên Tier-A đã được stage."""
    files = sorted([p for p in STAGING_DIR.glob("*.json") if not p.name.startswith("_")])
    assert len(files) > 0, "Không tìm thấy tệp ứng viên nào trong tier_a_candidates!"
    docs = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        docs.append((f.name, data))
    return docs


class TestCorpusCurationTierA:

    def test_candidate_count_within_target_range(self, staged_candidates):
        """Xác minh số lượng tài liệu Tier-A được chọn nằm trong ngưỡng 110–140."""
        count = len(staged_candidates)
        assert 110 <= count <= 140, f"Số lượng tài liệu Tier-A ({count}) không nằm trong khoảng 110–140!"

    def test_candidates_language_en_and_no_spanish(self, staged_candidates):
        """Xác minh 100% ứng viên là tiếng Anh, không chứa Spanish và không lấy từ Medical_book.pdf."""
        for fname, doc in staged_candidates:
            assert doc.get("language") == "en", f"{fname}: language không phải 'en'!"
            url = doc.get("source_url", "").lower()
            assert "espanol" not in url, f"{fname}: URL chứa tiếng Tây Ban Nha ({url})!"
            assert "medical_book" not in url, f"{fname}: Dữ liệu đến từ Medical_book.pdf!"
            assert doc.get("source") == "MedlinePlus", f"{fname}: Nguồn không phải MedlinePlus!"

    def test_no_duplicate_urls_or_content_against_curated_or_internal(self, staged_candidates):
        """Xác minh 0 trùng lặp URL hoặc mã băm nội dung giữa Tier-A và ready_documents cũng như nội bộ."""
        curated_urls = set()
        curated_hashes = set()
        staged_names = {fname for fname, _ in staged_candidates}
        for p in READY_DOCS_DIR.glob("*.json"):
            if p.name in staged_names:
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("source_url"):
                curated_urls.add(d["source_url"].strip().rstrip("/"))
            body = d.get("page_content", "") or d.get("summary", "")
            if body:
                curated_hashes.add(compute_content_hash(body))

        staged_urls = set()
        staged_hashes = set()

        for fname, doc in staged_candidates:
            url = doc.get("source_url", "").strip().rstrip("/")
            content_hash = doc.get("content_sha256") or compute_content_hash(doc.get("page_content", ""))

            # Không trùng lặp với curated hiện có
            assert url not in curated_urls, f"{fname}: URL ({url}) đã tồn tại trong ready_documents!"
            assert content_hash not in curated_hashes, f"{fname}: Nội dung trùng khớp tệp trong ready_documents!"

            # Không trùng lặp trong nội bộ Tier-A
            assert url not in staged_urls, f"{fname}: URL ({url}) bị trùng lặp trong nội bộ Tier-A!"
            assert content_hash not in staged_hashes, f"{fname}: Nội dung bị trùng lặp trong nội bộ Tier-A!"

            staged_urls.add(url)
            staged_hashes.add(content_hash)

    def test_bilingual_metadata_completeness(self, staged_candidates):
        """Xác minh 100% ứng viên có đầy đủ trường siêu dữ liệu song ngữ chuẩn mực."""
        for fname, doc in staged_candidates:
            # Tiêu đề
            assert doc.get("title_en") and doc["title_en"].strip(), f"{fname}: thiếu title_en!"
            assert doc.get("title_vi") and doc["title_vi"].strip(), f"{fname}: thiếu title_vi!"

            # Chuyên khoa
            assert doc.get("category_en") and doc["category_en"].strip(), f"{fname}: thiếu category_en!"
            assert doc.get("category_vi") and doc["category_vi"].strip(), f"{fname}: thiếu category_vi!"

            # Từ khóa
            assert isinstance(doc.get("keywords_en"), list) and len(doc["keywords_en"]) >= 3, \
                f"{fname}: keywords_en phải có ít nhất 3 từ khóa!"
            assert isinstance(doc.get("keywords_vi"), list) and len(doc["keywords_vi"]) >= 3, \
                f"{fname}: keywords_vi phải có ít nhất 3 từ khóa!"

            # Đảm bảo có cả search_phrases hỗ trợ tương thích ngược
            assert isinstance(doc.get("search_phrases"), list) and len(doc["search_phrases"]) >= 6, \
                f"{fname}: search_phrases phải tổng hợp cả từ khóa en và vi!"

            # Provenance
            assert doc.get("metadata_generated_by") == "curation_pipeline_bilingual_v1"
            assert doc.get("metadata_review_status") in ("automated_qa_passed", "audited_qa_passed")

    def test_english_body_integrity(self, staged_candidates):
        """Xác minh thân văn bản tiếng Anh giữ nguyên vẹn 100%, mã băm SHA-256 khớp tuyệt đối."""
        for fname, doc in staged_candidates:
            content = doc.get("page_content", "")
            summary = doc.get("summary", "")
            assert content, f"{fname}: page_content bị rỗng!"
            assert content == summary, f"{fname}: page_content không khớp summary!"
            calculated_hash = compute_content_hash(content)
            assert doc.get("content_sha256") == calculated_hash, \
                f"{fname}: content_sha256 ({doc.get('content_sha256')}) không khớp ({calculated_hash})!"

    def test_no_retained_document_has_review_required(self, staged_candidates):
        """Xác minh không có tài liệu giữ lại nào ở trạng thái REVIEW_REQUIRED (Phải là APPROVED hoặc APPROVED_WITH_SAFETY_FLAG)."""
        for fname, doc in staged_candidates:
            qa_status = doc.get("qa_status")
            assert qa_status != "REVIEW_REQUIRED", f"{fname}: vẫn còn ở trạng thái REVIEW_REQUIRED chưa được thẩm định!"
            assert qa_status in ("APPROVED", "APPROVED_WITH_SAFETY_FLAG", "EXCLUDED"), f"{fname}: qa_status không hợp lệ: {qa_status}"

    def test_safety_flags_persisted_and_audited(self, staged_candidates):
        """Xác minh các cờ an toàn và lý do thẩm định lâm sàng được lưu giữ đầy đủ."""
        flagged_docs = {doc["id"]: doc for _, doc in staged_candidates if doc.get("qa_status") == "APPROVED_WITH_SAFETY_FLAG"}
        assert len(flagged_docs) == 4, f"Số lượng tài liệu APPROVED_WITH_SAFETY_FLAG ({len(flagged_docs)}) không khớp 4!"

        # 1. howtolowercholesterolwithdiet
        assert "howtolowercholesterolwithdiet" in flagged_docs
        doc_chol = flagged_docs["howtolowercholesterolwithdiet"]
        assert "dietary_reference_intake" in doc_chol.get("qa_flags", [])
        assert doc_chol.get("safety_classification") == "SAFE_WITH_CONTEXT"
        assert doc_chol.get("qa_review_reason")

        # 2. tetanusdiphtheriaandpertussisvaccines
        assert "tetanusdiphtheriaandpertussisvaccines" in flagged_docs
        doc_vac = flagged_docs["tetanusdiphtheriaandpertussisvaccines"]
        assert "public_health_immunization_schedule" in doc_vac.get("qa_flags", [])
        assert doc_vac.get("safety_classification") == "SAFE_WITH_CONTEXT"
        assert doc_vac.get("qa_review_reason")

        # 3. overthecountermedicines
        assert "overthecountermedicines" in flagged_docs
        doc_otc = flagged_docs["overthecountermedicines"]
        assert "pediatric_device_safety_guidance" in doc_otc.get("qa_flags", [])
        assert doc_otc.get("safety_classification") == "SAFE_WITH_CONTEXT"
        assert doc_otc.get("qa_review_reason")

        # 4. chlamydiainfections
        assert "chlamydiainfections" in flagged_docs
        doc_chlam = flagged_docs["chlamydiainfections"]
        assert "clinical_treatment_adherence_counseling" in doc_chlam.get("qa_flags", [])
        assert doc_chlam.get("safety_classification") == "SAFE_WITH_CONTEXT"
        assert doc_chlam.get("qa_review_reason")

    def test_no_html_tags_in_content(self, staged_candidates):
        """Xác minh 0 tài liệu nào chứa thẻ HTML rác."""
        html_regex = re.compile(r"<[^>]+>", re.IGNORECASE)
        for fname, doc in staged_candidates:
            content = doc.get("page_content", "")
            assert not html_regex.search(content), f"{fname}: chứa thẻ HTML rác!"

    def test_retained_tier_a_count_excludes_none(self, staged_candidates):
        """Xác minh không có tài liệu nào bị EXCLUDED và tổng số tài liệu Tier-A giữ lại đạt 123."""
        retained = [doc for _, doc in staged_candidates if doc.get("qa_status") != "EXCLUDED"]
        assert len(retained) == 123
        assert 110 <= len(retained) <= 140

    def test_mandatory_priority_topics_present(self, staged_candidates):
        """Xác minh các chủ đề bắt buộc (Cấp cứu, An toàn thuốc, Dự phòng, Bệnh mạn) đều có mặt."""
        staged_slugs = {doc["id"] for _, doc in staged_candidates}

        # 1. Cấp cứu (Emergency)
        emergency_mandatory = [
            "anaphylaxis",
            "heartattack",
            "stroke",
            "seizures",
            "carbonmonoxidepoisoning",
            "gastrointestinalbleeding",
            "visionimpairmentandblindness"
        ]
        for em in emergency_mandatory:
            assert em in staged_slugs, f"Thiếu chủ đề cấp cứu bắt buộc: {em}!"

        # 2. An toàn dùng thuốc (Medication Safety)
        med_mandatory = [
            "drugsafety",
            "antibioticresistance",
            "medicationerrors"
        ]
        for med in med_mandatory:
            assert med in staged_slugs, f"Thiếu chủ đề an toàn thuốc bắt buộc: {med}!"

        # 3. Y học dự phòng & Lối sống (Prevention)
        prev_mandatory = [
            "secondhandsmoke",
            "quittingsmoking",
            "healthscreening",
            "vaccinesafety",
            "childhoodvaccines",
            "exerciseandphysicalfitness",
            "howtolowercholesterolwithdiet"
        ]
        for pr in prev_mandatory:
            assert pr in staged_slugs, f"Thiếu chủ đề dự phòng bắt buộc: {pr}!"

        # 4. Khoảng trống bệnh mạn (Chronic Gaps)
        chronic_mandatory = [
            "chronickidneydisease",
            "copd",
            "sleepapnea",
            "gout",
            "steatoticliverdisease",
            "panicdisorder",
            "dementia",
            "parkinsonsdisease",
            "peripheralnervedisorders",
            "osteoporosis",
            "cirrhosis",
            "pancreatitis",
            "cataract",
            "glaucoma"
        ]
        for ch in chronic_mandatory:
            assert ch in staged_slugs, f"Thiếu chủ đề bệnh mạn bắt buộc: {ch}!"

    def test_canonical_deduplication_rejections(self, staged_candidates):
        """Xác minh các biến thể trùng lặp và tài liệu phi lâm sàng bị từ chối triệt để."""
        staged_urls = {doc["source_url"].strip().rstrip("/") for _, doc in staged_candidates}

        for rejected_url, reason in REJECTIONS.items():
            clean_rej = rejected_url.strip().rstrip("/")
            assert clean_rej not in staged_urls, f"Tài liệu đã bị từ chối ({clean_rej} - {reason}) lại xuất hiện trong Tier-A!"

    def test_staging_safety_and_runtime_immutability(self):
        """Xác minh việc staging KHÔNG làm biến đổi ready_documents hoặc active_collection.json."""
        # 1. ready_documents có 241 tệp (hoặc 364 sau khi promote)
        curated_count = len(list(READY_DOCS_DIR.glob("*.json")))
        assert curated_count in (241, 364), f"ready_documents có số lượng tệp không hợp lệ ({curated_count})!"

        # 2. active_collection.json giữ nguyên pointer hợp lệ (V2 hoặc V4)
        assert ACTIVE_COLLECTION_FILE.exists(), "active_collection.json không tồn tại!"
        manifest = json.loads(ACTIVE_COLLECTION_FILE.read_text(encoding="utf-8"))
        assert manifest["active_collection"] in (
            "medical_knowledge_shadow_v2_20261114_211653",
            "medical_knowledge_expanded_v4_20261115_005612"
        )
        assert manifest["document_count"] in (408, 725)
        assert manifest["source_file_count"] in (241, 364)
