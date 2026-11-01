import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import chromadb
from core.rag_service import MedicalRAGService
from ingest import run_ingestion


def test_rag_distance_metric_and_acceptance_threshold(tmp_path):
    """Kiểm thử 7a: RAG sử dụng L2 distance, minh bạch metric và lọc theo ngưỡng chấp nhận."""
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.create_collection("medical_knowledge")

    # Thêm 2 tài liệu: 1 tài liệu khớp cao, 1 tài liệu hoàn toàn không liên quan
    collection.add(
        ids=["doc_relevant", "doc_irrelevant"],
        documents=[
            "Bệnh cảm cúm: Triệu chứng sốt, ho, đau họng. Cách chăm sóc: nghỉ ngơi, uống nhiều nước.",
            "Lập trình hướng đối tượng trong Python và cách sử dụng decorator."
        ],
        metadatas=[
            {"title": "Cảm cúm mùa", "category": "Hô hấp", "source": "MedlinePlus", "source_url": "https://medlineplus.gov/flu"},
            {"title": "Tài liệu kỹ thuật", "category": "CNTT", "source": "DevDocs", "source_url": "https://dev.to"}
        ]
    )

    rag = MedicalRAGService(db_dir=tmp_path, acceptance_threshold=1.35)
    docs = rag.retrieve_context("triệu chứng sốt và đau họng", top_k=2)

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
    active_col = client.create_collection("medical_knowledge_v1")
    active_col.add(
        ids=[f"id_{i}" for i in range(5)],
        documents=[f"Nội dung y khoa {i}" for i in range(5)],
        metadatas=[{"title": f"Bài {i}"} for i in range(5)]
    )

    # Đánh dấu medical_knowledge_v1 là active
    meta_file = db_dir / "active_collection.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"active_collection": "medical_knowledge_v1", "document_count": 5}, f)

    assert active_col.count() == 5

    # 2. Giả lập quá trình ingestion mới bị lỗi giữa chừng
    with patch("ingest.load_curated_medlineplus_documents") as mock_load:
        mock_load.return_value = []  # Giả lập thư mục curated bị trống hoặc lỗi

        success, msg = run_ingestion(custom_db_dir=db_dir)
        assert success is False

    # 3. Kiểm tra collection cũ: Vẫn hoàn toàn nguyên vẹn với 5 tài liệu!
    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["active_collection"] == "medical_knowledge_v1"

    recheck_col = client.get_collection("medical_knowledge_v1")
    assert recheck_col.count() == 5

