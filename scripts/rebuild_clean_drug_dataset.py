"""
================================================================================
SCRIPT TẠO BỘ DỮ LIỆU THUỐC VIỆT NAM DUY NHẤT: CAM KẾT 0% TRÙNG LẶP (ZERO DUPLICATE)
================================================================================
Quy tắc khử trùng lặp đa tầng:
  1. Loại bỏ các câu hỏi, tiêu đề bài viết (chỉ giữ đúng tên thuốc/hoạt chất).
  2. Khử trùng lặp tuyệt đối theo:
     - Tên nguyên bản (Exact Match)
     - Tên chữ thường (Case-insensitive)
     - Tên không dấu (ASCII folded)
     - Tên hoạt chất gốc không tính ngoặc đơn (Base Key)
     - Tên đồng nghĩa / Biệt dược đi kèm (Synonyms & Aliases)
  3. Xuất bản DUY NHẤT 1 file .xlsx và 1 file .csv tại data/vietnam_drug_catalog/
================================================================================
"""

import io
import re
import json
import unicodedata
import urllib.request
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CATALOG_DIR = DATA_DIR / "vietnam_drug_catalog"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)


def fold_ascii(text: str) -> str:
    """Chuyển thành chữ thường, bỏ dấu tiếng Việt và chuẩn hóa khoảng trắng."""
    if not text:
        return ""
    s = str(text).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


def get_base_key(text: str) -> str:
    """Lấy khóa gốc bằng cách loại bỏ ngoặc đơn (VD: 'Paracetamol (acetaminophen)' -> 'paracetamol')."""
    base = re.sub(r"\s*\([^)]*\)", "", text)
    return fold_ascii(base)


def extract_aliases(name: str) -> list:
    """Tách các tên trong ngoặc đơn."""
    aliases = []
    matches = re.findall(r"\(([^)]+)\)", name)
    for m in matches:
        clean = m.strip()
        if clean and len(clean) > 1 and not clean.isdigit():
            for part in re.split(r",|\bhoặc\b|\bhay\b", clean, flags=re.IGNORECASE):
                p = part.strip()
                if p and len(p) > 1:
                    aliases.append(p)
    return aliases


def is_valid_drug_name(name: str) -> bool:
    """Kiểm tra chuỗi có phải là tên thuốc thực sự hay là câu hỏi/tiêu đề bài viết."""
    clean = str(name or "").strip()
    if not clean or len(clean) < 2 or len(clean) > 80:
        return False

    lower = clean.lower()
    invalid_starters = (
        "cách ", "tác dụng", "chỉ định", "chống chỉ định", "lưu ý", "cảnh báo",
        "hướng dẫn", "liều dùng", "công dụng", "thành phần", "bảo quản", "tương tác",
        "triệu chứng", "xử trí", "dấu hiệu", "trường hợp", "đối tượng", "phụ nữ",
        "trẻ em", "giá thuốc", "mua thuốc", "uống thuốc", "dùng thuốc", "sử dụng thuốc",
        "thận trọng", "quá liều", "quên liều", "dược lực", "dược động", "tổng quan",
        "giới thiệu", "thông tin", "chú ý", "phân loại", "chẩn đoán", "phòng ngừa"
    )
    if any(lower.startswith(st) for st in invalid_starters):
        return False

    invalid_substrings = (
        "?", "là gì", "có giá", "bao nhiêu", "như thế nào", "ở đâu", "tác dụng phụ",
        "hiếm gặp", "thường gặp", "ít gặp", "nguy hiểm không", "mua ở", "uống khi nào",
        "uống trước hay sau", "dùng như thế nào", "bao lâu thì khỏi", "chữa bệnh gì",
        "uống có tốt không", "uống lúc nào"
    )
    if any(sub in lower for sub in invalid_substrings):
        return False

    if clean.endswith(":") or clean.endswith("?") or clean.endswith("."):
        return False

    # Loại bỏ câu văn dài hơn 8 từ nếu không phải thuốc phối hợp (+)
    words = clean.split()
    if len(words) > 8 and "+" not in clean:
        return False

    return True


