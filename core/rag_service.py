"""
================================================================================
🩺 MEDIMIND RAG RETRIEVAL SERVICE (DỊCH VỤ TRUY XUẤT TRI THỨC Y KHOA TỪ CHROMADB)
================================================================================
Mục đích:
  - Kết nối tới Cơ sở dữ liệu Vector ChromaDB tại ./medical_vectordb.
  - Nhận câu hỏi/triệu chứng của người dân và tìm kiếm Top các đoạn y văn khớp nhất.
  - Hỗ trợ chuyển đổi từ khóa y khoa Việt - Anh (Query Translation) để tìm chính xác tài liệu gốc.
  - Trích xuất siêu dữ liệu (Metadata) chính xác: Tên tài liệu, Chuyên khoa, URL nguồn.
  - Minh bạch khoảng cách khoảng cách vector (L2 distance), không tự gán xác suất 1 - distance.
================================================================================
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb

# Đường dẫn tới thư mục lưu trữ ChromaDB
BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_DB_DIR = BASE_DIR / "medical_vectordb"
DEFAULT_COLLECTION_NAME = "medical_knowledge"
METADATA_FILE = VECTOR_DB_DIR / "active_collection.json"

# Tiêu chí khoảng cách chấp nhận tài liệu (khoảng cách Euclidean L2 tối đa)
DEFAULT_ACCEPTANCE_THRESHOLD = float(os.getenv("RAG_ACCEPTANCE_THRESHOLD", "1.35"))

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

    def __init__(self, db_dir: Optional[Path] = None, acceptance_threshold: float = DEFAULT_ACCEPTANCE_THRESHOLD):
        self.db_dir = Path(db_dir) if db_dir else VECTOR_DB_DIR
        self.acceptance_threshold = acceptance_threshold
        self.client = None
        self.collection = None
        self.collection_name = self._resolve_active_collection_name()
        self._init_db()

    def _resolve_active_collection_name(self) -> str:
        """Đọc tên collection đang hoạt động từ metadata để hỗ trợ zero-downtime versioning."""
        meta_file = self.db_dir / "active_collection.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("active_collection", DEFAULT_COLLECTION_NAME)
            except Exception:
                pass
        return DEFAULT_COLLECTION_NAME

    def _init_db(self):
        """Khởi tạo kết nối tới kho dữ liệu Vector ChromaDB."""
        try:
            if self.db_dir.exists():
                self.client = chromadb.PersistentClient(path=str(self.db_dir))
                try:
                    self.collection = self.client.get_collection(name=self.collection_name)
                    print(f"✅ [RAG Service] Đã kết nối ChromaDB (Collection: '{self.collection_name}', {self.collection.count()} tài liệu).")
                except Exception:
                    # Fallback to default collection if versioned collection is not found
                    try:
                        self.collection = self.client.get_collection(name=DEFAULT_COLLECTION_NAME)
                        print(f"✅ [RAG Service] Fallback sang collection mặc định '{DEFAULT_COLLECTION_NAME}' ({self.collection.count()} tài liệu).")
                    except Exception:
                        self.collection = None
            else:
                self.collection = None
        except Exception as e:
            print(f"⚠️ [RAG Service] Lỗi kết nối ChromaDB: {e}")
            self.collection = None

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
        - Ghi rõ distance_metric ("l2") và giá trị khoảng cách thô thực tế.
        - Áp dụng ngưỡng chấp nhận tài liệu (acceptance_threshold).
        """
        if not self.is_available():
            return []

        try:
            search_query = self.expand_query(user_query)

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
                    dist_float = float(dist) if dist is not None else 1.0
                    is_accepted = (dist_float <= self.acceptance_threshold)

                    # Chỉ nạp tài liệu đạt tiêu chuẩn ngưỡng chấp nhận để tránh rác
                    if is_accepted:
                        retrieved_docs.append({
                            "content": doc_text,
                            "title": meta.get("title", "Tài liệu Y khoa"),
                            "category": meta.get("category", "Y học Tổng quát"),
                            "source": meta.get("source", "MedlinePlus Medical Encyclopedia"),
                            "source_url": meta.get("source_url", "https://medlineplus.gov"),
                            "distance": round(dist_float, 4),
                            "distance_metric": "l2",
                            "accepted": True
                        })

            return retrieved_docs

        except Exception as e:
            print(f"⚠️ [RAG Service] Lỗi khi truy vấn tri thức y khoa: {e}")
            return []


# Khởi tạo thể hiện Singleton dùng chung toàn ứng dụng
medical_rag_service = MedicalRAGService()
