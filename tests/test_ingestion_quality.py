"""
================================================================================
🧪 TEST SUITE: INGESTION QUALITY NORMALIZATION (PHASE 6.1)
================================================================================
Kiểm thử toàn diện các yêu cầu chất lượng pipeline nạp dữ liệu y khoa RAG:
  1. Bảo toàn ranh giới câu, đoạn văn và từ (không cắt gãy từ giữa chừng).
  2. Gắn Contextual Prefix (Tên bệnh, Chuyên khoa, Từ khóa) vào 100% chunks.
  3. Gộp phần đuôi nhỏ (< 200 ký tự) vào chunk trước đó, loại bỏ orphan chunks.
  4. Document ID tất định (doc_{slug}_{source_hash8}_p{part_index}), độc lập thứ tự.
  5. SHA-256 content fingerprinting và phát hiện tài liệu trùng lặp.
  6. Quản lý Manifest nguyên tử (Atomic active_collection.json) và tính hợp lệ schema.
  7. Tích hợp cấu hình tập trung (core.settings IngestionSettings).
  8. Độ an toàn của chế độ --dry-run (không kết nối hay sửa đổi database).
  9. Khả năng tương thích dự phòng (fallback) của RAG Service khi chưa có manifest.
================================================================================
"""

import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from core.document_chunker import (
    compute_content_hash,
    generate_deterministic_id,
    find_boundary_split_point,
    chunk_document,
    detect_duplicates,
    save_manifest_atomic,
    load_manifest,
    validate_manifest,
)
from core.settings import Settings, get_settings
from scripts.ingest import (
    load_raw_curated_documents,
    prepare_ingestion_chunks,
    run_dry_run,
)
from core.rag_service import MedicalRAGService, DEFAULT_COLLECTION_NAME


