"""
scripts/promote_and_unify_sources.py
Phase 6.7 Source Promotion & Canonical Corpus Unification:
  1. Promotes 123 Tier-A candidates into data/curated/ready_documents/ and data/curated/ready_documents_enriched/.
  2. Updates 241 legacy documents in ready_documents/ with symmetric bilingual metadata (keeping 100% body_en).
  3. Verifies exactly 364 files, 0 duplicate URLs, 0 duplicate contents, 100% bilingual coverage.
  4. Runs dry-run chunking to verify exact 725 chunks and deterministic chunk IDs matching V4.
"""

import os
import sys
import json
import shutil
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.document_chunker import chunk_document, compute_content_hash
from scripts.ingest import load_curated_medlineplus_documents

READY_DIR = ROOT / "data" / "curated" / "ready_documents"
ENRICHED_DIR = ROOT / "data" / "curated" / "ready_documents_enriched"
TIER_A_DIR = ROOT / "data" / "curated" / "tier_a_candidates"
LEGACY_ORIGINAL_BACKUP = ROOT / "data" / "curated" / "ready_documents_legacy_original_backup"


def run_promotion():
    print("=" * 80)
    print("🚀 BẮT ĐẦU QUY TRÌNH SOURCE PROMOTION & CHUẨN HÓA CANONICAL CORPUS (PHASE 6.7)")
    print("=" * 80)

    # 1. Kiểm tra số lượng trước khi promote
    before_ready = sorted(list(READY_DIR.glob("*.json")))
    before_enriched = sorted(list(ENRICHED_DIR.glob("*.json")))
    tier_a_files = sorted([f for f in TIER_A_DIR.glob("*.json") if not f.name.startswith("_")])

    print(f" • Ready documents hiện tại: {len(before_ready)} tệp (Kỳ vọng: 241 hoặc 364)")
    print(f" • Enriched documents hiện tại: {len(before_enriched)} tệp (Kỳ vọng: 241 hoặc 364)")
    print(f" • Tier-A documents: {len(tier_a_files)} tệp (Kỳ vọng: 123)")

    assert len(tier_a_files) == 123, f"Sai lệch số lượng Tier-A: {len(tier_a_files)}"

    # Nếu chưa backup, thực hiện backup
    if not LEGACY_ORIGINAL_BACKUP.exists() and len(before_ready) == 241:
        LEGACY_ORIGINAL_BACKUP.mkdir(parents=True, exist_ok=True)
        for rf in before_ready:
            shutil.copy2(rf, LEGACY_ORIGINAL_BACKUP / rf.name)
        print(f"✅ Đã tạo bản lưu trữ dự phòng 241 tệp legacy gốc tại: {LEGACY_ORIGINAL_BACKUP.name}")

    legacy_source_dir = LEGACY_ORIGINAL_BACKUP if LEGACY_ORIGINAL_BACKUP.exists() else READY_DIR
    legacy_files = sorted(list(legacy_source_dir.glob("*.json")))
    assert len(legacy_files) == 241, f"Bản lưu legacy phải có 241 tệp, có {len(legacy_files)}"

    # Cập nhật 241 tệp legacy trong ready_documents bằng phiên bản enriched
    for ef in ENRICHED_DIR.glob("*.json"):
        if ef.name in [f.name for f in legacy_files]:
            target_file = READY_DIR / ef.name
            enriched_data = json.loads(ef.read_text(encoding="utf-8"))
            target_file.write_text(json.dumps(enriched_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Promote 123 tệp Tier-A vào cả READY_DIR và ENRICHED_DIR
    for tf in tier_a_files:
        dest_ready = READY_DIR / tf.name
        dest_enriched = ENRICHED_DIR / tf.name
        shutil.copy2(tf, dest_ready)
        shutil.copy2(tf, dest_enriched)

    after_ready = sorted(list(READY_DIR.glob("*.json")))
    after_enriched = sorted(list(ENRICHED_DIR.glob("*.json")))

    print(f"\n✅ Đã promote thành công:")
    print(f" • Ready Documents sau promote: {len(after_ready)} tệp (Kỳ vọng: 364)")
    print(f" • Enriched Documents sau promote: {len(after_enriched)} tệp (Kỳ vọng: 364)")
    assert len(after_ready) == 364, f"Số lượng ready sau promote không phải 364: {len(after_ready)}"
    assert len(after_enriched) == 364, f"Số lượng enriched sau promote không phải 364: {len(after_enriched)}"

    # 4. Xác minh không trùng lặp giữa Tier-A và Ready Documents gốc
    curated_urls = {
        json.loads(f.read_text(encoding="utf-8")).get("source_url", "").strip().rstrip("/")
        for f in legacy_files
    }
    curated_hashes = {
        json.loads(f.read_text(encoding="utf-8")).get("content_sha256") or
        hashlib.sha256((json.loads(f.read_text(encoding="utf-8")).get("page_content") or "").encode("utf-8")).hexdigest()
        for f in legacy_files
    }

    tier_a_urls = set()
    tier_a_hashes = set()
    for tf in tier_a_files:
        d = json.loads(tf.read_text(encoding="utf-8"))
        u = d.get("source_url", "").strip().rstrip("/")
        ch = d.get("content_sha256") or hashlib.sha256((d.get("page_content") or "").encode("utf-8")).hexdigest()

        # Không trùng lặp với ready_documents gốc
        assert u not in curated_urls, f"Tier-A trùng URL ({u}) với ready_documents gốc!"
        assert ch not in curated_hashes, f"Tier-A trùng nội dung ({ch}) với ready_documents gốc!"

        # Không trùng lặp trong nội bộ Tier-A
        assert u not in tier_a_urls, f"Tier-A trùng lặp nội bộ URL: {u}"
        assert ch not in tier_a_hashes, f"Tier-A trùng lặp nội bộ content hash: {ch}"

        tier_a_urls.add(u)
        tier_a_hashes.add(ch)

    print(f"✅ Kiểm tra toàn vẹn Tier-A vs Ready Documents:")
    print(f" • Trùng lặp URLs giữa Tier-A và ready gốc: 0")
    print(f" • Trùng lặp nội dung giữa Tier-A và ready gốc: 0")
    print(f" • Trùng lặp nội bộ Tier-A: 0")

    # Kiểm tra siêu dữ liệu song ngữ đối xứng trên toàn bộ 364 tệp
    for f in after_ready:
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("title_en") and d["title_en"].strip(), f"Thiếu title_en: {f.name}"
        assert d.get("title_vi") and d["title_vi"].strip(), f"Thiếu title_vi: {f.name}"
        assert d.get("category_en") and d["category_en"].strip(), f"Thiếu category_en: {f.name}"
        assert d.get("category_vi") and d["category_vi"].strip(), f"Thiếu category_vi: {f.name}"
        kw_en = d.get("keywords_en") or []
        kw_vi = d.get("keywords_vi") or []
        assert isinstance(kw_en, list) and len(kw_en) >= 3, f"Thiếu keywords_en: {f.name}"
        assert isinstance(kw_vi, list) and len(kw_vi) >= 3, f"Thiếu keywords_vi: {f.name}"

    print(f" • Độ phủ song ngữ: 100% (364/364 tệp có đầy đủ title_vi, title_en, category_vi, category_en, keywords_vi, keywords_en)")

    # 5. Chạy Dry-Run tái tạo chunks từ READY_DIR
    print("\n--- Chạy Ingestion Dry-Run trên Ready Documents Canonical (364 tệp) ---")
    raw_chunks = load_curated_medlineplus_documents(curated_dirs=[READY_DIR])
    print(f" • Số lượng chunks dự kiến: {len(raw_chunks)} (Kỳ vọng: 725)")
    assert len(raw_chunks) == 725, f"Số lượng chunks ({len(raw_chunks)}) không khớp 725!"

    # 6. Kiểm tra tính tất định của Chunk IDs đối chiếu với V4 trong ChromaDB
    import chromadb
    client = chromadb.PersistentClient(path=str(ROOT / "medical_vectordb"))
    v4_col = client.get_collection("medical_knowledge_expanded_v4_20261115_005612")
    v4_ids = set(v4_col.get()["ids"])
    dry_run_ids = set(c["id"] for c in raw_chunks)

    diff = v4_ids.symmetric_difference(dry_run_ids)
    print(f" • Sai lệch chunk IDs giữa Dry-Run và V4: {len(diff)}")
    assert len(diff) == 0, f"Chunk IDs không khớp tất định: {len(diff)} khác biệt!"
    print(f"✅ 100% Chunk IDs khớp tuyệt đối tất định với V4 ({len(v4_ids)} IDs)!")

    print("\n🎉 SOURCE PROMOTION & CANONICAL CORPUS REPRODUCIBILITY THÀNH CÔNG RỰC RỠ!")
    return True


if __name__ == "__main__":
    run_promotion()