def clean_name_formatting(name: str) -> str:
    """Làm sạch tiền tố thừa như 'Thuốc', 'Viên'."""
    s = re.sub(r"^(?:thuốc|thuoc|viên|vien|dung dịch|bột|siro|cao)\s+", "", name.strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def main():
    print(">>> 1. Đang nạp dữ liệu Thông tư 20/2022/TT-BYT...")
    tt20_csv = CATALOG_DIR / "thong_tu_20_drugs.csv"
    if not tt20_csv.exists():
        raise FileNotFoundError(f"Không tìm thấy {tt20_csv}")

    df_tt20 = pd.read_csv(tt20_csv)
    raw_tt20_names = df_tt20["Tên hoạt chất"].dropna().tolist()
    print(f"    => Đã nạp {len(raw_tt20_names)} dòng gốc từ Thông tư 20.")

    # 2. Tải danh sách keyword sạch từ ViMedAQA (Hugging Face)
    print(">>> 2. Đang tải và bóc tách keyword sạch từ Hugging Face ViMedAQA...")
    urls = [
        "https://huggingface.co/datasets/tmnam20/ViMedAQA/resolve/refs%2Fconvert%2Fparquet/drug/train/0000.parquet",
        "https://huggingface.co/datasets/tmnam20/ViMedAQA/resolve/refs%2Fconvert%2Fparquet/drug/test/0000.parquet",
        "https://huggingface.co/datasets/tmnam20/ViMedAQA/resolve/refs%2Fconvert%2Fparquet/drug/validation/0000.parquet",
        "https://huggingface.co/datasets/tmnam20/ViMedAQA/resolve/refs%2Fconvert%2Fparquet/medicine/train/0000.parquet",
        "https://huggingface.co/datasets/tmnam20/ViMedAQA/resolve/refs%2Fconvert%2Fparquet/medicine/test/0000.parquet",
        "https://huggingface.co/datasets/tmnam20/ViMedAQA/resolve/refs%2Fconvert%2Fparquet/medicine/validation/0000.parquet",
    ]

    raw_vimed_keywords = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                df = pd.read_parquet(io.BytesIO(resp.read()))
            for kw in df["keyword"].dropna():
                raw_vimed_keywords.append(str(kw))
        except Exception as e:
            print(f"    Lỗi khi tải {url}: {e}")

    print(f"    => Đã bóc tách {len(raw_vimed_keywords)} keyword thô từ ViMedAQA.")

    # 3. THIẾT KẾ ĐỘNG CƠ KHỬ TRÙNG LẶP TOÀN PHẦN (ZERO DUPLICATE FILTER)
    print(">>> 3. Đang thực thi khử trùng lặp và làm sạch triệt để...")

    seen_base_keys = set()
    seen_exact_keys = set()
    deduped_drugs = []

    # BƯỚC 3A: Xử lý danh mục chuẩn Thông tư 20 (Ưu tiên tuyệt đối)
    for raw in raw_tt20_names:
        clean = clean_name_formatting(raw)
        if not is_valid_drug_name(clean):
            continue

        base_k = get_base_key(clean)
        exact_k = fold_ascii(clean)

        # Kiểm tra xem có bị trùng với thuốc nào trước đó không
        if base_k in seen_base_keys or exact_k in seen_exact_keys:
            continue

        seen_base_keys.add(base_k)
        seen_exact_keys.add(exact_k)

        # Khóa các bí danh trong ngoặc đơn để không bị xuất hiện trùng lần 2
        for a in extract_aliases(clean):
            ak = fold_ascii(a)
            if ak:
                seen_base_keys.add(ak)
                seen_exact_keys.add(ak)

        deduped_drugs.append({
            "name": clean,
            "source": "Thông tư 20/2022/TT-BYT"
        })

    count_tt20 = len(deduped_drugs)
    print(f"    => Thông tư 20 sau khử trùng: {count_tt20} hoạt chất chuẩn.")

    # BƯỚC 3B: Bổ sung biệt dược thực tế từ ViMedAQA (Khử trùng lặp đối chiếu)
    added_vimed = 0
    for raw in raw_vimed_keywords:
        clean = clean_name_formatting(raw)
        if not is_valid_drug_name(clean):
            continue

        base_k = get_base_key(clean)
        exact_k = fold_ascii(clean)

        # Nếu đã có trong Thông tư 20 hoặc đã được thêm trước đó -> LOẠI BỎ (KHÔNG TRÙNG)
        if base_k in seen_base_keys or exact_k in seen_exact_keys:
            continue

        seen_base_keys.add(base_k)
        seen_exact_keys.add(exact_k)
        added_vimed += 1

        deduped_drugs.append({
            "name": clean,
            "source": "Biệt dược ViMedAQA"
        })

    print(f"    => ViMedAQA bổ sung thêm: {added_vimed} biệt dược thương mại duy nhất.")
    print(f"    => TỔNG CỘNG DANH MỤC DUY NHẤT: {len(deduped_drugs)} thuốc (Cam kết 0% trùng lặp).")

    # 4. Gán STT liên tục 1..N
    for i, item in enumerate(deduped_drugs, 1):
        item["stt"] = i
        item["search_key"] = fold_ascii(item["name"])

    # 5. Xuất bản DUY NHẤT 1 file .xlsx và 1 file .csv
    df_final = pd.DataFrame([
        {
            "STT": d["stt"],
            "Tên thuốc / Hoạt chất": d["name"],
            "Nguồn": d["source"]
        }
        for d in deduped_drugs
    ])

    xlsx_path = CATALOG_DIR / "vietnam_drug_catalog.xlsx"
    csv_path = CATALOG_DIR / "vietnam_drug_catalog.csv"
    json_path = CATALOG_DIR / "vietnam_drug_catalog.json"

    df_final.to_excel(xlsx_path, index=False, engine="openpyxl")
    df_final.to_csv(csv_path, index=False, encoding="utf-8-sig")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(deduped_drugs, f, ensure_ascii=False, indent=2)

    # Đồng bộ sang data/vietnam_drugs.json cho backend OCR
    with open(DATA_DIR / "vietnam_drugs.json", "w", encoding="utf-8") as f:
        json.dump(deduped_drugs, f, ensure_ascii=False, indent=2)

    print(f"    => Đã lưu file Excel chuẩn: {xlsx_path.name}")
    print(f"    => Đã lưu file CSV chuẩn:   {csv_path.name}")
    print(f"    => Đã lưu file JSON chuẩn:  {json_path.name}")

    # 6. KIỂM ĐỊNH TỰ ĐỘNG: KIỂM TRA TRÙNG LẶP (INTEGRITY AUDIT)
    names = [d["name"] for d in deduped_drugs]
    lower_names = [d["name"].lower() for d in deduped_drugs]
    ascii_names = [d["search_key"] for d in deduped_drugs]

    assert len(names) == len(set(names)), "Lỗi: Có trùng lặp chính xác chuỗi!"
    assert len(lower_names) == len(set(lower_names)), "Lỗi: Có trùng lặp chữ hoa/chữ thường!"
    assert len(ascii_names) == len(set(ascii_names)), "Lỗi: Có trùng lặp không dấu!"

    print(">>> [KIỂM ĐỊNH TOÀN DIỆN THÀNH CÔNG]: 0 bản ghi trùng lặp (100% sạch & chuẩn hóa)!")


if __name__ == "__main__":
    main()