class TestBoundaryPreservationAndChunking:
    """Kiểm tra thuật toán tìm ranh giới và phân đoạn không cắt gãy từ."""

    def test_find_boundary_split_point_prefers_paragraphs(self):
        """Ưu tiên cắt ở ranh giới đoạn văn (double newline) khi khả dụng."""
        para1 = "Đây là đoạn văn thứ nhất về bệnh viêm phổi." + (" Nội dung mở rộng." * 20)
        para2 = "\n\nĐây là đoạn văn thứ hai về điều trị kháng sinh." + (" Chi tiết điều trị." * 20)
        text = para1 + para2
        split_idx = find_boundary_split_point(text, max_chars=len(para1) + 50, min_chunk_chars=100)
        assert split_idx == len(para1)
        assert text[split_idx:split_idx + 2] == "\n\n"

    def test_find_boundary_split_point_prefers_sentence_over_word(self):
        """Ưu tiên cắt ở kết thúc câu (.!?) khi không có ranh giới đoạn văn."""
        sent1 = "Bệnh nhân có triệu chứng sốt cao và đau đầu dữ dội."
        sent2 = " Các xét nghiệm máu cho thấy bạch cầu tăng cao."
        sent3 = " Cần tiến hành chụp X-quang phổi ngay."
        text = sent1 + sent2 + sent3
        max_c = len(sent1) + len(sent2) + 10
        split_idx = find_boundary_split_point(text, max_chars=max_c, min_chunk_chars=30)
        # Điểm cắt phải tách hoàn toàn sau sent2 và trước sent3
        assert text[:split_idx].strip() == (sent1 + sent2).strip()
        assert text[split_idx:].startswith("Cần")

    def test_find_boundary_split_point_never_cuts_words(self):
        """Không bao giờ cắt giữa chừng một từ dài nếu có ranh giới từ."""
        words = ["internationalization", "cardiovascular", "gastroenterology", "pneumonoultramicroscopicsilicovolcanoconiosis"]
        text = " ".join(words * 5)
        split_idx = find_boundary_split_point(text, max_chars=150, min_chunk_chars=50)
        # Ký tự tại split_idx phải là khoảng trắng hoặc kết thúc từ
        assert text[split_idx] == " " or split_idx == len(text)
        # Đoạn cắt ra không được kết thúc bằng từ bị xẻ đôi
        chunk_text = text[:split_idx]
        last_word = chunk_text.split()[-1]
        assert last_word in words

    def test_contextual_prefix_attached_to_all_chunks(self):
        """Đảm bảo Contextual Prefix xuất hiện ở 100% các chunks, kể cả chunk con."""
        title = "Bệnh Đái tháo đường Tuýp 2"
        category = "Nội tiết"
        search_phrases = "tiểu đường, insulin, glucose"
        # Tạo văn bản dài ~5000 ký tự để bắt buộc phân thành nhiều chunk
        content = ("Triệu chứng bao gồm khát nước nhiều, đi tiểu thường xuyên và sụt cân không rõ nguyên nhân. " * 50)

        chunks = chunk_document(
            title=title,
            category=category,
            content=content,
            search_phrases=search_phrases,
            max_chars=1000,
            overlap_chars=100,
            min_chunk_chars=100
        )

        assert len(chunks) >= 3, f"Văn bản dài phải được phân tách thành ít nhất 3 chunks, nhận được {len(chunks)}"

        expected_prefix_start = f"Bệnh/Chủ đề: {title}\nChuyên khoa: {category}\nTừ khóa liên quan: {search_phrases}\n\nNội dung chi tiết:\n"

        for idx, chunk in enumerate(chunks):
            assert chunk["part_index"] == idx
            assert chunk["text"].startswith(expected_prefix_start), f"Chunk {idx} thiếu contextual prefix!"
            assert len(chunk["text"]) <= 2200, f"Chunk {idx} vượt quá hard_max_chars: {len(chunk['text'])}"

    def test_tiny_tail_merging_prevents_orphan_chunks(self):
        """Phần đuôi nhỏ (< 200 ký tự) phải được gộp vào chunk trước đó."""
        title = "Cảm cúm thông thường"
        category = "Hô hấp"
        # Tạo đoạn văn bản sao cho phần dư sau khi cắt chunk 1 chỉ khoảng 80 ký tự
        chunk1_body = "Triệu chứng ban đầu của cảm cúm là đau họng và nghẹt mũi kéo dài khoảng một tuần. " * 8
        tiny_tail = "Nếu sốt cao trên 39 độ cần đi khám bác sĩ ngay lập tức."
        content = chunk1_body + "\n\n" + tiny_tail

        chunks = chunk_document(
            title=title,
            category=category,
            content=content,
            max_chars=len(chunk1_body) + 150,
            overlap_chars=50,
            min_chunk_chars=200,
            hard_max_chars=3000
        )

        # Vì tiny_tail < 200 ký tự, nó phải được gộp vào chunk trước, không tạo chunk riêng
        assert len(chunks) == 1
        assert tiny_tail in chunks[0]["text"]
        assert chunks[0]["char_count"] == len(chunks[0]["text"])

    def test_empty_content_returns_empty_list(self):
        """Văn bản rỗng trả về danh sách rỗng, không gây lỗi runtime."""
        chunks = chunk_document(title="Trống", category="Khác", content="   \n  ")
        assert chunks == []


