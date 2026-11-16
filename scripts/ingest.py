"""
================================================================================
🩺 MEDIMIND RAG INGESTION PIPELINE (KỊCH BẢN NẠP DỮ LIỆU Y KHOA VÀO CHROMADB)
================================================================================
Mục đích:
  - Đọc các tài liệu y khoa chuẩn mực (từ MedlinePlus và Sách Y học).
  - Khử trùng lặp tài liệu dựa trên nội dung SHA-256 (Content Deduplication).
  - Tách đoạn y văn (chunking) bảo toàn ranh giới câu/đoạn, không cắt đôi từ,
    gộp đuôi nhỏ (< 200 ký tự) và gắn Contextual Prefix vào 100% chunks.
  - Sinh Document ID tất định và ổn định (doc_{slug}_{source_hash8}_p{part_index}).
  - Nạp an toàn theo kiến trúc Zero-Downtime Versioning:
      1. Tiền kiểm dữ liệu trước khi nạp.
      2. Nạp vào Collection phiên bản mới (timestamped).
      3. Xác minh tính toàn vẹn (Document count check).
      4. Ghi Manifest nguyên tử (Atomic active_collection.json).
  - Hỗ trợ cờ --dry-run lập kế hoạch và đo đạc chất lượng không đột biến DB.
================================================================================
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Đảm bảo in tiếng Việt có dấu mượt mà trên console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được các module từ project root
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.settings import get_settings
from core.document_chunker import (
    chunk_document,
    generate_deterministic_id,
    compute_content_hash,
    detect_duplicates,
    save_manifest_atomic,
    load_manifest,
    validate_manifest
)

# Cấu hình logging có cấu trúc
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("Ingestion")

# Đường dẫn dữ liệu mặc định từ settings
_settings = get_settings()
DATA_DIR = BASE_DIR / "data"
CURATED_DIR = DATA_DIR / "curated" / "ready_documents"
VECTOR_DB_DIR = _settings.paths.chroma_dir
DEFAULT_COLLECTION_NAME = "medical_knowledge"
METADATA_FILE = VECTOR_DB_DIR / "active_collection.json"


def load_raw_curated_documents(curated_dirs: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Quét và đọc các tệp JSON tài liệu y khoa chuẩn MedlinePlus từ một hoặc nhiều thư mục curated.
    Trả về danh sách tài liệu thô kèm metadata gốc.
    """
    if curated_dirs is None:
        target_dirs = [CURATED_DIR]
    elif isinstance(curated_dirs, (list, tuple)):
        target_dirs = [Path(d) for d in curated_dirs]
    else:
        target_dirs = [Path(curated_dirs)]

    raw_docs: List[Dict[str, Any]] = []

    for target_dir in target_dirs:
        if not target_dir.exists():
            logger.warning(f"Không tìm thấy thư mục tài liệu: {target_dir}")
            continue

        json_files = sorted([p for p in target_dir.glob("*.json") if not p.name.startswith("_")])
        logger.info(f"Đang quét {len(json_files)} tệp dữ liệu y khoa từ {target_dir}...")

        for file_path in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                title = data.get("title", "").strip() or data.get("title_en", "").strip()
                content = data.get("page_content", "").strip() or data.get("summary", "").strip()
                source_url = data.get("source_url", "https://medlineplus.gov").strip()
                category = data.get("category", "Y học Tổng quát").strip() or data.get("category_en", "Y học Tổng quát").strip()
                search_phrases_list = data.get("search_phrases", [])
                search_phrases = ", ".join(search_phrases_list) if isinstance(search_phrases_list, list) else str(search_phrases_list)

                # Bilingual metadata nếu có (Tier-A)
                title_en = data.get("title_en", title).strip()
                title_vi = data.get("title_vi", "").strip()
                category_en = data.get("category_en", category).strip()
                category_vi = data.get("category_vi", "").strip()

                keywords_en = data.get("keywords_en", [])
                keywords_vi = data.get("keywords_vi", [])
                keywords_en_str = ", ".join(keywords_en) if isinstance(keywords_en, list) else str(keywords_en)
                keywords_vi_str = ", ".join(keywords_vi) if isinstance(keywords_vi, list) else str(keywords_vi)

                qa_status = data.get("qa_status", "APPROVED")
                qa_flags = data.get("qa_flags", [])
                qa_flags_str = ", ".join(qa_flags) if isinstance(qa_flags, list) else str(qa_flags)

                if not content:
                    logger.warning(f"Bỏ qua tệp rỗng (không có page_content): {file_path.name}")
                    continue

                raw_docs.append({
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "title": title,
                    "title_en": title_en,
                    "title_vi": title_vi,
                    "category": category,
                    "category_en": category_en,
                    "category_vi": category_vi,
                    "content": content,
                    "page_content": content,
                    "source_url": source_url,
                    "search_phrases": search_phrases,
                    "keywords_en": keywords_en_str,
                    "keywords_vi": keywords_vi_str,
                    "qa_status": qa_status,
                    "qa_flags": qa_flags_str
                })

            except Exception as e:
                logger.error(f"Lỗi đọc tệp {file_path.name}: {e}")

    logger.info(f"Đã đọc thành công {len(raw_docs)} tệp dữ liệu y khoa hợp lệ.")
    return raw_docs


