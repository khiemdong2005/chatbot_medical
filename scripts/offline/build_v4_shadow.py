"""
Builds medical_knowledge_expanded_v4_<timestamp> in ChromaDB.
Combines data/curated/ready_documents_enriched (241) and data/curated/tier_a_candidates (123).
Shadow mode: True (active_collection.json is preserved).
"""

import sys
import time
import json
import statistics
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ingest import run_ingestion, load_curated_medlineplus_documents
from core.settings import get_settings

ENRICHED_DIR = ROOT / "data" / "curated" / "ready_documents_enriched"
TIER_A_DIR = ROOT / "data" / "curated" / "tier_a_candidates"
ACTIVE_CONFIG = ROOT / "medical_vectordb" / "active_collection.json"


def percentile(values, p):
    if not values:
        return 0.0
    v = sorted(values)
    pos = (len(v) - 1) * p
    lower, upper = int(pos), min(len(v) - 1, int(pos) + 1)
    return v[lower] + (v[upper] - v[lower]) * (pos - lower)


def main():
    print("=" * 80)
    print("🚀 BẮT ĐẦU XÂY DỰNG SHADOW COLLECTION V4 (SYMMETRIC BILINGUAL)")
    print("=" * 80)

    # 1. Đo đạc prefix budget
    raw_chunks = load_curated_medlineplus_documents(curated_dirs=[ENRICHED_DIR, TIER_A_DIR])
    print(f"Tổng số chunks đã chuẩn bị: {len(raw_chunks)}")

    prefix_lengths = []
    for c in raw_chunks:
        # Tách phần prefix trước "\n\nNội dung chi tiết:\n"
        txt = c["text"]
        if "\n\nNội dung chi tiết:\n" in txt:
            pref = txt.split("\n\nNội dung chi tiết:\n")[0]
            prefix_lengths.append(len(pref))

    mean_prefix = round(statistics.mean(prefix_lengths), 1) if prefix_lengths else 0
    p95_prefix = round(percentile(prefix_lengths, 0.95), 1) if prefix_lengths else 0
    print(f"Prefix budget: Mean = {mean_prefix} chars | P95 = {p95_prefix} chars")

    # 2. Xây dựng collection V4
    timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    v4_name = f"medical_knowledge_expanded_v4_{timestamp_tag}"

    before_active = json.loads(ACTIVE_CONFIG.read_text(encoding="utf-8"))["active_collection"]
    print(f"Active collection trước khi nạp: {before_active}")

    t0 = time.perf_counter()
    success, stats = run_ingestion(
        shadow_mode=True,
        collection_name_override=v4_name,
        curated_dirs=[ENRICHED_DIR, TIER_A_DIR]
    )
    total_time_ms = (time.perf_counter() - t0) * 1000

    after_active = json.loads(ACTIVE_CONFIG.read_text(encoding="utf-8"))["active_collection"]
    print(f"Active collection sau khi nạp: {after_active}")
    assert before_active == after_active, "active_collection.json KHÔNG ĐƯỢC PHÉP THAY ĐỔI!"

    print("\n" + "=" * 80)
    print("✅ XÂY DỰNG THÀNH CÔNG SHADOW COLLECTION V4!")
    print(f" • Collection Name: {v4_name}")
    print(f" • Total Source Files: {len(list(ENRICHED_DIR.glob('*.json'))) + len([f for f in TIER_A_DIR.glob('*.json') if not f.name.startswith('_')])}")
    print(f" • Total Chunks: {len(raw_chunks)}")
    print(f" • Prefix Budget: Mean = {mean_prefix} chars | P95 = {p95_prefix} chars")
    print(f" • Build Time: {total_time_ms:.1f} ms (~{total_time_ms/1000:.1f} s)")
    print(f" • Invariant Verified: active_collection vẫn giữ nguyên {after_active}")
    print("=" * 80)

    # Lưu thông tin shadow V4 để evaluator sử dụng
    info_path = ROOT / "data" / "curated" / "v4_shadow_manifest.json"
    info_path.write_text(json.dumps({
        "collection_name": v4_name,
        "created_at": datetime.now().isoformat(),
        "source_count": 364,
        "chunk_count": len(raw_chunks),
        "mean_prefix_chars": mean_prefix,
        "p95_prefix_chars": p95_prefix,
        "build_time_ms": round(total_time_ms, 1)
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