class TestDeterministicDocumentIDs:
    """Kiểm thử tính tất định và ổn định của Document IDs."""

    def test_deterministic_id_reproducible_and_stable(self):
        """Document ID tạo ra phải hoàn toàn giống nhau bất kể số lần chạy hay thứ tự."""
        file_name = "respiratory_seasonal_allergies.json"
        source_url = "https://medlineplus.gov/ency/article/000813.htm"

        id_1 = generate_deterministic_id(file_name, source_url, part_index=0)
        id_2 = generate_deterministic_id(file_name, source_url, part_index=0)
        id_part1 = generate_deterministic_id(file_name, source_url, part_index=1)

        assert id_1 == id_2
        assert id_1.startswith("doc_respiratory_seasonal_allergies_")
        assert id_1.endswith("_p0")
        assert id_part1.endswith("_p1")
        assert id_1 != id_part1

    def test_slug_collisions_prevented_by_source_hash(self):
        """Hai tài liệu có cùng tên file nhưng nguồn khác nhau sẽ có ID phân biệt nhờ 8-char hash."""
        id_a = generate_deterministic_id("pneumonia.json", "https://medlineplus.gov/ency/article/000145.htm", 0)
        id_b = generate_deterministic_id("pneumonia.json", "https://medlineplus.gov/ency/article/000146.htm", 0)

        assert id_a != id_b
        assert id_a.startswith("doc_pneumonia_")
        assert id_b.startswith("doc_pneumonia_")

    def test_special_characters_in_filename_sanitized(self):
        """Ký tự đặc biệt, khoảng trắng và dấu tiếng Việt được chuẩn hóa thành slug an toàn."""
        dirty_name = "Bệnh Viêm Gan Siêu Vi C (2026)!@#.json"
        clean_id = generate_deterministic_id(dirty_name, "https://medlineplus.gov", 0)
        assert " " not in clean_id
        assert "!" not in clean_id
        assert "@" not in clean_id
        assert "#" not in clean_id
        assert clean_id.startswith("doc_")
        assert clean_id.endswith("_p0")


class TestContentHashAndDuplicateDetection:
    """Kiểm tra fingerprint SHA-256 và khử trùng lặp dữ liệu trước khi nạp."""

    def test_compute_content_hash_consistency(self):
        """Mã băm SHA-256 nhất quán sau khi chuẩn hóa khoảng trắng thừa."""
        t1 = "  Bệnh nhân sốt cao, co giật.  \n"
        t2 = "Bệnh nhân sốt cao, co giật."
        assert compute_content_hash(t1) == compute_content_hash(t2)

    def test_detect_duplicates_identifies_and_excludes_duplicates(self):
        """Phát hiện chính xác tài liệu trùng lặp và giữ lại bản ghi canonical đầu tiên."""
        raw_docs = [
            {"file_name": "doc1.json", "title": "Bệnh A", "page_content": "Nội dung chuẩn A về triệu chứng."},
            {"file_name": "doc2.json", "title": "Bệnh B", "page_content": "Nội dung chuẩn B về chẩn đoán."},
            {"file_name": "doc3_duplicate.json", "title": "Bệnh A trùng lặp", "page_content": "Nội dung chuẩn A về triệu chứng."}
        ]

        unique_docs, report = detect_duplicates(raw_docs)
        assert len(unique_docs) == 2
        assert report["total_scanned"] == 3
        assert report["unique_count"] == 2
        assert report["duplicate_count"] == 1
        assert report["duplicates"][0]["duplicate_file"] == "doc3_duplicate.json"
        assert report["duplicates"][0]["original_file"] == "doc1.json"


