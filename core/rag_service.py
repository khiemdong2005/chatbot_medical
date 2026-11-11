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
import math
import re
import unicodedata
from collections import Counter
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import chromadb
except ImportError:
    chromadb = None

# Đường dẫn tới thư mục lưu trữ ChromaDB
BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_DB_DIR = BASE_DIR / "medical_vectordb"
DEFAULT_COLLECTION_NAME = "medical_knowledge"
METADATA_FILE = VECTOR_DB_DIR / "active_collection.json"

# Tiêu chí khoảng cách chấp nhận tài liệu (khoảng cách Euclidean L2 tối đa)
DEFAULT_ACCEPTANCE_THRESHOLD = float(os.getenv("RAG_ACCEPTANCE_THRESHOLD", "1.35"))
logger = logging.getLogger("MedicalRAGService")

# Từ điển ánh xạ triệu chứng Việt - Anh phổ biến để hỗ trợ tìm kiếm chéo ngôn ngữ chuẩn xác
VIETNAMESE_TO_ENGLISH_KEYWORDS = {
    "chấn thủy": "abdominal pain epigastric",
    "chấn thuỷ": "abdominal pain epigastric",
    "lan ra sau lưng": "radiating to back",
    "nhói": "sharp pain",
    "sốt": "fever pyrexia temperature",
    "đau họng": "sore throat pharyngitis tonsillitis",
    "rát họng": "sore throat irritation",
    "ho khan": "dry cough",
    "ho": "cough",
    "sổ mũi": "runny nose congestion rhinitis",
    "nghẹt mũi": "nasal congestion blocked nose",
    "đau đầu": "headache migraine",
    "chóng mặt": "dizziness vertigo",
    "đau bụng": "abdominal pain stomach ache",
    "tiêu chảy": "diarrhea gastroenteritis",
    "buồn nôn": "nausea vomiting",
    "đau ngực": "chest pain",
    "khó thở": "shortness of breath dyspnea",
    "phát ban": "skin rash dermatitis hives",
    "dị ứng": "allergy allergic reaction",
    "đường huyết": "blood glucose",
    "tiểu đường": "diabetes mellitus",
    "huyết áp": "blood pressure",
    "men gan": "liver enzymes hepatitis",
    "mỡ máu": "cholesterol lipid disorder"
}


def search_tokens(text):
    folded = unicodedata.normalize("NFKD", text.lower().replace("đ", "d"))
    return re.findall(r"[a-z0-9]+", "".join(c for c in folded if not unicodedata.combining(c)))


