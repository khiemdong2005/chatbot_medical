"""
================================================================================
🩺 MEDIMIND RAG INGESTION PIPELINE (KỊCH BẢN NẠP DỮ LIỆU Y KHOA VÀO CHROMADB)
================================================================================
Mục đích:
  - Đọc các tài liệu y khoa chuẩn mực (từ MedlinePlus và Sách Y học).
  - Tách nhỏ thành từng đoạn (chunking) kèm siêu dữ liệu (metadata: tên bệnh, nguồn, link).
  - Nhúng vector và lưu trữ vào Cơ sở Dữ liệu Vector ChromaDB đặt tại thư mục: ./medical_vectordb.
  - Chạy 1 lần duy nhất để tạo cơ sở tri thức cho Chatbot tra cứu.
================================================================================
"""

import os
import sys
import json
import glob
from pathlib import Path
from typing import List, Dict, Any

# Đảm bảo in tiếng Việt có dấu mượt mà trên console Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import chromadb
from chromadb.config import Settings

# Đường dẫn lưu trữ thư mục dữ liệu và ChromaDB
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CURATED_DIR = DATA_DIR / "curated" / "ready_documents"
VECTOR_DB_DIR = BASE_DIR / "medical_vectordb"

COLLECTION_NAME = "medical_knowledge"


def init_chroma_client():
    """
    Khởi tạo Client kết nối ChromaDB lưu trữ cục bộ (Persistent Storage).
    Dữ liệu sẽ được lưu vĩnh viễn trên máy tại thư mục ./medical_vectordb
    """
    print(f"📦 [ChromaDB] Đang kết nối kho dữ liệu Vector tại: {VECTOR_DB_DIR}")
    client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
    
    # Lấy hoặc tạo mới collection (nếu đã tồn tại thì xóa đi tạo lại để cập nhật mới nhất)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"🔄 [ChromaDB] Đã dọn dẹp collection cũ '{COLLECTION_NAME}'.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Kho tri thức y khoa lâm sàng MedlinePlus & Y văn chuẩn"}
    )
    return client, collection


def load_curated_medlineplus_documents() -> List[Dict[str, Any]]:
    """
    Đọc 241 tệp tài liệu y khoa chuẩn MedlinePlus đã được cấu trúc hóa sẵn trong thư mục curated.
    Mỗi tệp chứa: Tiêu đề bệnh, mô tả, triệu chứng, hướng dẫn điều trị, link nguồn.
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

            # Đoạn văn bản kết hợp hoàn chỉnh để tạo embedding
            full_text = f"Bệnh/Chủ đề: {title}\nChuyên khoa: {category}\nTừ khóa liên quan: {search_phrases}\n\nNội dung chi tiết:\n{content}"

            # Cắt ngắn nếu nội dung quá dài (mỗi chunk tối đa 2000 ký tự để tìm kiếm chính xác)
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


def run_ingestion():
    """
    Hàm thực thi chính: Nạp toàn bộ dữ liệu vào ChromaDB.
    """
    print("\n" + "=" * 70)
    print("🚀 BẮT ĐẦU QUY TRÌNH NẠP DỮ LIỆU Y KHOA VÀO CHROMADB VECTOR STORE")
    print("=" * 70)

    # 1. Khởi tạo ChromaDB
    client, collection = init_chroma_client()

    # 2. Đọc tài liệu
    docs = load_curated_medlineplus_documents()
    if not docs:
        print("❌ Không có tài liệu nào để nạp. Vui lòng kiểm tra lại thư mục data!")
        return

    # 3. Nạp theo từng đợt (batch) để tối ưu bộ nhớ
    batch_size = 50
    total_docs = len(docs)
    print(f"\n🧠 [Embedding & Indexing] Đang nhúng Vector và lưu vào ChromaDB ({total_docs} đoạn)...")

    for i in range(0, total_docs, batch_size):
        batch = docs[i:i + batch_size]
        ids = [doc["id"] for doc in batch]
        texts = [doc["text"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch]

        # ChromaDB tự động sử dụng mô hình embedding mặc định (nhanh, nhẹ, miễn phí)
        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )
        print(f"  ✓ Đã nạp {min(i + batch_size, total_docs)}/{total_docs} tài liệu...")

    print("\n" + "=" * 70)
    print(f"🎉 HOÀN TẤT NẠP DỮ LIỆU! Tổng cộng: {collection.count()} đoạn y văn đã sẵn sàng.")
    print(f"📁 Vị trí lưu trữ cơ sở dữ liệu: {VECTOR_DB_DIR}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_ingestion()