class TestAtomicManifestManagement:
    """Kiểm thử tính nguyên tử và hợp lệ của Manifest active_collection.json."""

    def test_save_and_load_manifest_atomic(self, tmp_path):
        """Lưu manifest nguyên tử và đọc lại thành công."""
        manifest_data = {
            "active_collection": "medical_knowledge_20261114_204500",
            "created_at": "2026-11-14T20:45:00",
            "updated_at": "2026-11-14T20:45:00",
            "document_count": 408,
            "source_file_count": 241,
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dimension": 384,
            "chunking_version": "v2_sentence_contextual",
            "chunk_config": {
                "max_chars": 2000,
                "overlap_chars": 200,
                "min_chunk_chars": 200,
                "hard_max_chars": 2200
            },
            "version": "20261114_204500"
        }

        meta_file = tmp_path / "active_collection.json"
        save_manifest_atomic(manifest_data, meta_file)

        assert meta_file.exists()
        loaded = load_manifest(tmp_path)
        assert loaded is not None
        assert loaded["active_collection"] == "medical_knowledge_20261114_204500"
        assert loaded["document_count"] == 408
        assert loaded["embedding_dimension"] == 384

    def test_validate_manifest_rejects_invalid_data(self):
        """Từ chối các định dạng manifest không hợp lệ."""
        assert validate_manifest(None) is False
        assert validate_manifest("string") is False
        assert validate_manifest({}) is False
        assert validate_manifest({"active_collection": ""}) is False
        assert validate_manifest({"active_collection": "valid_name", "document_count": -5}) is False
        assert validate_manifest({"active_collection": "valid_name", "document_count": 100}) is True

    def test_load_manifest_returns_none_on_corrupt_file(self, tmp_path):
        """Trả về None an toàn khi tệp manifest bị rỗng hoặc lỗi cú pháp JSON."""
        bad_file = tmp_path / "active_collection.json"
        bad_file.write_text("{corrupt_json: invalid", encoding="utf-8")
        assert load_manifest(tmp_path) is None


class TestSettingsAndDryRunSafety:
    """Kiểm tra tích hợp Settings và an toàn của chế độ --dry-run."""

    def test_ingestion_settings_integration(self):
        """Settings phân giải đúng các tham số Ingestion từ biến môi trường."""
        custom_env = {
            "INGEST_CHUNK_MAX_CHARS": "1800",
            "INGEST_CHUNK_OVERLAP_CHARS": "150",
            "INGEST_MIN_CHUNK_CHARS": "250",
            "INGEST_BATCH_SIZE": "25",
            "INGEST_CHUNKING_VERSION": "v2_custom_test"
        }
        with patch.dict(os.environ, custom_env):
            s = Settings(_env_file=None)
            assert s.ingestion.chunk_max_chars == 1800
            assert s.ingestion.chunk_overlap_chars == 150
            assert s.ingestion.min_chunk_chars == 250
            assert s.ingestion.batch_size == 25
            assert s.ingestion.chunking_version == "v2_custom_test"

    def test_dry_run_executes_without_mutating_disk(self):
        """Chế độ dry-run chạy trơn tru trên 241 tệp mà không tạo hay sửa active_collection.json."""
        manifest_path = Path("medical_vectordb/active_collection.json")
        existed_before = manifest_path.exists()

        stats = run_dry_run()

        assert stats["total_source_files"] == 241
        assert stats["unique_source_files"] == 241
        assert stats["total_chunks_planned"] == 408
        assert stats["tiny_chunks_count"] == 0
        assert stats["broken_starts_count"] == 0
        assert "100.0%" in stats["prefix_coverage_ratio"]

        # Tuyệt đối không tạo active_collection.json trong dry-run
        assert manifest_path.exists() == existed_before


class TestRAGServiceManifestFallbackCompatibility:
    """Kiểm tra RAG Service tự động fallback an toàn khi chưa có active_collection.json."""

    def test_rag_service_resolves_default_when_no_manifest(self, tmp_path):
        """Khi không có active_collection.json, RAG Service trỏ về DEFAULT_COLLECTION_NAME."""
        rag = MedicalRAGService(db_dir=str(tmp_path), vector_search_enabled=False)
        assert rag.collection_name == DEFAULT_COLLECTION_NAME

    def test_rag_service_resolves_manifest_collection_when_present(self, tmp_path):
        """Khi có active_collection.json hợp lệ, RAG Service đọc đúng tên collection phiên bản mới."""
        manifest = {
            "active_collection": "medical_knowledge_v2_shadow",
            "created_at": "2026-11-14T20:00:00",
            "document_count": 408
        }
        save_manifest_atomic(manifest, tmp_path / "active_collection.json")

        rag = MedicalRAGService(db_dir=str(tmp_path), vector_search_enabled=False)
        assert rag.collection_name == "medical_knowledge_v2_shadow"