class MedicalRAGService:
    """
    Dịch vụ quản lý truy xuất tri thức y khoa từ ChromaDB.
    """

    def __init__(self, db_dir: Optional[Path] = None, acceptance_threshold: float = DEFAULT_ACCEPTANCE_THRESHOLD,
                 vector_search_enabled: Optional[bool] = None):
        self.db_dir = Path(db_dir) if db_dir else VECTOR_DB_DIR
        self.acceptance_threshold = acceptance_threshold
        # Querying query_texts can lazily download an embedding model. Keep the
        # default request path entirely local; vectors require operator opt-in.
        self.vector_search_enabled = (os.getenv("RAG_VECTOR_SEARCH_ENABLED", "").lower() in ("1", "true", "yes")
                                      if vector_search_enabled is None else vector_search_enabled is True)
        self._lexical_index = None
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
        if chromadb is None:
            print("⚠️ [RAG Service] Thư viện 'chromadb' chưa được cài đặt. RAG sẽ tạm thời chuyển sang chế độ dự phòng (fallback).")
            self.collection = None
            return
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
        try:
            return self.collection is not None and self.collection.count() > 0
        except Exception as error:
            logger.warning("Reference collection unavailable (%s).", type(error).__name__)
            return False

    def expand_query(self, query: str) -> str:
        """
        Mở rộng từ khóa truy vấn: Kết hợp câu hỏi tiếng Việt của người bệnh
        với các thuật ngữ y khoa tiếng Anh tương ứng để nâng cao độ chính xác khi tìm trong sách.
        """
        query_lower = " " + " ".join(search_tokens(query)) + " "
        matched_en_terms = []

        for vi_term, en_terms in VIETNAMESE_TO_ENGLISH_KEYWORDS.items():
            if " " + " ".join(search_tokens(vi_term)) + " " in query_lower:
                if en_terms not in matched_en_terms:
                    matched_en_terms.append(en_terms)

        if matched_en_terms:
            expanded = f"{query} {' '.join(matched_en_terms)}"
            return expanded
        return query

    def _bm25_matches(self, query, limit):
        key = (self.collection_name, self.collection.count())
        if not self._lexical_index or self._lexical_index[0] != key:
            corpus = self.collection.get(include=["documents", "metadatas"])
            documents, metadata = corpus.get("documents") or [], corpus.get("metadatas") or []
            rows = [(doc, metadata[index] if index < len(metadata) and isinstance(metadata[index], dict) else {})
                    for index, doc in enumerate(documents) if isinstance(doc, str) and doc.strip()]
            counts = [Counter(search_tokens((meta or {}).get("title", "") + " " + doc)) for doc, meta in rows]
            df = Counter(term for row in counts for term in row)
            lengths = [sum(row.values()) for row in counts]
            self._lexical_index = key, rows, counts, df, lengths
        _, rows, counts, df, lengths = self._lexical_index
        size = len(rows)
        average = sum(lengths) / max(size, 1) or 1
        stop = {"va", "co", "la", "cua", "toi", "bi", "nay", "thi", "cho", "xin", "hoi", "gi",
                "khong", "voi", "ve", "nhu", "nao", "the", "and", "of", "in", "to", "with", "is"}
        terms = {t for t in search_tokens(query) if t not in stop if len(t) > 1 and 0 < df[t] <= max(1, size * 0.4)}
        scores = []
        whole_query = " " + " ".join(search_tokens(query)) + " "
        for idx, row in enumerate(counts):
            score = 0
            overlap = terms.intersection(row)
            title = " ".join(search_tokens((rows[idx][1] or {}).get("title", "")))
            exact_title = bool(title and " " + title + " " in whole_query)
            if len(overlap) < min(2, len(terms)) and not exact_title:
                continue
            for term in overlap:
                idf = math.log1p((size - df[term] + 0.5) / (df[term] + 0.5))
                tf = row[term]
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[idx] / average))
            if score or exact_title:
                scores.append(((score or 1) * (2 if exact_title else 1), idx))
        return [rows[idx] for _, idx in sorted(scores, reverse=True)[:limit]]

    def retrieve_context(self, user_query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Local BM25 by default, with optional vector search after lexical search.
        No user-query cache, embedding download or external request is required
        for the default path. A failed vector lookup cannot discard local hits.
        """
        if not isinstance(user_query, str) or not user_query.strip() or not self.is_available():
            return []
        top_k = max(1, min(5, top_k)) if type(top_k) is int else 2
        search_query = self.expand_query(user_query[:2000])
        pool = min(self.collection.count(), top_k * 3)
        by_text, ranks = {}, {}
        # Index only the local source corpus, never store user messages/queries.
        try:
            for rank, (content, meta) in enumerate(self._bm25_matches(search_query, pool), 1):
                meta = meta or {}
                ranks[content] = 1 / (60 + rank)
                by_text[content] = dict(content=content, title=meta.get("title", ""),
                    category=meta.get("category", ""), source=meta.get("source", ""),
                    source_url=meta.get("source_url", ""), distance=None, distance_metric=None,
                    accepted=True, retrieval="bm25")
        except Exception as error:
            logger.warning("Local reference lookup unavailable (%s).", type(error).__name__)

        if self.vector_search_enabled:
            try:
                # Exactly one attempt. Operators enabling this path must have
                # provisioned a compatible embedding model outside requests.
                results = self.collection.query(query_texts=[search_query], n_results=pool)
                docs = (results.get("documents") or [[]])[0]
                metas = (results.get("metadatas") or [[]])[0]
                distances = (results.get("distances") or [[]])[0]
                for index, (content, distance) in enumerate(zip(docs, distances), 1):
                    if not isinstance(content, str) or not content.strip() or distance is None:
                        continue
                    try:
                        dist = float(distance)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if not math.isfinite(dist) or not 0 <= dist <= self.acceptance_threshold:
                        continue
                    meta = metas[index - 1] if index <= len(metas) and isinstance(metas[index - 1], dict) else {}
                    ranks[content] = ranks.get(content, 0) + 1 / (60 + index)
                    by_text[content] = dict(content=content, title=meta.get("title", ""),
                        category=meta.get("category", ""), source=meta.get("source", ""),
                        source_url=meta.get("source_url", ""), distance=round(dist, 4), distance_metric="l2",
                        accepted=True, retrieval="hybrid" if content in by_text else "vector")
            except Exception as error:
                logger.warning("Optional vector lookup unavailable (%s); keeping local matches.", type(error).__name__)
        return [by_text[key] for key in sorted(ranks, key=ranks.get, reverse=True)[:top_k]]


# Khởi tạo thể hiện Singleton dùng chung toàn ứng dụng
medical_rag_service = MedicalRAGService()
