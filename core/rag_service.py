"""
================================================================================
🩺 MEDIMIND RAG RETRIEVAL SERVICE (DỊCH VỤ TRUY XUẤT TRI THỨC Y KHOA TỪ CHROMADB)
================================================================================
Mục đích:
  - Kết nối tới Cơ sở dữ liệu Vector ChromaDB tại ./medical_vectordb.
  - Nhận câu hỏi/triệu chứng của người dân và tìm kiếm Top các đoạn y văn khớp nhất.
  - Hỗ trợ chuyển đổi từ khóa y khoa Việt - Anh (Query Translation) để tìm chính xác tài liệu gốc.
  - Trích xuất siêu dữ liệu (Metadata) chính xác: Tên tài liệu, Chuyên khoa, URL nguồn.
================================================================================
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb

# Đường dẫn tới thư mục lưu trữ ChromaDB
BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_DB_DIR = BASE_DIR / "medical_vectordb"
COLLECTION_NAME = "medical_knowledge"

# Từ điển ánh xạ triệu chứng Việt - Anh phổ biến để hỗ trợ tìm kiếm chéo ngôn ngữ chuẩn xác
VIETNAMESE_TO_ENGLISH_KEYWORDS = {
    "sốt": "fever pyrexia temperature",
    "đau họng": "sore throat pharyngitis tonsillitis",
    "rát họng": "sore throat irritation",
    "ho": "cough bronchitis",
    "sổ mũi": "runny nose congestion rhinitis",
    "nghẹt mũi": "nasal congestion blocked nose",
    "đau đầu": "headache migraine",
    "chóng mặt": "dizziness vertigo",
    "đau bụng": "abdominal pain stomach ache gastritis",
    "tiêu chảy": "diarrhea gastroenteritis",
    "buồn nôn": "nausea vomiting",
    "đau ngực": "chest pain angina",
    "khó thở": "shortness of breath dyspnea asthma",
    "phát ban": "skin rash dermatitis hives",
    "dị ứng": "allergy allergic reaction",
    "đường huyết": "blood glucose diabetes hyperglycemia",
    "tiểu đường": "diabetes mellitus",
    "huyết áp": "blood pressure hypertension",
    "men gan": "liver enzymes hepatitis",
    "mỡ máu": "cholesterol lipid disorder"
}


class MedicalRAGService:
    """
    Dịch vụ quản lý truy xuất tri thức y khoa từ ChromaDB.
    """

    def __init__(self):
        self.client = None
        self.collection = None
        self._init_db()

    def _init_db(self):
        """Khởi tạo kết nối tới kho dữ liệu Vector ChromaDB."""
        try:
            if VECTOR_DB_DIR.exists():
                self.client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
                self.collection = self.client.get_collection(name=COLLECTION_NAME)
                print(f"✅ [RAG Service] Đã kết nối thành công ChromaDB ({self.collection.count()} tài liệu y khoa).")
            else:
                print(f"⚠️ [RAG Service] Chưa tìm thấy kho dữ liệu tại: {VECTOR_DB_DIR}. Hãy chạy python ingest.py!")
        except Exception as e:
            print(f"⚠️ [RAG Service] Lỗi kết nối ChromaDB: {e}")

    def is_available(self) -> bool:
        """Kiểm tra xem hệ thống RAG đã sẵn sàng hoạt động chưa."""
        return self.collection is not None and self.collection.count() > 0

    def expand_query(self, query: str) -> str:
        """
        Mở rộng từ khóa truy vấn: Kết hợp câu hỏi tiếng Việt của người bệnh
        với các thuật ngữ y khoa tiếng Anh tương ứng để nâng cao độ chính xác khi tìm trong sách.
        """
        query_lower = query.lower()
        matched_en_terms = []

        for vi_term, en_terms in VIETNAMESE_TO_ENGLISH_KEYWORDS.items():
            if vi_term in query_lower:
                matched_en_terms.append(en_terms)

        if matched_en_terms:
            expanded = f"{query} {' '.join(matched_en_terms)}"
            return expanded
        return query

    def retrieve_context(self, user_query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Tìm kiếm các đoạn tài liệu y khoa phù hợp nhất với câu hỏi của người dùng.
        
        Args:
            user_query (str): Câu hỏi hoặc mô tả triệu chứng của người dân.
            top_k (int): Số lượng đoạn trích y văn cần lấy (mặc định 2).

        Returns:
            List[Dict]: Danh sách các đoạn trích gồm nội dung, tên tài liệu, nguồn và URL.
        """
        if not self.is_available():
            return []

        try:
            # 1. Mở rộng từ khóa song ngữ
            search_query = self.expand_query(user_query)

            # 2. Truy vấn tương đồng Vector trong ChromaDB
            results = self.collection.query(
                query_texts=[search_query],
                n_results=top_k
            )

            retrieved_docs = []
            if results and results.get("documents") and len(results["documents"][0]) > 0:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

                for doc_text, meta, dist in zip(docs, metas, distances):
                    retrieved_docs.append({
                        "content": doc_text,
                        "title": meta.get("title", "Tài liệu Y khoa"),
                        "category": meta.get("category", "Y học Tổng quát"),
                        "source": meta.get("source", "MedlinePlus"),
                        "source_url": meta.get("source_url", "https://medlineplus.gov"),
                        "relevance_score": round(1.0 - float(dist), 2) if dist is not None else 0.85
                    })

            return retrieved_docs

        except Exception as e:
            print(f"⚠️ [RAG Service] Lỗi khi truy vấn tri thức y khoa: {e}")
            return []


# Khởi tạo thể hiện Singleton dùng chung toàn ứng dụng
medical_rag_service = MedicalRAGService()