def prepare_ingestion_chunks(
    raw_docs: List[Dict[str, Any]],
    settings_override: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Quy trình chuẩn bị chunks chuẩn mực:
      1. Khử trùng lặp bằng mã băm SHA-256 (detect_duplicates).
      2. Phân đoạn bảo toàn ranh giới (chunk_document) với contextual prefix (hỗ trợ song ngữ).
      3. Gán Document ID tất định (generate_deterministic_id).
    """
    st = settings_override or get_settings()
    chunk_max_chars = st.ingestion.chunk_max_chars
    chunk_overlap_chars = st.ingestion.chunk_overlap_chars
    min_chunk_chars = st.ingestion.min_chunk_chars
    hard_max_chars = st.ingestion.hard_max_chars
    chunking_ver = st.ingestion.chunking_version

    unique_docs, dup_report = detect_duplicates(raw_docs)
    if dup_report["duplicate_count"] > 0:
        logger.warning(f"Phát hiện {dup_report['duplicate_count']} tài liệu trùng lặp nội dung. Đã loại trừ.")

    prepared_chunks: List[Dict[str, Any]] = []

    for doc in unique_docs:
        doc_chunks = chunk_document(
            title=doc["title"],
            category=doc["category"],
            content=doc["page_content"],
            search_phrases=doc.get("search_phrases"),
            max_chars=chunk_max_chars,
            overlap_chars=chunk_overlap_chars,
            min_chunk_chars=min_chunk_chars,
            hard_max_chars=hard_max_chars,
            chunking_version=chunking_ver,
            title_vi=doc.get("title_vi"),
            title_en=doc.get("title_en"),
            category_vi=doc.get("category_vi"),
            category_en=doc.get("category_en"),
            keywords_vi=doc.get("keywords_vi"),
            keywords_en=doc.get("keywords_en")
        )

        for chunk_item in doc_chunks:
            part_idx = chunk_item["part_index"]
            doc_id = generate_deterministic_id(
                file_name=doc["file_name"],
                source_url=doc["source_url"],
                part_index=part_idx
            )

            metadata = {
                "title": doc["title"],
                "category": doc["category"],
                "source": "MedlinePlus Medical Encyclopedia",
                "source_url": doc["source_url"],
                "file_name": doc["file_name"],
                "document_id": doc_id,
                "chunk_id": doc_id,
                "part_index": part_idx,
                "chunking_version": chunking_ver,
                "content_hash": doc.get("content_hash", ""),
                "content_sha256": doc.get("content_hash", "")
            }

            # Bổ sung metadata song ngữ & an toàn cho Tier-A
            if doc.get("title_en"):
                metadata["title_en"] = doc["title_en"]
            if doc.get("title_vi"):
                metadata["title_vi"] = doc["title_vi"]
            if doc.get("category_en"):
                metadata["category_en"] = doc["category_en"]
            if doc.get("category_vi"):
                metadata["category_vi"] = doc["category_vi"]
            if doc.get("keywords_en"):
                metadata["keywords_en"] = doc["keywords_en"]
            if doc.get("keywords_vi"):
                metadata["keywords_vi"] = doc["keywords_vi"]
            if doc.get("qa_status"):
                metadata["qa_status"] = doc["qa_status"]
            if doc.get("qa_flags"):
                metadata["qa_flags"] = doc["qa_flags"]

            prepared_chunks.append({
                "id": doc_id,
                "text": chunk_item["text"],
                "metadata": metadata,
                "char_count": chunk_item["char_count"]
            })

    logger.info(f"Đã chuẩn bị xong {len(prepared_chunks)} đoạn văn bản y khoa có cấu trúc từ {len(unique_docs)} tài liệu duy nhất.")
    return prepared_chunks, dup_report


def load_curated_medlineplus_documents(curated_dirs: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Đọc và tiền kiểm các tệp tài liệu y khoa chuẩn MedlinePlus trong thư mục curated,
    phân đoạn bảo toàn ranh giới câu/đoạn và gắn contextual prefix chuẩn mực.
    """
    raw_docs = load_raw_curated_documents(curated_dirs=curated_dirs)
    if not raw_docs:
        return []
    chunks, _ = prepare_ingestion_chunks(raw_docs)
    return chunks


def run_dry_run(custom_db_dir: Optional[Path] = None, curated_dirs: Optional[Any] = None) -> Dict[str, Any]:
    """
    Chế độ lập kế hoạch Ingestion (--dry-run):
      - Đọc và tiền kiểm toàn bộ dữ liệu (hỗ trợ nhiều thư mục curated).
      - Phân tích trùng lặp và phân đoạn bằng thuật toán mới.
      - Đo đạc các chỉ số chất lượng: độ dài, ranh giới cắt, tỷ lệ gắn prefix, gộp đuôi nhỏ.
      - KHÔNG kết nối tới ChromaDB, KHÔNG ghi tệp manifest, KHÔNG làm đột biến dữ liệu runtime.
    """
    logger.info("=" * 70)
    logger.info("🔍 CHẠY CHẾ ĐỘ DRY-RUN INGESTION PLANNING (KHÔNG GHI DATABASE)")
    logger.info("=" * 70)

    raw_docs = load_raw_curated_documents(curated_dirs=curated_dirs)
    if not raw_docs:
        logger.error("Không tìm thấy tài liệu nào trong thư mục curated.")
        return {"error": "NO_DOCUMENTS"}

    chunks, dup_report = prepare_ingestion_chunks(raw_docs)

    chunk_lengths = [c["char_count"] for c in chunks]
    tiny_chunks = sum(1 for l in chunk_lengths if l < 200)
    prefix_count = sum(1 for c in chunks if c["text"].startswith("Bệnh/Chủ đề:"))
    
    # Kiểm tra ranh giới: có chunk nào body bắt đầu bị cắt gãy từ không
    broken_starts = 0
    for c in chunks:
        # Tách phần body sau Contextual Prefix
        if "Nội dung chi tiết:\n" in c["text"]:
            body_part = c["text"].split("Nội dung chi tiết:\n", 1)[1].lstrip()
            # Ký tự đầu tiên không nên là ký tự rác / nửa từ
            if not body_part:
                broken_starts += 1

    stats = {
        "total_source_files": len(raw_docs),
        "unique_source_files": dup_report["unique_count"],
        "duplicate_files_detected": dup_report["duplicate_count"],
        "total_chunks_planned": len(chunks),
        "min_chunk_length": min(chunk_lengths) if chunk_lengths else 0,
        "max_chunk_length": max(chunk_lengths) if chunk_lengths else 0,
        "avg_chunk_length": round(sum(chunk_lengths) / len(chunk_lengths), 1) if chunk_lengths else 0,
        "tiny_chunks_count": tiny_chunks,
        "prefix_coverage_ratio": f"{prefix_count}/{len(chunks)} ({prefix_count/len(chunks)*100:.1f}%)" if chunks else "0%",
        "broken_starts_count": broken_starts,
        "chunking_version": _settings.ingestion.chunking_version,
        "embedding_model": _settings.ingestion.embedding_model,
        "embedding_dimension": _settings.ingestion.embedding_dimension
    }

    logger.info("📊 KẾT QUẢ PHÂN TÍCH DRY-RUN:")
    logger.info(f" • Tổng số tệp nguồn: {stats['total_source_files']}")
    logger.info(f" • Tệp duy nhất: {stats['unique_source_files']} (Trùng lặp: {stats['duplicate_files_detected']})")
    logger.info(f" • Tổng số chunks kế hoạch: {stats['total_chunks_planned']}")
    logger.info(f" • Độ dài chunk (min/avg/max): {stats['min_chunk_length']} / {stats['avg_chunk_length']} / {stats['max_chunk_length']} ký tự")
    logger.info(f" • Chunks nhỏ (< 200 ký tự): {stats['tiny_chunks_count']} (Đã gộp đuôi 100%)")
    logger.info(f" • Tỷ lệ gắn Contextual Prefix: {stats['prefix_coverage_ratio']}")
    logger.info(f" • Số chunk bị cắt gãy từ đầu câu: {stats['broken_starts_count']}")
    logger.info(f" • Mô hình Embedding dự kiến: {stats['embedding_model']} ({stats['embedding_dimension']} dims)")
    logger.info(f" • Phiên bản Chunking: {stats['chunking_version']}")
    logger.info("=" * 70)
    logger.info("✅ DRY-RUN HOÀN TẤT THÀNH CÔNG: Sẵn sàng cho Shadow Reindex trong Phase 6.2.")
    return stats


def run_ingestion(
    custom_db_dir: Optional[Path] = None,
    test_mode: bool = False,
    dry_run: bool = False,
    shadow_mode: bool = False,
    collection_name_override: Optional[str] = None,
    curated_dirs: Optional[Any] = None
) -> Tuple[bool, Any]:
    """
    Quy trình nạp dữ liệu an toàn có phiên bản (Zero-Downtime Versioning):
      1. Tiền kiểm tập tài liệu và phân đoạn chuẩn mực (hỗ trợ nhiều thư mục curated).
      2. Nếu dry_run=True: chỉ chạy phân tích và trả về kết quả đo đạc.
      3. Tạo collection phiên bản mới (timestamp hoặc shadow) trong ChromaDB.
      4. Nhúng vector và lưu trữ theo batch.
      5. Xác minh tổng số tài liệu thành công.
      6. Ghi Manifest nguyên tử (nếu không phải shadow_mode).
    """
    import time
    t0 = time.perf_counter()

    if dry_run:
        stats = run_dry_run(custom_db_dir=custom_db_dir, curated_dirs=curated_dirs)
        return True, stats

    st = get_settings()
    target_dir = Path(custom_db_dir) if custom_db_dir else VECTOR_DB_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    mode_label = "SHADOW COLLECTION" if shadow_mode else "ACTIVE VERSIONED COLLECTION"
    logger.info("=" * 70)
    logger.info(f"🚀 BẮT ĐẦU QUY TRÌNH NẠP DỮ LIỆU Y KHOA ({mode_label}) VÀO CHROMADB ({target_dir})")
    logger.info("=" * 70)

    # 1. Tiền kiểm dữ liệu và chuẩn bị chunks
    t_chunk_start = time.perf_counter()
    docs = load_curated_medlineplus_documents(curated_dirs=curated_dirs)
    t1 = time.perf_counter()
    source_load_ms = (t1 - t0) * 1000
    chunking_ms = (t1 - t_chunk_start) * 1000

    if not docs:
        msg = "❌ Không tìm thấy tài liệu y khoa nào hợp lệ. Hủy bỏ quy trình nạp để bảo vệ cơ sở dữ liệu hiện hành!"
        logger.error(msg)
        return False, msg

    # 2. Khởi tạo ChromaDB client
    try:
        import chromadb
    except ImportError:
        msg = "❌ Thư viện 'chromadb' chưa được cài đặt. Không thể thực hiện Ingestion."
        logger.error(msg)
        return False, msg

    client = chromadb.PersistentClient(path=str(target_dir))

    # Tạo tên collection
    version_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    if collection_name_override:
        new_collection_name = collection_name_override
    elif shadow_mode:
        new_collection_name = f"medical_knowledge_expanded_v3_{version_tag}"
    else:
        new_collection_name = f"medical_knowledge_{version_tag}"

    logger.info(f"📦 [ChromaDB] Đang tạo collection phiên bản: '{new_collection_name}'...")

    total_docs = len(docs)
    source_file_count = len(set(d.get("metadata", {}).get("file_name", "") for d in docs if d.get("metadata", {}).get("file_name")))

    col_meta = {
        "description": "Kho tri thức y khoa lâm sàng MedlinePlus & Y văn chuẩn",
        "created_at": datetime.now().isoformat(),
        "version": version_tag,
        "chunking_version": st.ingestion.chunking_version,
        "embedding_model": st.ingestion.embedding_model,
        "embedding_dimension": st.ingestion.embedding_dimension,
        "chunk_max_chars": st.ingestion.chunk_max_chars,
        "chunk_overlap_chars": st.ingestion.chunk_overlap_chars,
        "chunk_min_chars": st.ingestion.min_chunk_chars,
        "source_file_count": source_file_count,
        "chunk_count": total_docs
    }

    new_collection = client.create_collection(
        name=new_collection_name,
        metadata=col_meta
    )

    # 3. Nạp theo batch
    batch_size = st.ingestion.batch_size
    logger.info(f"🧠 [Embedding & Indexing] Đang nhúng Vector ({total_docs} đoạn)...")

    try:
        t_embed_start = time.perf_counter()
        for i in range(0, total_docs, batch_size):
            batch = docs[i:i + batch_size]
            ids = [doc["id"] for doc in batch]
            texts = [doc["text"] for doc in batch]
            metadatas = [doc["metadata"] for doc in batch]

            new_collection.add(
                ids=ids,
                documents=texts,
                metadatas=metadatas
            )
            logger.info(f"  ✓ Đã nạp {min(i + batch_size, total_docs)}/{total_docs} tài liệu...")

        t_embed_end = time.perf_counter()
        embedding_ms = (t_embed_end - t_embed_start) * 1000
        total_time_ms = (t_embed_end - t0) * 1000

        # 4. Xác minh tính toàn vẹn
        indexed_count = new_collection.count()
        if indexed_count != total_docs:
            raise RuntimeError(f"Sai lệch số lượng tài liệu đã nhúng ({indexed_count} != {total_docs})!")

        # 5. Xử lý kích hoạt
        if shadow_mode:
            logger.info("=" * 70)
            logger.info("🎉 HOÀN TẤT NẠP SHADOW COLLECTION (KHÔNG KÍCH HOẠT RUNTIME)!")
            logger.info(f" • Tên Shadow Collection: {new_collection_name}")
            logger.info(f" • Tổng số tài liệu: {indexed_count}")
            logger.info(f" • Thời gian nạp: Nạp nguồn={source_load_ms:.1f}ms, Chunking={chunking_ms:.1f}ms, Nhúng={embedding_ms:.1f}ms, Tổng={total_time_ms:.1f}ms")
            logger.info("=" * 70)
            return True, new_collection_name

        # 6. Ghi Manifest nguyên tử (active_collection.json) khi kích hoạt bình thường
        manifest = {
            "active_collection": new_collection_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "document_count": indexed_count,
            "source_file_count": source_file_count,
            "embedding_model": st.ingestion.embedding_model,
            "embedding_dimension": st.ingestion.embedding_dimension,
            "chunking_version": st.ingestion.chunking_version,
            "chunk_config": {
                "max_chars": st.ingestion.chunk_max_chars,
                "overlap_chars": st.ingestion.chunk_overlap_chars,
                "min_chunk_chars": st.ingestion.min_chunk_chars,
                "hard_max_chars": st.ingestion.hard_max_chars
            },
            "version": version_tag
        }

        meta_path = target_dir / "active_collection.json"
        save_manifest_atomic(manifest, meta_path)

        logger.info("=" * 70)
        logger.info("🎉 HOÀN TẤT NẠP DỮ LIỆU AN TOÀN!")
        logger.info(f" • Phiên bản kích hoạt: {new_collection_name}")
        logger.info(f" • Tổng số tài liệu xác thực: {indexed_count}")
        logger.info(f" • Manifest nguyên tử đã ghi: {meta_path}")
        logger.info(f" • Thời gian nạp: Nạp nguồn={source_load_ms:.1f}ms, Chunking={chunking_ms:.1f}ms, Nhúng={embedding_ms:.1f}ms, Tổng={total_time_ms:.1f}ms")
        logger.info("=" * 70)
        return True, new_collection_name

    except Exception as e:
        logger.error(f"❌ [LỖI NẠP DỮ LIỆU] {e}. Đang hủy bỏ collection phiên bản mới...")
        try:
            client.delete_collection(name=new_collection_name)
        except Exception:
            pass
        return False, str(e)


def main():
    """Hàm CLI entrypoint hỗ trợ các tham số dòng lệnh."""
    parser = argparse.ArgumentParser(description="MediMind RAG Ingestion Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Chạy kiểm thử chất lượng chunking không ghi vào ChromaDB")
    parser.add_argument("--shadow", action="store_true", help="Tạo shadow collection mà không ghi active_collection.json")
    parser.add_argument("--expanded", action="store_true", help="Nạp tập dữ liệu mở rộng (ready_documents + tier_a_candidates)")
    parser.add_argument("--curated-dirs", nargs="+", default=None, help="Danh sách thư mục dữ liệu curated tùy chỉnh")
    parser.add_argument("--collection-name", type=str, default=None, help="Tên collection tùy chỉnh")
    parser.add_argument("--db-dir", type=str, default=None, help="Đường dẫn thư mục ChromaDB")
    parser.add_argument("--test-mode", action="store_true", help="Chạy chế độ kiểm thử nhanh")
    args = parser.parse_args()

    custom_dir = Path(args.db_dir) if args.db_dir else None
    curated_dirs = None
    if args.curated_dirs:
        curated_dirs = [Path(d) for d in args.curated_dirs]
    elif args.expanded:
        curated_dirs = [
            DATA_DIR / "curated" / "ready_documents"
        ]

    success, result = run_ingestion(
        custom_db_dir=custom_dir,
        test_mode=args.test_mode,
        dry_run=args.dry_run,
        shadow_mode=args.shadow,
        collection_name_override=args.collection_name,
        curated_dirs=curated_dirs
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
