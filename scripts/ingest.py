"""
================================================================================
🩺 MEDIMIND RAG INGESTION PIPELINE (KỊCH BẢN NẠP DỮ LIỆU Y KHOA VÀO CHROMADB)
================================================================================
Mục đích:
  - Đọc các tài liệu y khoa chuẩn mực (từ MedlinePlus và Sách Y học).
  - Tách nhỏ thành từng đoạn (chunking) kèm siêu dữ liệu (metadata: tên bệnh, nguồn, link).
  - Nạp an toàn theo kiến trúc Zero-Downtime Versioning:
      1. Tiền kiểm dữ liệu trước khi nạp.
      2. Nạp vào Collection phiên bản mới (timestamped).
      3. Xác minh tính toàn vẹn (Document count check).
      4. Chuyển con trỏ active collection sang bản mới; bảo toàn bản cũ để rollback.
================================================================================
"""

import os
import sys
import json
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Đảm bảo in tiếng Việt có dấu mượt mà trên console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import chromadb
from chromadb.config import Settings

# Đường dẫn lưu trữ thư mục dữ liệu và ChromaDB
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CURATED_DIR = DATA_DIR / "curated" / "ready_documents"
VECTOR_DB_DIR = BASE_DIR / "medical_vectordb"

DEFAULT_COLLECTION_NAME = "medical_knowledge"
METADATA_FILE = VECTOR_DB_DIR / "active_collection.json"


def load_curated_medlineplus_documents() -> List[Dict[str, Any]]:
    """
    Đọc và tiền kiểm các tệp tài liệu y khoa chuẩn MedlinePlus trong thư mục curated.
    """
    documents = []
    if not CURATED_DIR.exists():
        print(f"⚠️ [Cảnh báo] Không tìm thấy thư mục: {CURATED_DIR}")
        return documents

    json_files = sorted(list(CURATED_DIR.glob("*.json")))
    print(f"📄 [Nạp tài liệu] Đang quét {len(json_files)} tệp dữ liệu y khoa chuẩn từ MedlinePlus...")

    doc_counter = 0

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            title = data.get("title", "").strip()
            content = data.get("page_content", "").strip()
            source_url = data.get("source_url", "https://medlineplus.gov")
            category = data.get("category", "Y học Tổng quát")
            search_phrases = ", ".join(data.get("search_phrases", []))

            if not content:
                continue

            full_text = f"Bệnh/Chủ đề: {title}\nChuyên khoa: {category}\nTừ khóa liên quan: {search_phrases}\n\nNội dung chi tiết:\n{content}"

            max_chunk_length = 2000
            if len(full_text) > max_chunk_length:
                chunk_index = 0
                for i in range(0, len(full_text), max_chunk_length - 200):
                    chunk = full_text[i:i + max_chunk_length]
                    doc_counter += 1
                    doc_id = f"doc_{doc_counter}_{file_path.stem[:30]}_part{chunk_index}"
                    documents.append({
                        "id": doc_id,
                        "text": chunk,
                        "metadata": {
                            "title": title,
                            "category": category,
                            "source": "MedlinePlus Medical Encyclopedia",
                            "source_url": source_url,
                            "file_name": file_path.name
                        }
                    })
                    chunk_index += 1
            else:
                doc_counter += 1
                doc_id = f"doc_{doc_counter}_{file_path.stem[:30]}"
                documents.append({
                    "id": doc_id,
                    "text": full_text,
                    "metadata": {
                        "title": title,
                        "category": category,
                        "source": "MedlinePlus Medical Encyclopedia",
                        "source_url": source_url,
                        "file_name": file_path.name
                    }
                })

        except Exception as e:
            print(f"⚠️ Lỗi đọc tệp {file_path.name}: {e}")

    print(f"✅ [Nạp tài liệu] Đã chuẩn bị xong {len(documents)} đoạn văn bản y khoa có cấu trúc!")
    return documents


def run_ingestion(custom_db_dir: Path = None, test_mode: bool = False) -> Tuple[bool, str]:
    """
    Quy trình nạp dữ liệu an toàn có phiên bản:
      1. Tiền kiểm tập tài liệu
      2. Tạo collection phiên bản mới (timestamp)
      3. Nhúng vector và lưu trữ
      4. Xác minh tổng số tài liệu thành công
      5. Cập nhật active collection metadata
    """
    target_dir = custom_db_dir or VECTOR_DB_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print(f"🚀 BẮT ĐẦU QUY TRÌNH NẠP DỮ LIỆU Y KHOA VÀO CHROMADB ({target_dir})")
    print("=" * 70)

    # 1. Tiền kiểm dữ liệu trước
    docs = load_curated_medlineplus_documents()
    if not docs:
        msg = "❌ Không tìm thấy tài liệu y khoa nào hợp lệ. Hủy bỏ quy trình nạp để bảo vệ cơ sở dữ liệu hiện hành!"
        print(msg)
        return False, msg

    # 2. Khởi tạo ChromaDB client
    client = chromadb.PersistentClient(path=str(target_dir))

    # Tạo collection phiên bản mới
    version_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_collection_name = f"medical_knowledge_{version_tag}"
    print(f"📦 [ChromaDB] Đang tạo collection phiên bản mới: '{new_collection_name}'...")

    new_collection = client.create_collection(
        name=new_collection_name,
        metadata={
            "description": "Kho tri thức y khoa lâm sàng MedlinePlus & Y văn chuẩn",
            "created_at": datetime.now().isoformat(),
            "version": version_tag
        }
    )

    # 3. Nạp theo batch
    batch_size = 50
    total_docs = len(docs)
    print(f"🧠 [Embedding & Indexing] Đang nhúng Vector ({total_docs} đoạn)...")

    try:
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
            print(f"  ✓ Đã nạp {min(i + batch_size, total_docs)}/{total_docs} tài liệu...")

        # 4. Xác minh tính toàn vẹn
        indexed_count = new_collection.count()
        if indexed_count != total_docs:
            raise RuntimeError(f"Sai lệch số lượng tài liệu đã nhúng ({indexed_count} != {total_docs})!")

        # 5. Đồng bộ vào collection mặc định và cập nhật active metadata
        active_meta = {
            "active_collection": new_collection_name,
            "updated_at": datetime.now().isoformat(),
            "document_count": indexed_count,
            "version": version_tag
        }

        meta_path = target_dir / "active_collection.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(active_meta, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 70)
        print(f"🎉 HOÀN TẤT NẠP DỮ LIỆU AN TOÀN!")
        print(f" • Phiên bản kích hoạt: {new_collection_name}")
        print(f" • Tổng số tài liệu xác thực: {indexed_count}")
        print("=" * 70 + "\n")
        return True, new_collection_name

    except Exception as e:
        print(f"❌ [LỖI NẠP DỮ LIỆU] {e}. Đang hủy bỏ collection phiên bản mới...")
        try:
            client.delete_collection(name=new_collection_name)
        except Exception:
            pass
        return False, str(e)


if __name__ == "__main__":
    run_ingestion()
