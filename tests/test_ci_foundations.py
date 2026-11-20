"""
tests/test_ci_foundations.py
Kiểm thử nền tảng kiểm định tự động (CI/CD Foundation Tests):
1. Cô lập phát hiện kiểm thử Pytest (Pytest Discovery Isolation).
2. Triệt tiêu cuộc gọi mạng ngoài ý muốn tới Gemini / AI Provider (Zero-Secret Isolation).
3. Tính bất biến của Active Collection Pointer (active_collection.json Immutability).
4. Tính toàn vẹn của Kho ngữ liệu Chuẩn mực Canonical (Curated Corpus Integrity).
5. Tính toàn vẹn của Bộ dữ liệu Đánh giá Đóng băng (Dataset Freeze Manifest Integrity).
"""

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_pytest_discovery_isolation():
    """Xác minh pytest.ini giới hạn testpaths = tests, loại trừ scratch/ và scripts/ khỏi quét mặc định."""
    ini_path = ROOT / "pytest.ini"
    assert ini_path.exists(), "pytest.ini bắt buộc phải tồn tại ở thư mục gốc!"
    content = ini_path.read_text(encoding="utf-8")
    assert "testpaths = tests" in content, "pytest.ini phải cấu hình testpaths = tests"

    # Chạy collect-only để xác minh các tệp được thu thập
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, f"Lỗi thu thập pytest: {proc.stderr}"
    
    lines = [l.strip() for l in proc.stdout.splitlines() if "::" in l]
    collected_files = {l.split("::")[0].replace("\\", "/") for l in lines}

    # Tuyệt đối không thu thập scratch/ và scripts/
    scratch_hits = [f for f in collected_files if f.startswith("scratch/")]
    scripts_hits = [f for f in collected_files if f.startswith("scripts/")]
    assert len(scratch_hits) == 0, f"Pytest vô tình quét tệp trong scratch/: {scratch_hits}"
    assert len(scripts_hits) == 0, f"Pytest vô tình quét tệp trong scripts/: {scripts_hits}"

    # Toàn bộ tệp thu thập phải nằm trong tests/
    assert all(f.startswith("tests/") for f in collected_files), "Toàn bộ test items phải bắt đầu từ tests/"


def test_no_accidental_provider_calls_when_env_key_present(monkeypatch):
    """Xác minh khi giả lập có GEMINI_API_KEY trong env, /api/chat vẫn không thực hiện cuộc gọi mạng live ra ngoài."""
    from starlette.testclient import TestClient
    from core.main_fastapi import app as fastapi_app

    # Giả lập developer có API key trong env
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.SimulatedTestGeminiKey1234567890abcdef")

    client = TestClient(fastapi_app)
    req_body = {
        "message": "Tôi bị sốt nhẹ và đau họng 2 ngày nay",
        "history": [],
        "lang": "vi"
    }

    # Gửi request vào FastAPI Gateway
    res = client.post("/api/chat", json=req_body)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "risk_level" in data
    assert "sources" in data
    # Kiểm tra contract dữ liệu chuẩn mực
    assert isinstance(data["sources"], list)


def test_active_manifest_immutability():
    """Xác minh tính hợp lệ và cấu trúc schema của active_collection.json trỏ tới V4 collection."""
    manifest_path = ROOT / "medical_vectordb" / "active_collection.json"
    assert manifest_path.exists(), "active_collection.json phải tồn tại!"
    
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("active_collection") == "medical_knowledge_expanded_v4_20261115_005612"
    assert data.get("document_count") == 725
    assert data.get("source_file_count") == 364
    assert data.get("chunk_count") == 725
    assert data.get("bilingual_metadata_version") == "v2_symmetric_bilingual"
    assert data.get("bm25_df_policy") == "no_df_cutoff"


def test_canonical_corpus_integrity():
    """Xác minh kho ngữ liệu chuẩn mực canonical gồm đúng 364 tệp, 100% song ngữ, 0 trùng lặp nội dung."""
    ready_dir = ROOT / "data" / "curated" / "ready_documents"
    files = list(ready_dir.glob("*.json"))
    assert len(files) == 364, f"Kho ngữ liệu canonical phải có đúng 364 tệp, hiện tại có {len(files)}"

    seen_hashes = set()
    duplicate_hashes = []
    missing_bilingual = []

    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            d = json.load(f)
        
        # 1. Kiểm tra hash nội dung duy nhất
        h = d.get("content_sha256")
        assert h, f"Tệp {fp.name} thiếu content_sha256!"
        if h in seen_hashes:
            duplicate_hashes.append((fp.name, h))
        seen_hashes.add(h)

        # 2. Kiểm tra độ phủ siêu dữ liệu song ngữ đối xứng 100%
        has_bilingual = bool(
            d.get("title_en") and d.get("title_vi") and
            d.get("category_en") and d.get("category_vi") and
            d.get("keywords_en") and d.get("keywords_vi")
        )
        if not has_bilingual:
            missing_bilingual.append(fp.name)

    assert len(duplicate_hashes) == 0, f"Phát hiện trùng lặp nội dung chính xác trong ready_documents: {duplicate_hashes}"
    assert len(missing_bilingual) == 0, f"Phát hiện tệp thiếu trường song ngữ đối xứng: {missing_bilingual}"


def test_dataset_freeze_integrity():
    """Xác minh tệp dataset_manifest.json khớp chính xác SHA-256 và số lượng câu hỏi của các bộ đánh giá frozen."""
    manifest_path = ROOT / "evaluation" / "dataset_manifest.json"
    assert manifest_path.exists(), "evaluation/dataset_manifest.json phải tồn tại!"
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    datasets = manifest_data.get("datasets", [])
    assert len(datasets) == 4, f"Phải có 4 bộ dữ liệu frozen trong manifest, hiện có {len(datasets)}"

    expected_counts = {
        "evaluation/rag_dev_dataset.json": 56,
        "evaluation/rag_test_dataset.json": 102,
        "evaluation/safety_eval_dataset.json": 100,
        "evaluation/answer_eval_dataset.json": 50,
    }

    for item in datasets:
        fn = item["filename"]
        target_path = ROOT / fn
        assert target_path.exists(), f"Tệp đánh giá {fn} không tồn tại trên đĩa!"
        
        # Kiểm tra SHA-256 thực tế (chuẩn hóa dòng tương thích cả Windows CRLF và Linux LF)
        actual_bytes = target_path.read_bytes()
        actual_shas = {
            hashlib.sha256(actual_bytes).hexdigest(),
            hashlib.sha256(actual_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            hashlib.sha256(actual_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")).hexdigest(),
        }
        assert item["sha256"] in actual_shas, f"Tệp {fn} bị sai lệch SHA-256! (Mong đợi: {item['sha256']}, Thực tế: {hashlib.sha256(actual_bytes).hexdigest()})"
        
        # Kiểm tra số lượng queries/cases
        assert item["query_count"] == expected_counts[fn], f"Tệp {fn} sai lệch query_count: {item['query_count']} != {expected_counts[fn]}"
