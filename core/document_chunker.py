"""
================================================================================
🩺 MEDIMIND DOCUMENT CHUNKER & INGESTION QUALITY MODULE
================================================================================
Module cung cấp các hàm thuần túy (pure functions), tất định (deterministic)
phục vụ pipeline nạp dữ liệu y khoa chuẩn MedlinePlus vào ChromaDB / RAG:
  1. find_boundary_split_point: Tìm ranh giới cắt tự nhiên (đoạn văn > dòng > câu > từ).
  2. chunk_document: Phân đoạn văn bản y khoa bảo toàn ranh giới câu, gộp đuôi nhỏ (< 200 ký tự)
     và luôn gắn contextual prefix (Tiêu đề, Chuyên khoa, Từ khóa) vào 100% chunks.
  3. generate_deterministic_id: Sinh Document ID ổn định, không phụ thuộc thứ tự nạp.
  4. compute_content_hash: Tạo SHA-256 fingerprint phục vụ kiểm soát toàn vẹn dữ liệu.
  5. detect_duplicates: Phát hiện và khử trùng lặp tài liệu trước khi nạp.
  6. save_manifest_atomic / load_manifest / validate_manifest: Quản lý manifest collection an toàn.
================================================================================
"""

import os
import re
import json
import uuid
import hashlib
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


def compute_content_hash(text: str) -> str:
    """
    Tính mã băm SHA-256 của nội dung văn bản sau khi chuẩn hóa Unicode NFC và loại bỏ khoảng trắng thừa.
    """
    normalized = unicodedata.normalize("NFC", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_deterministic_id(file_name: str, source_url: str = "", part_index: int = 0) -> str:
    """
    Tạo Document ID tất định và ổn định theo quy tắc:
        doc_{slug}_{source_hash8}_p{part_index}

    Đảm bảo:
      - Không phụ thuộc vào bộ đếm tuần tự (thêm/sắp xếp lại tệp không làm xê dịch ID của tệp khác).
      - Slug ngắn gọn, dễ tra cứu trong log/debug.
      - 8 ký tự băm từ source_url (hoặc file_name) ngăn ngừa xung đột slug trùng tên.
    """
    stem = Path(file_name).stem.lower()
    # Chỉ giữ chữ thường, số, dấu gạch dưới
    clean_stem = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")
    slug = clean_stem[:32] if clean_stem else "doc"

    hash_source = source_url.strip() if source_url.strip() else file_name
    source_hash8 = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()[:8]

    return f"doc_{slug}_{source_hash8}_p{part_index}"


def find_boundary_split_point(text: str, max_chars: int, min_chunk_chars: int = 200) -> int:
    r"""
    Tìm điểm cắt tối ưu trong chuỗi `text` không vượt quá `max_chars`,
    tuân thủ nghiêm ngặt thứ tự ưu tiên ranh giới ngữ nghĩa:
      1. Ranh giới đoạn văn (\n\s*\n)
      2. Ranh giới dòng mới (\n)
      3. Ranh giới kết thúc câu ([.!?]\s+)
      4. Ranh giới từ trắng (\s+)
      5. Fallback max_chars nếu văn bản không chứa khoảng trắng (chuỗi liền).
    """
    if len(text) <= max_chars:
        return len(text)

    search_window = text[:max_chars]

    # Ưu tiên 1: Đoạn văn (Double newline)
    para_splits = [m.start() for m in re.finditer(r"\n\s*\n", search_window)]
    valid_paras = [p for p in para_splits if p >= min_chunk_chars]
    if valid_paras:
        return valid_paras[-1]

    # Ưu tiên 2: Dòng mới (Single newline)
    line_splits = [m.start() for m in re.finditer(r"\n", search_window)]
    valid_lines = [p for p in line_splits if p >= min_chunk_chars]
    if valid_lines:
        return valid_lines[-1]

    # Ưu tiên 3: Kết thúc câu (. ! ? theo sau bởi khoảng trắng)
    sent_splits = [m.end() for m in re.finditer(r"[.!?]\s+", search_window)]
    valid_sents = [p for p in sent_splits if p >= min_chunk_chars]
    if valid_sents:
        return valid_sents[-1]

    # Ưu tiên 4: Ranh giới từ (Khoảng trắng)
    word_splits = [m.start() for m in re.finditer(r"\s+", search_window)]
    valid_words = [p for p in word_splits if p >= min_chunk_chars]
    if valid_words:
        return valid_words[-1]

    return max_chars


def chunk_document(
    title: str,
    category: str,
    content: str,
    search_phrases: Optional[str] = None,
    max_chars: int = 2000,
    overlap_chars: int = 200,
    min_chunk_chars: int = 200,
    hard_max_chars: int = 2200,
    chunking_version: str = "v2_sentence_contextual",
    title_vi: Optional[str] = None,
    title_en: Optional[str] = None,
    category_vi: Optional[str] = None,
    category_en: Optional[str] = None,
    keywords_vi: Optional[str] = None,
    keywords_en: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Phân mảnh văn bản tài liệu y khoa đảm bảo chất lượng:
      - Gắn Contextual Prefix (Tên bệnh/chủ đề, Chuyên khoa, Từ khóa liên quan; hỗ trợ song ngữ cho Tier-A) vào TẤT CẢ chunks.
      - Sử dụng ranh giới tự nhiên (paragraph -> newline -> sentence -> word), không cắt đôi từ.
      - Gộp phần đuôi nhỏ (< min_chunk_chars) vào chunk trước đó thay vì tạo chunk mồ côi.
      - Overlap lùi về ranh giới câu hoặc từ gần nhất.
      - Đảm bảo độ dài toàn văn chunk <= hard_max_chars.
    """
    clean_content = content.strip()
    if not clean_content:
        return []

    # Xây dựng Contextual Prefix chuẩn mực (hỗ trợ song ngữ nếu có đầy đủ trường)
    if title_vi and title_en:
        header_lines = [
            f"Bệnh/Chủ đề: {title_vi.strip()}",
            f"Disease/Topic: {title_en.strip()}",
            f"Chuyên khoa: {(category_vi or category).strip()}",
            f"Category: {(category_en or category).strip()}"
        ]
        if keywords_vi and keywords_vi.strip():
            header_lines.append(f"Từ khóa: {keywords_vi.strip()}")
        if keywords_en and keywords_en.strip():
            header_lines.append(f"Keywords: {keywords_en.strip()}")
        elif not keywords_vi and search_phrases and search_phrases.strip():
            header_lines.append(f"Từ khóa: {search_phrases.strip()}")
    else:
        header_lines = [
            f"Bệnh/Chủ đề: {title.strip()}",
            f"Chuyên khoa: {category.strip()}"
        ]
        if search_phrases and search_phrases.strip():
            header_lines.append(f"Từ khóa liên quan: {search_phrases.strip()}")

    prefix = "\n".join(header_lines) + "\n\nNội dung chi tiết:\n"
    prefix_len = len(prefix)

    # Chiều dài tối đa cho phần thân văn bản mỗi chunk
    target_body_chars = max(300, max_chars - prefix_len)

    chunks: List[Dict[str, Any]] = []
    start = 0
    total_len = len(clean_content)

    while start < total_len:
        remaining = total_len - start

        # Xử lý đoạn đuôi nhỏ: nếu còn lại < min_chunk_chars và đã có chunk trước đó,
        # gộp vào chunk cuối cùng nếu không vượt quá hard_max_chars.
        if remaining < min_chunk_chars and chunks:
            candidate_body = chunks[-1]["body"] + " " + clean_content[start:].strip()
            candidate_text = prefix + candidate_body
            if len(candidate_text) <= hard_max_chars:
                chunks[-1]["body"] = candidate_body
                chunks[-1]["text"] = candidate_text
                chunks[-1]["char_count"] = len(candidate_text)
                break

        # Nếu phần còn lại nằm gọn trong target_body_chars, lấy nốt làm chunk cuối
        if remaining <= target_body_chars:
            body_slice = clean_content[start:].strip()
            if body_slice:
                full_text = prefix + body_slice
                part_idx = len(chunks)
                chunks.append({
                    "part_index": part_idx,
                    "text": full_text,
                    "body": body_slice,
                    "prefix": prefix,
                    "char_count": len(full_text),
                    "chunking_version": chunking_version
                })
            break

        # Tìm điểm cắt tối ưu trong cửa sổ
        search_slice = clean_content[start:start + target_body_chars]
        split_offset = find_boundary_split_point(search_slice, target_body_chars, min_chunk_chars)
        split_point = start + split_offset

        body_slice = clean_content[start:split_point].strip()
        if body_slice:
            full_text = prefix + body_slice
            part_idx = len(chunks)
            chunks.append({
                "part_index": part_idx,
                "text": full_text,
                "body": body_slice,
                "prefix": prefix,
                "char_count": len(full_text),
                "chunking_version": chunking_version
            })

        # Xác định điểm bắt đầu cho chunk tiếp theo với Overlap có điều chỉnh ranh giới
        target_next = max(start + 1, split_point - overlap_chars)
        overlap_window = clean_content[target_next:split_point]

        # Tìm ranh giới kết thúc câu trong vùng overlap
        sent_match = re.search(r"(?<=[.!?])\s+", overlap_window)
        if sent_match:
            start = target_next + sent_match.end()
        else:
            word_match = re.search(r"\s+", overlap_window)
            if word_match:
                start = target_next + word_match.end()
            else:
                start = target_next

    return chunks


def detect_duplicates(
    documents: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Phát hiện trùng lặp tài liệu dựa trên mã băm SHA-256 của nội dung (page_content).
    Giữ lại bản ghi đầu tiên (canonical), ghi nhận danh sách tài liệu trùng lặp.
    """
    seen_hashes: Dict[str, str] = {}
    unique_docs: List[Dict[str, Any]] = []
    duplicate_records: List[Dict[str, Any]] = []

    for doc in documents:
        content = (doc.get("page_content") or doc.get("content") or "").strip()
        file_name = doc.get("file_name", "unknown")
        content_hash = compute_content_hash(content)

        if content_hash in seen_hashes:
            duplicate_records.append({
                "duplicate_file": file_name,
                "original_file": seen_hashes[content_hash],
                "content_hash": content_hash,
                "title": doc.get("title", "")
            })
        else:
            seen_hashes[content_hash] = file_name
            # Gắn sẵn content_hash vào doc để tái sử dụng
            doc["content_hash"] = content_hash
            unique_docs.append(doc)

    report = {
        "total_scanned": len(documents),
        "unique_count": len(unique_docs),
        "duplicate_count": len(duplicate_records),
        "duplicates": duplicate_records
    }
    return unique_docs, report


def save_manifest_atomic(manifest_data: Dict[str, Any], target_path: Path) -> None:
    """
    Lưu tệp active_collection.json an toàn nguyên tử (Atomic write via tmp file + rename).
    Ngăn chặn việc tệp bị lỗi hoặc hỏng một nửa khi máy chủ bị tắt ngang hoặc crash.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = target.with_name(f"{target.name}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise


def load_manifest(db_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Đọc tệp active_collection.json nếu tồn tại và hợp lệ.
    Trả về None nếu không tìm thấy hoặc tệp bị hỏng.
    """
    manifest_file = Path(db_dir) / "active_collection.json"
    if not manifest_file.exists():
        return None

    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if validate_manifest(data):
            return data
        return None
    except Exception:
        return None


def validate_manifest(data: Any) -> bool:
    """
    Kiểm tra cấu trúc manifest có thỏa mãn schema tối thiểu:
      - Là dict
      - Có active_collection (chuỗi không rỗng)
      - Có document_count (số nguyên >= 0)
    """
    if not isinstance(data, dict):
        return False

    collection_name = data.get("active_collection")
    if not collection_name or not isinstance(collection_name, str):
        return False

    doc_count = data.get("document_count")
    if doc_count is None or not isinstance(doc_count, int) or doc_count < 0:
        return False

    return True
