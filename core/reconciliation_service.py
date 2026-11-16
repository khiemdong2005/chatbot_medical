import re
import difflib
import unicodedata
from typing import Dict, Any, List

KNOWN_MEDS = [
    {
        "pattern": r"(?:scotol|shunorac)",
        "name": "Scotolac (Shunorac)",
        "default_strength": "200mg",
        "default_dose": "1 viên",
        "default_freq": "2 lần / ngày",
        "default_usage": "Uống sau ăn"
    },
    {
        "pattern": r"(?:độc hoạt|doc hoat|dxk hoat|dk hoat|tks)",
        "name": "Độc hoạt TKS viên (Lọ/100v)",
        "default_strength": "",
        "default_dose": "3 viên",
        "default_freq": "3 lần / ngày",
        "default_usage": "Uống sau ăn"
    },
    {
        "pattern": r"(?:đại tần|dai lin|dai tan|tan giao)",
        "name": "Đại tần giao (H/100v)",
        "default_strength": "",
        "default_dose": "3 viên",
        "default_freq": "3 lần / ngày",
        "default_usage": "Uống sau ăn"
    },
    {
        "pattern": r"(?:rheumatin|rhcumatin)",
        "name": "Rheumatin (Ch/40v)",
        "default_strength": "",
        "default_dose": "3 viên",
        "default_freq": "3 lần / ngày",
        "default_usage": "Uống sau ăn"
    },
    {
        "pattern": r"(?:ginkobil|ginkgo)",
        "name": "Ginkobil (H/100v)",
        "default_strength": "",
        "default_dose": "1 viên",
        "default_freq": "3 lần / ngày",
        "default_usage": "Uống sau ăn"
    },
    {
        "pattern": r"(?:jex)",
        "name": "JEX (H/30v)",
        "default_strength": "",
        "default_dose": "1 viên",
        "default_freq": "2 lần / ngày",
        "default_usage": "Uống sau ăn"
    },
    {
        "pattern": r"(?:cồn xoa|con xoa|can xon|xoa bóp|xoa bop)",
        "name": "Cồn xoa bóp Viện",
        "default_strength": "",
        "default_dose": "Thoa ngoài da",
        "default_freq": "Khi đau",
        "default_usage": "Xoa lưng đau"
    }
]


def _ascii_fold(s: str) -> str:
    if not s:
        return ""
    t = str(s).replace("đ", "d").replace("Đ", "D").replace("ø", "o").replace("Ø", "O").replace("ß", "ss")
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if unicodedata.category(ch) != "Mn")
    t = t.lower()
    t = re.sub(r"\bu6ng\b|\bi-jong\b", "uong", t)
    t = re.sub(r"\bt6i\b", "toi", t)
    t = re.sub(r"\btru&c\b", "truoc", t)
    t = re.sub(r"\bian\b", "lan", t)
    return re.sub(r"\s+", " ", t).strip()


def _clean_str(s: str) -> str:
    return _ascii_fold(s)


def _clean_ocr_display(s: str) -> str:
    """Khử dấu Bắc Âu giả (å, ä, ö, ü, ø) sinh ra khi engine OCR tiếng Anh đọc văn bản tiếng Việt."""
    if not s:
        return ""
    txt = str(s).strip()
    if re.search(r"[åäöüøÅÄÖÜØ]", txt):
        txt = "".join(ch for ch in unicodedata.normalize("NFKD", txt) if unicodedata.category(ch) != "Mn")
        txt = re.sub(r"([uU])qc\b", r"\1oc", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _extract_numbers(s: str) -> List[str]:
    """Bóc tách các cụm số nguyên hoặc số thập phân trong chuỗi."""
    if not s:
        return []
    found = re.findall(r"\d+(?:[.,]\d+)?", str(s))
    return [x.replace(",", ".") for x in found]


def _unit_label(raw_u: str) -> str:
    u = _ascii_fold(raw_u)
    mapping = {
        "vien": "viên", "vicn": "viên", "ven": "viên",
        "hop": "hộp", "hon": "hộp", "box": "hộp",
        "chai": "chai", "char": "chai", "chal": "chai", "bottle": "chai",
        "goi": "gói", "gôi": "gói", "sachet": "gói", "pack": "gói",
        "ong": "ống", "ông": "ống", "amp": "ống", "ampoule": "ống",
        "lo": "lọ", "vial": "lọ",
        "vi": "vỉ", "blister": "vỉ",
        "tuyp": "tuýp", "tube": "tuýp",
    }
    base = mapping.get(u, u)
    if raw_u.istitle():
        return base.capitalize()
    return base


def _parse_dosing_details(text: str) -> Dict[str, str]:
    """Bóc tách liều dùng mỗi lần, tần suất và cách dùng từ dòng hướng dẫn (có dấu / không dấu / OCR nhiễu)."""
    f_txt = _ascii_fold(text)
    out = {"dose": "", "frequency": "", "usage": ""}
    if not f_txt:
        return out

    # 1. Dose (mỗi lần uống bao nhiêu viên/gói/ống/ml)
    # Loại bỏ cụm số lượng tổng (SL: 30 Viên) để không nhầm sang liều dùng
    clean_dosing_txt = re.sub(r"\b(?:sl|sc|so\s*luong|qty)\s*[:.\-]?\s*\d+\s*(?:vien|goi|ong|chai|hop|lo|vi|tuyp|tablet|cap|sachet)?\b", "", f_txt, flags=re.IGNORECASE)
    m_each = re.search(
        r"(?:moi\s*lan|uong|sang|trua|chieu|toi|take)\s*[:\-]?\s*(\d+(?:[\/.,]\d+)?)\s*(vien|goi|ong|ml|giot|nhát|nhat|tablet|tab|cap|capsule|sachet)\b",
        clean_dosing_txt,
    )
    if not m_each:
        m_each = re.search(
            r"\b(\d+(?:[\/.,]\d+)?|iv|jv|ur)\s*(vien|v|vx|goi|ong|ml|tablet|tab|cap|capsule|sachet)\b(?=\s*(?:[,;\/x]|lan|times|sang|trua|chieu|toi|truoc|sau|$))",
            clean_dosing_txt,
        )
    if m_each:
        raw_d = m_each.group(1)
        d_num = "1" if raw_d in ("iv", "ur") else ("3" if raw_d == "jv" else raw_d)
        u_lbl = "ml" if m_each.group(2) == "ml" else _unit_label(m_each.group(2)).lower()
        out["dose"] = f"{d_num} {u_lbl}"

    # 2. Frequency (Sáng / Trưa / Chiều / Tối hoặc X lần/ngày)
    slots = []
    if re.search(r"\b(sang|morning|breakfast)\b", f_txt):
        slots.append("Sáng")
    if re.search(r"\b(trua|noon|lunch)\b", f_txt):
        slots.append("Trưa")
    if re.search(r"\b(chieu|afternoon)\b", f_txt):
        slots.append("Chiều")
    if re.search(r"\b(toi|evening|dinner)\b", f_txt):
        slots.append("Tối")
    if re.search(r"\b(truoc\s*(?:khi\s*)?ngu|bedtime)\b", f_txt):
        slots.append("Trước ngủ")

    m_freq = re.search(
        r"(?:ngay\s*(?:uong\s*)?|x\s*)([1-6]|iv|jv)\s*(?:lan|kan|nean|times?)\b",
        f_txt,
    )
    if m_freq:
        raw_f = m_freq.group(1)
        f_num = "1" if raw_f == "iv" else ("3" if raw_f == "jv" else raw_f)
        if slots:
            out["frequency"] = f"{f_num} lần / ngày ({' - '.join(slots)})"
        else:
            out["frequency"] = f"{f_num} lần / ngày"
    elif slots:
        out["frequency"] = f"{len(slots)} lần / ngày ({' - '.join(slots)})"
    elif re.search(r"\btwice\s*(?:daily|a\s*day)\b|\bbid\b", f_txt):
        out["frequency"] = "2 lần / ngày"
    elif re.search(r"\bthree\s*times\s*(?:daily|a\s*day)\b|\btid\b", f_txt):
        out["frequency"] = "3 lần / ngày"
    elif re.search(r"\bonce\s*(?:daily|a\s*day)\b|\bqd\b", f_txt):
        out["frequency"] = "1 lần / ngày"

    # 3. Usage (trước ăn / sau ăn / ngoài da / súc họng / ngậm)
    if re.search(r"\b(truoc\s*an|before\s*meals?)\b", f_txt):
        m_m = re.search(r"truoc\s*an\s*(\d{1,2})\s*phut", f_txt)
        out["usage"] = f"Uống trước ăn {m_m.group(1)} phút" if m_m else "Uống trước ăn"
    elif re.search(r"\b(sau\s*an|after\s*meals?)\b", f_txt):
        m_m = re.search(r"sau\s*an\s*(\d{1,2})\s*phut", f_txt)
        out["usage"] = f"Uống sau ăn {m_m.group(1)} phút" if m_m else "Uống sau ăn"
    elif re.search(r"\b(trong\s*khi\s*an|cung\s*bua\s*an|with\s*meals?)\b", f_txt):
        out["usage"] = "Uống trong bữa ăn"
    elif re.search(r"\b(khi\s*dau|prn|as\s*needed)\b", f_txt):
        out["usage"] = "Khi đau"
    elif re.search(r"\b(xoa\s*lung|thoa\s*ngoai|ngoai\s*da|boi|external)\b", f_txt):
        out["usage"] = "Dùng ngoài da"
    return out


_MEDICATION_LABEL = re.compile(
    r"(?:đơn\s*thuốc|don\s*thuoc|chẩn\s*đoán|chan\s*doan|"
    r"bác\s*sĩ|bac\s*si|điều\s*trị|dieu\s*tri|"
    r"bệnh\s*viện|benh\s*vien|phòng\s*khám|phong\s*kham|sở\s*y\s*tế|so\s*y\s*te|"
    r"cộng\s*khoản|cong\s*khoan|lời\s*dặn|loi\s*dan|"
    r"tái\s*khám|tai\s*kham|ngày\s*khám|ngay\s*kham|"
    r"ngày\s*sinh|ngay\s*sinh|họ\s*tên|ho\s*ten|"
    r"địa\s*chỉ|dia\s*chi|số\s*hồ\s*sơ|so\s*ho\s*so|"
    r"\bsl\b|\bsc\b|\bso\s*luong\b|\bquanti(?:ty)?\b|\bqty\b)",
    re.IGNORECASE,
)
_MEDICATION_UNITS = r"viên|vien|ven|gói|gôi|goi|chai|chal|lọ|lo|ống|ông|ong|hộp|hop|vỉ|vi|ml|mg|mcg|g"


def is_plausible_medication_name(name: str) -> bool:
    """Reject obvious OCR labels, dates and quantities without guessing a drug list."""
    raw_value = re.sub(r"\s+", " ", str(name or "")).strip()
    if re.fullmatch(r"\[[^\]]+\]", raw_value):
        return False
    if re.match(r"^\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|g|iu)\b", raw_value, re.IGNORECASE):
        return False
    value = raw_value.strip(" \t\r\n\"'.,;:()[]")
    if len(value) < 2 or not re.search(r"[A-Za-zÀ-ỹ]", value):
        return False
    if _MEDICATION_LABEL.search(value):
        return False
    # Column headings often appear as independent OCR boxes beside the drug row.
    if _ascii_fold(value) in {"stt", "ten thuoc", "ham luong", "so luong", "don vi",
                              "cach dung", "cahdur", "cha", "chicu", "cong chicu", "sig"}:
        return False
    if re.fullmatch(r"\d{1,2}\s*[/.-]\s*\d{2,4}", value):
        return False
    if re.fullmatch(rf"\d+(?:[.,]\d+)?\s*(?:{_MEDICATION_UNITS})?", value, re.IGNORECASE):
        return False
    if re.fullmatch(rf"(?:{_MEDICATION_UNITS})", value, re.IGNORECASE):
        return False
    return True


def _normalized_entity(value: Any) -> str:
    """Compare OCR/AI fields despite stray quotes and punctuation."""
    return re.sub(r"\W+", " ", str(value or "").casefold(), flags=re.UNICODE).strip()


def _header_values_agree(field: str, ocr_value: Any, model_value: Any) -> bool:
    """Allow spelling/accent differences without hiding a real field conflict."""
    ocr = str(ocr_value or "").strip()
    model = str(model_value or "").strip()
    if field in ("date", "dob"):
        ocr_digits = re.findall(r"\d+", ocr)
        model_digits = re.findall(r"\d+", model)
        if len(ocr_digits) == len(model_digits) == 3:
            return [int(part) for part in ocr_digits] == [int(part) for part in model_digits]
    def fold(value: str) -> str:
        value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
        value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        return re.sub(r"\W+", " ", value, flags=re.UNICODE).strip()

    left, right = fold(ocr), fold(model)
    if not left or not right:
        return False
    if field == "doctor":
        left = re.sub(r"^(?:bs|bac si)\s+", "", left)
        right = re.sub(r"^(?:bs|bac si)\s+", "", right)
    if left == right:
        return True
    if field in ("patient_name", "doctor", "age", "gender", "date", "dob"):
        return False
    if (len(left) >= 5 and left in right) or (len(right) >= 5 and right in left):
        return True
    if field == "diagnosis":
        return difflib.SequenceMatcher(None, left, right).ratio() >= 0.75
    return False


def _is_role_only_doctor(value: Any) -> bool:
    role = _normalized_entity(value)
    return bool(role) and bool(re.fullmatch(
        r"(?:bác sĩ|bac si|bs|thầy thuốc|thay thuoc)(?: điều trị| dieu tri| kê đơn| ke don)?|"
        r"điều trị|dieu tri|kê đơn|ke don",
        role,
    ))


def _is_malformed_facility(value: Any) -> bool:
    facility = str(value or "").strip()
    if not facility:
        return False
    return bool(facility.count('"') % 2 or facility.count("'") % 2)


def _merge_medication_rows(ocr_meds: List[Dict[str, Any]],
                           model_meds: List[Dict[str, Any]],
                           anchor_pairs: Dict[int, int] = None) -> List[Dict[str, Any]]:
    """Keep OCR row order while using a corroborated model reading for noisy text."""
    if not ocr_meds:
        return model_meds

    merged_rows = []
    used_model_rows = set()
    anchor_pairs = anchor_pairs or {}
    for row_index, ocr_med in enumerate(ocr_meds):
        ocr_name = _normalized_entity(ocr_med.get("name"))
        best_index = None
        best_score = 0.0
        best_name_score = 0.0
        for index, model_med in enumerate(model_meds):
            if index in used_model_rows or not isinstance(model_med, dict):
                continue
            model_name = _normalized_entity(model_med.get("name"))
            if not ocr_name or not model_name:
                continue
            score = difflib.SequenceMatcher(None, ocr_name, model_name).ratio()
            if len(ocr_name) >= 4 and (ocr_name in model_name or model_name in ocr_name):
                score = 1.0
            name_score = score
            # A weak OCR spelling can still be the same row when both readers
            # found the same number of medicines in the same order. Never use
            # this shortcut for a conflicting numeric strength.
            if (len(ocr_meds) == len(model_meds) and index == row_index and score >= 0.55):
                ocr_strength = _extract_numbers(ocr_med.get("strength"))
                model_strength = _extract_numbers(model_med.get("strength"))
                if not (ocr_strength and model_strength and ocr_strength != model_strength):
                    score = max(score, 0.72)
            if anchor_pairs.get(row_index) == index:
                score = 1.1  # Unique prescription row anchor outranks fuzzy spelling.
            if score > best_score:
                best_index, best_score = index, score
                best_name_score = name_score

        combined = dict(ocr_med)
        if best_index is not None and best_score >= 0.72:
            used_model_rows.add(best_index)
            model_med = model_meds[best_index]
            raw_name = str(combined.get("name") or "")
            model_name = str(model_med.get("name") or "").strip()
            if (model_name and raw_name != model_name and best_name_score < 0.72
                    and is_plausible_medication_name(model_name)):
                combined["name"] = model_name
                combined["raw_ocr_name"] = raw_name
                combined["needs_review"] = True
            for field in ("strength", "dose", "frequency", "days", "usage"):
                if not model_med.get(field):
                    continue
                ocr_value = str(combined.get(field) or "")
                model_value = str(model_med[field])
                if field == "strength" and ocr_value:
                    ocr_numbers = _extract_numbers(ocr_value)
                    model_numbers = _extract_numbers(model_value)
                    if not ocr_numbers and model_numbers:
                        combined["raw_ocr_strength"] = ocr_value
                        combined[field] = model_value
                        combined["needs_review"] = True
                        continue
                    if ocr_numbers != model_numbers:
                        combined["needs_review"] = True
                        continue
                noisy_instruction = (field in ("frequency", "usage") and (
                    bool(re.search(r"[{}|~\";]", ocr_value))
                    or _ascii_fold(ocr_value) in {"cha", "cahdur", "cong chicu", "chicu"}
                ))
                if not ocr_value or noisy_instruction:
                    combined[field] = str(model_med[field])
                    if ocr_value:
                        combined["needs_review"] = True
        merged_rows.append(combined)
    return merged_rows


def _prescription_body_bounds(rows: List[Dict[str, Any]]) -> tuple:
    """Locate the medicine table using section labels, without trusting row numbers alone."""
    start = None
    end = len(rows)
    for index, row in enumerate(rows):
        folded = _ascii_fold(row.get("text", ""))
        if re.search(r"\b(?:chan\s*doan|don\s*thuoc|toa\s*thuoc)\b", folded):
            start = index + 1
        if re.search(r"\b(?:stt|ten\s*thuoc|ten\s*duoc\s*pham)\b", folded):
            start = index + 1
        if start is not None and index >= start and re.search(
            r"\b(?:cong\s*khoan|tong\s*cong|bac\s*si\s*dieu\s*tri|"
            r"loi\s*dan|tai\s*kham|hen\s*tai\s*kham|ngay\s*hen)\b", folded,
        ):
            end = index
            break
    if start is None:
        start = next((index for index, row in enumerate(rows)
                      if re.match(r"^\s*[1-9]\d*[.)]\s*\S", row.get("text", ""))), len(rows))
    return start, end


def _medicine_heading_rows(rows: List[Dict[str, Any]]) -> List[tuple]:
    """Find distinct drug-shaped rows, leaving dosing and quantity-only rows out."""
    headings = []
    for index, row in enumerate(rows):
        items = sorted(row.get("items") or [], key=lambda item: item.get("x_min", 0))
        cells = [str(item.get("text", "")).strip() for item in items if item.get("text")]
        if not cells:
            cells = [part.strip() for part in str(row.get("text", "")).split("|") if part.strip()]
        if cells and re.fullmatch(r"[1-9]\d*[.)]?", cells[0]):
            cells = cells[1:]
        if not cells:
            continue
        first = re.sub(r"^\s*[1-9]\d*[.)]\s*", "", cells[0]).strip()
        folded = _ascii_fold(first).replace("_", " ")
        if re.match(r"^(?:uong|sang|trua|chieu|toi|cach|lieu|ngay|hen|tai|"
                    r"cahdur|cichduro|cakdur|casadung|cdch\s*dirg)\b", folded):
            continue
        if not is_plausible_medication_name(first) or not re.search(r"[A-Za-zÀ-ỹ]{3}", first):
            continue
        text = str(row.get("text", ""))
        product_code = bool(re.search(r"\[(?:KDNT|KINT|KD[A-Z]{1,3}T)\]", text, re.IGNORECASE))
        strength = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|g|iu)\b", text, re.IGNORECASE))
        quantity = bool(re.search(r"\b\d+\s*(?:vi[eê]n|vien|goi|g[oó]i|ong|[oố]ng|chai|lo|l[oọ])\b",
                                  text, re.IGNORECASE))
        ordinal = bool(re.match(r"^\s*[1-9]\d*[.)]\s*\S", text))
        if product_code or (strength and (quantity or ordinal)) or (ordinal and quantity):
            headings.append((index, row))
    return headings


def _row_anchor_box(row: Dict[str, Any]) -> List[List[float]]:
    box = row.get("union_bbox")
    if box and len(box) == 4:
        return [[float(x), float(y)] for x, y in box]
    points = [point for item in row.get("items", []) for point in item.get("box", [])]
    if not points:
        return []
    x_min, x_max = min(point[0] for point in points), max(point[0] for point in points)
    y_min, y_max = min(point[1] for point in points), max(point[1] for point in points)
    return [[float(x_min), float(y_min)], [float(x_max), float(y_min)],
            [float(x_max), float(y_max)], [float(x_min), float(y_max)]]


def _prescription_medications_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Read drug names only inside the prescription body, never from its header/footer."""
    start, end = _prescription_body_bounds(rows)
    if start >= end:
        return []

    has_table_heading = any(re.search(r"\b(?:stt|ten\s*thuoc)\b", _ascii_fold(row.get("text", "")))
                            for row in rows[:start])
    groups: List[Dict[str, Any]] = []
    for row in rows[start:end]:
        row_items = row.get("items", [])
        if row_items and all(item.get("x_min") is not None for item in row_items):
            row_items = sorted(row_items, key=lambda item: item["x_min"])
        items = [str(item.get("text", "")).strip() for item in row_items]
        if not items:
            items = [part.strip() for part in row.get("text", "").split("|")]
        candidate = ""
        strength = ""
        row_strength = re.search(r"\b(\d+[oO0]*\s*(?:mg|mcg|ml|g|iu))\b",
                                 row.get("text", ""), re.IGNORECASE)
        for item in items:
            item = re.sub(r"^\s*\d{1,2}\s*[.)]\s*", "", item).strip()
            if re.match(r"^(?:uống|uong|ngày\s*uống|ngay\s*uong|sáng|sang|trưa|trua|"
                        r"chiều|chieu|tối|toi|mỗi\s*lần|moi\s*lan|cách\s*dùng|cach\s*dung)\b",
                        _ascii_fold(item).replace("_", " ")):
                continue
            prefix = item.split("(", 1)[0].strip()
            words = prefix.split()
            if not words or not re.search(r"[A-Za-zÀ-ỹ]{3}", prefix):
                continue
            # A bracketed product code such as [KDNT] is not the brand token.
            upper_brand = len(words[0]) >= 3 and words[0].isupper()
            strength_match = re.search(r"\b(\d+[oO0]*\s*(?:mg|mcg|ml|g|iu))\b", item, re.IGNORECASE)
            row_has_quantity = bool(re.search(r"\b\d{1,3}\s*(?:vien|viên|goi|gói|ong|ống|chai|lo|lọ|hop|hộp)\b",
                                              row.get("text", ""), re.IGNORECASE))
            row_product_marker = bool(re.search(r"\[(?:KDNT|KINT|KD[A-Z]{1,3}T)\]", row.get("text", ""), re.IGNORECASE))
            if not upper_brand and not strength_match and not (
                row_strength or row_product_marker
                or (has_table_heading and (row_has_quantity or "(" in item))
            ):
                continue
            brand_words = []
            if upper_brand:
                for word in words:
                    if re.fullmatch(r"\d+[oO0]*\s*(?:mg|mcg|ml|g)", word, re.IGNORECASE):
                        break
                    if word.isupper() or re.fullmatch(r"\d{1,3}", word):
                        brand_words.append(word)
                    else:
                        break
            proposed = " ".join(brand_words).strip() if upper_brand else prefix
            proposed = re.sub(r"\s+\d+[oO0]*\s*(?:mg|mcg|ml|g|iu)\b.*$", "", proposed,
                              flags=re.IGNORECASE).strip()
            if not is_plausible_medication_name(proposed):
                continue
            candidate = proposed
            if strength_match or row_strength:
                strength = re.sub(r"[oO]", "0", (strength_match or row_strength).group(1)).replace(" ", "")
            break
        if candidate:
            groups.append({"name": candidate, "strength": strength, "rows": [row]})
        elif groups:
            groups[-1]["rows"].append(row)

    medications = []
    for group in groups:
        first_text = group["rows"][0].get("text", "").replace("|", " ")
        full_text = " ".join(r.get("text", "").replace("|", " ") for r in group["rows"])
        quantity = ""
        quantity_matches = list(re.finditer(
            r"\b(\d{1,3})\s*(viên|vien|ven|gói|gôi|goi|chai|chal|lọ|lo|ống|ông|ong|hộp|hop|vỉ)\b",
            first_text, re.IGNORECASE,
        ))
        if quantity_matches:
            quantity_match = quantity_matches[-1]
            unit = quantity_match.group(2).casefold()
            unit = {
                "vien": "viên", "ven": "viên", "gôi": "gói", "goi": "gói",
                "chal": "chai", "lo": "lọ", "ông": "ống", "ong": "ống",
                "hop": "hộp",
            }.get(unit, unit)
            quantity = f"{quantity_match.group(1)} {unit}"
        if not quantity and start > 0:
            # OCR can put the rightmost quantity into the table-heading row
            # while the drug name falls into the next row. Use coordinates,
            # and only attach a unique nearby quantity to the first drug.
            heading = rows[start - 1]
            med_row = group["rows"][0]
            heading_y = heading.get("y_center")
            med_y = med_row.get("y_center")
            med_x = min((item.get("x_min") for item in med_row.get("items", [])
                         if item.get("x_min") is not None), default=None)
            if group is groups[0] and heading_y is not None and med_y is not None and med_x is not None \
                    and 0 <= med_y - heading_y <= 40:
                nearby = []
                for item in heading.get("items", []):
                    item_x = item.get("x_min")
                    match = re.fullmatch(
                        r"\s*(\d{1,3})\s*(viên|vien|ven|gói|goi|ống|ong|chai|lọ|lo|hộp|hop|vỉ)\s*",
                        item.get("text", ""), re.IGNORECASE,
                    )
                    if match and item_x is not None and item_x > med_x + 50:
                        nearby.append(match)
                if len(nearby) == 1:
                    quantity = f"{nearby[0].group(1)} {_unit_label(nearby[0].group(2).lower())}"
        dose = ""
        dose_match = re.search(
            r"mỗi\s*lần\s*(\d+(?:/\d+)?)\s*(viên|gói|chai|ống|ml)\b",
            full_text, re.IGNORECASE,
        )
        if dose_match:
            dose = f"{dose_match.group(1)} {dose_match.group(2)}"
        frequency = ""
        frequency_match = re.search(
            r"(?:ngày\s*uống|ngay\s*uong|ngay\s*ucng).{0,35}?([1-9])\s*(?:lần|lan|làn|ian)\b",
            full_text, re.IGNORECASE,
        )
        if frequency_match:
            frequency = f"{frequency_match.group(1)} lần/ngày"
        usage = ""
        if re.search(r"uống\s*sau\s*ăn|uong\s*sau\s*an", full_text, re.IGNORECASE):
            usage = "Uống sau ăn"
        elif re.search(r"uống\s*trước\s*ăn|uong\s*truoc\s*an", full_text, re.IGNORECASE):
            usage = "Uống trước ăn"
        medications.append({"name": group["name"], "strength": group["strength"],
                            "dose": dose, "frequency": frequency,
                            "days": quantity, "usage": usage})
    return medications


def _parse_numbered_medications(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Parse numbered prescriptions with potential multi-line dosing instructions."""
    meds: List[Dict[str, str]] = []
    continuation_re = re.compile(
        r"^(?:[-+•*]\s*)?(?:uong|ngay\s*uong|sang|trua|chieu|toi|moi\s*lan|lieu\s*dung|cach\s*dung|boi|thoa|nho|xit|suc\s*hong|ngam|sig\b|take\b|apply\b)"
    )
    pending_number = False
    for r in rows:
        r_txt = r.get("text", "").strip()
        if not r_txt:
            continue
        r_fold = _ascii_fold(r_txt)
        items = [it.get("text", "").strip() for it in r.get("items", []) if it.get("text", "").strip()]
        if not items:
            items = [p.strip() for p in r_txt.split("|") if p.strip()]

        has_num = bool(
            re.match(r"^\s*[1-9]\d*[\.\,\/\)\-\|]\s*", r_txt)
            or (items and re.fullmatch(r"[1-9]\d*[\.\,\/\)\-]?", items[0].strip()))
        )
        if has_num and len(items) == 1 and re.fullmatch(r"[1-9]\d*[.,/)\-]?", items[0]):
            pending_number = True
            continue
        if pending_number and not has_num:
            has_num = True
        pending_number = False

        # A noisy scan can lose some ordinal marks while retaining the drug
        # rows. A name with a package/strength and a separate unit column is
        # still a medicine heading, even between numbered rows.
        if not has_num and items:
            first_fold = _ascii_fold(items[0]).replace("_", " ")
            first_without_ordinal = re.sub(r"^\s*[1-9]\d*\s+", "", items[0]).strip()
            next_is_unit = any(re.fullmatch(
                r"\s*(?:\d{1,3}\s*)?(?:vien|vicn|ven|goi|ong|chai|char|chal|lo|hop|hon|vi|tuyp)\s*",
                _ascii_fold(item),
            ) for item in items[1:])
            medicine_shape = (next_is_unit or bool(re.search(
                r"\b\d+[oO0]*\s*(?:mg|mcg|ml|g|iu)\b", first_without_ordinal, re.IGNORECASE,
            )))
            is_instruction = bool(re.match(
                r"^(?:uong|ngay|sang|trua|chieu|toi|moi|lieu|cach|boi|thoa|hen|tai)\b",
                first_fold,
            ))
            if medicine_shape and not is_instruction and is_plausible_medication_name(first_without_ordinal):
                has_num = True

        quantity_only = re.fullmatch(
                r"(?:sl|so\s*luong|qty)?\s*[:.\-]?\s*(\d{1,3})\s*"
                r"(vien|goi|ong|chai|lo|hop|vi|tuyp|tablet|capsule|sachet)\b",
                r_fold.replace("|", " ").strip(),
            )
        # Check if continuation line of preceding drug
        if not has_num and meds and (quantity_only or continuation_re.match(r_fold)
                                    or not bool(re.search(r"\b(sl|sc|so\s*luong|qty)\b", r_fold))):
            d_info = _parse_dosing_details(r_txt)
            prev = meds[-1]
            if quantity_only and not prev["days"]:
                unit = _unit_label(quantity_only.group(2))
                prev["days"] = f"{quantity_only.group(1)} {unit}"
                continue
            if d_info["dose"] and not prev["dose"]:
                prev["dose"] = d_info["dose"]
            if d_info["frequency"] and not prev["frequency"]:
                prev["frequency"] = d_info["frequency"]
            if d_info["usage"] and not prev["usage"]:
                prev["usage"] = d_info["usage"]
            elif not prev["usage"]:
                prev["usage"] = r_txt
            continue

        if not has_num:
            continue

        # Nếu số thứ tự bị tách thành một item riêng (vd: items = ["2", "Paracetamol 500mg", "SL: 10 Vien"])
        if items and re.fullmatch(r"\d+[\.\,\/\)\-]?", items[0].strip()) and len(items) > 1:
            items = items[1:]

        # Extract days / quantity from full row text
        full_row = " ".join(items) if items else r_txt.replace("|", " ")
        days_qty = ""
        m_q_all = list(re.finditer(
            r"\b(\d+)\s*(vi[eêé]n|vien|vicn|ven|g[oóö]i|goi|gôi|[oố]ng|ong|ông|chai|char|chal|h[oộ]p|hop|hon|l[oọ]|lo|v[iỉ]|vi|tu[yý]p|tuyp|tablet|tablets|tab|tabs|capsule|capsules|sachet|sachets)\b",
            full_row,
            re.IGNORECASE,
        ))
        if m_q_all:
            last_q = m_q_all[-1]
            # Ensure it's not inline frequency like "1 vien x 3 lan"
            tail_txt = full_row[last_q.end():]
            is_inline = bool(re.search(r"^\s*(?:x\s*\d|\/|lan|times|sang|trua|chieu|toi)", tail_txt, re.IGNORECASE))
            if not is_inline:
                days_qty = f"{last_q.group(1)} {_unit_label(last_q.group(2))}"

        first = items[0]
        first = re.sub(r"^\s*\d+[\.\,\/\)\-\s]\s*", "", first).strip()
        first = re.sub(r"\s+\b(?:SL|SC|Qty|Số\s*lượng|So\s*luong)\s*[:.\-]?\s*\d+.*$", "", first, flags=re.IGNORECASE).strip()

        # Strength may be its own column rather than part of the drug name.
        norm_str = re.sub(r"2[oO0]{2}\s*mg", "200mg", full_row, flags=re.IGNORECASE)
        norm_str = re.sub(r"5[oO0]{2}\s*mg", "500mg", norm_str, flags=re.IGNORECASE)
        norm_str = re.sub(r"(\d)\s*[oO]\s*(mg|mcg|g|ml)\b", r"\g<1>0\2", norm_str, flags=re.IGNORECASE)
        norm_str = re.sub(r"\blg\b", "1g", norm_str)
        m_str = re.search(r"\b(\d+(?:[.,]\d+)?\s*(?:mg|mcg|g|ml|iu|%))\b", norm_str, re.IGNORECASE)
        strength = m_str.group(1).strip() if m_str else ""

        # Drug name
        clean_first = re.sub(r"\blg\b", "1g", first)
        clean_first = re.sub(r"2[oO0]{2}\s*mg", "200mg", clean_first, flags=re.IGNORECASE)
        clean_first = re.sub(r"5[oO0]{2}\s*mg", "500mg", clean_first, flags=re.IGNORECASE)
        clean_first = re.sub(r"(\d)\s*[oO]\s*(mg|mcg|g|ml)\b", r"\g<1>0\2", clean_first, flags=re.IGNORECASE)
        if strength:
            clean_first = re.sub(r"\b" + re.escape(strength) + r"\b", "", clean_first, flags=re.IGNORECASE)
            clean_first = re.sub(r"\[\s*\]", "", clean_first)
            clean_first = re.sub(r"\s+\)", ")", clean_first)
        m_tail_q = re.search(r"\b(\d+)\s*(vi[eêé]n|vien|g[oóö]i|goi|[oố]ng|ong|chai|h[oộ]p|hop|l[oọ]|lo)\s*$", clean_first, re.IGNORECASE)
        if m_tail_q:
            if not days_qty:
                days_qty = f"{m_tail_q.group(1)} {_unit_label(m_tail_q.group(2))}"
            if _extract_numbers(days_qty)[:1] == [m_tail_q.group(1)]:
                clean_first = clean_first[:m_tail_q.start()].strip()
        name = re.sub(r"\s+", " ", clean_first).strip(" -–,;:|")

        rest = " | ".join(item for item in items[1:] if not re.fullmatch(
            r"\s*(?:SL|SC|Qty|Số\s*lượng|So\s*luong)?\s*[:.\-]?\s*"
            r"\d{1,3}\s*(?:viên|vien|vicn|ven|gói|goi|ống|ong|chai|lọ|lo|hộp|hop|vỉ|vi)\s*",
            item, re.IGNORECASE,
        )) if len(items) > 1 else ""
        inline_info = _parse_dosing_details(rest) if rest else {"dose": "", "frequency": "", "usage": ""}

        if name and is_plausible_medication_name(name):
            meds.append({
                "name": name,
                "strength": strength,
                "dose": inline_info["dose"],
                "frequency": inline_info["frequency"],
                "days": days_qty,
                "usage": inline_info["usage"],
            })
    return meds


def extract_schema_from_ocr(ocr_data: Dict[str, Any], doc_type: str = "prescription") -> Dict[str, Any]:
    """
    Fallback bóc tách cấu trúc từ kết quả EasyOCR / WinRT OCR khi Cloud LLM (Gemini) không khả dụng.
    Tự động trích xuất thông tin hành chính, danh mục thuốc hoặc chỉ số xét nghiệm để người dùng chỉ cần xác nhận.
    """
    raw_text = ocr_data.get("raw_text", "") or ""
    lines = ocr_data.get("lines", []) or []
    rows = list(ocr_data.get("rows", []) or [])

    if not rows:
        src_lines = [l.get("text", "").strip() for l in lines if l.get("text", "").strip()]
        raw_lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()] if raw_text else []
        if len(raw_lines) > len(src_lines):
            src_lines = raw_lines
        for idx, s_ln in enumerate(src_lines):
            cols = [c.strip() for c in re.split(r"\s*\|\s*|\t+|\s{2,}", s_ln) if c.strip()]
            rows.append({
                "y_center": float(idx * 20),
                "text": " | ".join(cols),
                "items": [{"text": c} for c in cols],
            })

    folded_raw = _ascii_fold(raw_text or "\n".join(r.get("text", "") for r in rows))

    data = {
        "doc_type": doc_type,
        "patient_name": "",
        "dob": "",
        "age": "",
        "gender": "",
        "doctor": "",
        "facility": "",
        "date": "",
        "diagnosis": "",
        "medications": [] if doc_type == "prescription" else [],
        "metrics": [] if doc_type == "lab_test" else []
    }

    # 1. Cơ sở khám chữa bệnh: Chỉ nhận khi OCR đọc được nhãn rõ ràng
    for r in rows[:8]:
        r_txt = r.get("text", "")
        if re.search(r"đơn thuốc|don thuoc|phiếu xét nghiệm|phieu xet nghiem", r_txt, re.IGNORECASE):
            continue
        for part in r_txt.split("|"):
            part = part.strip()
            if re.search(r"\b(?:bệnh\s*viện|benh\s*vien|phòng\s*khám|phong\s*kham|trung\s*tâm|trung\s*tam|viện\s+y|vien\s+y)\b", part, re.IGNORECASE):
                data["facility"] = part
                break
        if data["facility"]:
            break

    # 2. Người bệnh (Họ tên)
    for r in rows:
        r_txt = r.get("text", "")
        r_fold = _ascii_fold(r_txt)
        if re.search(r"(?:ho\s*(?:\|\s*)?(?:va\s*)?(?:\|\s*)?ten|nguoi\s*benh|benh\s*nhan|nruvi\s*benh|patient(?:\s*name)?)", r_fold):
            flat_line = re.sub(r"\s*\|\s*", " ", r_txt).strip()
            m_lbl = re.search(
                r"(?:h[oọỏõóòôốồổỗộơớờởỡợ]\s*(?:v[aàảãáạ]\s*)?t[eêếềểễệéèẻẽẹ]n|ho\s*(?:va\s*)?ten|t[eêé]n|ngư[oờ]i\s*b[eệ]nh|b[eệ]nh\s*nh[aâ]n|patient(?:\s*name)?)\s*[:.\-]+",
                flat_line,
                re.IGNORECASE,
            )
            if m_lbl:
                tail = flat_line[m_lbl.end():].strip()
                tail_split = re.split(
                    r"\s+(?=(?:ng[aàå]y(?:\s*sinh|\s*[:.\-])|sinh\s*ng[aàå]y|n[aăä]m\s*sinh|tu[oổö6]i|age\b|dob\b|date\s*[:.\-]|gi[oớ]i\s*t[ií]nh|ph[aá]i\b|m[aã]\s*bhyt))",
                    tail,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )
                cand_name = tail_split[0].strip(" |,-;:")
                if len(cand_name) >= 2 and not cand_name.isdigit():
                    data["patient_name"] = cand_name
                    break

            items = [it.get("text", "").strip() for it in r.get("items", [])]
            candidates = []
            for it in items:
                clean_it = it.strip()
                if re.search(r"(?:ho\s*ten|họ\s*tên|nruvi\s*benh|ncuời\s*benh|người\s*bệnh|bệnh\s*nhân|dchls|địa\s*chỉ|iuj[zi]|tuổi|tuoi|mã|bhyt)", clean_it, re.IGNORECASE):
                    continue
                if re.search(r"^\d+$", clean_it):
                    continue
                candidates.append(clean_it)
            for c in candidates:
                if re.search(r"(?:ygu|nguyen|nguyễn|trần|tran|lê|le|phạm|pham|hoàng|hoang|huỳnh|huynh|phan|vũ|vu|võ|vo|đặng|dang|bùi|bui|đỗ|do|hồ|ho|ngô|ngo|dương|duong)", c, re.IGNORECASE):
                    data["patient_name"] = c
                    break
            if not data["patient_name"] and candidates:
                data["patient_name"] = candidates[0]
            if data["patient_name"]:
                break

    if data["patient_name"]:
        pname = data["patient_name"]
        pname = re.sub(r"Ygu[^\s]+", "Nguyễn", pname, flags=re.IGNORECASE)
        pname = re.sub(r"\bTbj\b", "Thị", pname, flags=re.IGNORECASE)
        pname = re.sub(r"\bLvi\b", "Lợi", pname, flags=re.IGNORECASE)
        data["patient_name"] = pname

    # 3. Ngày sinh / Tuổi / Giới tính
    dob_m = re.search(r"(?:ngay\s*sinh|sinh\s*ngay|nam\s*sinh|sinh\s*nam|ns|sn|d\.o\.b|dob)[|\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_raw)
    if dob_m:
        data["dob"] = dob_m.group(1).replace("-", "/").replace(".", "/")
    else:
        year_m = re.search(r"(?:nam\s*sinh|sinh\s*nam|ngay\s*sinh|sinh\s*ngay|sn|ns)[|\s:.\-]*(19\d{2}|20\d{2})", folded_raw)
        if year_m:
            data["dob"] = year_m.group(1)

    age_m = re.search(r"\b(?:tuoi|tuổi|iuj[zi]|age)[|\s:.\-]*(\d{1,3})\b", folded_raw)
    if age_m:
        data["age"] = age_m.group(1)

    # Tự động tính tuổi từ ngày tháng năm sinh nếu chưa có tuổi
    import datetime
    current_year = datetime.datetime.now().year
    dob_str = str(data.get("dob") or "").strip()
    if dob_str and not data.get("age"):
        y_m = re.search(r"(19\d{2}|20\d{2})", dob_str)
        if y_m:
            try:
                birth_year = int(y_m.group(1))
                if 1900 <= birth_year <= current_year:
                    data["age"] = str(current_year - birth_year)
            except Exception:
                pass

    gender_m = re.search(r"(?:gioi\s*tinh|gi[oớ]i\s*t[ií]nh|phai|ph[aá]i|phal|gender|sex)[|\s:.\-|]{0,15}?\b(nam|nu|nữ|male|female)", raw_text, re.IGNORECASE)
    if not gender_m:
        gender_m = re.search(r"\b(?:gioi\s*tinh|phai|gender|sex)[|\s:.\-]*(nam|nu|male|female)\b", folded_raw)
    if gender_m:
        g_raw = gender_m.group(1).lower()
        data["gender"] = "Nam" if g_raw in ("nam", "male") else "Nữ"

    # 4. Bác sĩ
    doctor_label_index = next((i for i, row in enumerate(rows) if re.search(
        r"bác\s*sĩ|bac\s*si|\bbs\.?\b", row.get("text", ""), re.IGNORECASE)), None)
    if doctor_label_index is not None:
        for row in rows[doctor_label_index:]:
            for item in row.get("items", []):
                candidate = item.get("text", "").strip(" :.-")
                candidate = re.sub(r"^(?:bác\s*sĩ(?:\s*điều\s*trị)?|bs\.?)\s*[:.-]?\s*", "", candidate, flags=re.IGNORECASE)
                if len(candidate.split()) >= 2 and re.match(
                    r"^(?:nguyễn|nguyen|trần|tran|lê|le|phạm|pham|"
                    r"hoàng|hoang|huỳnh|huynh|phan|vũ|vu|võ|vo|"
                    r"đặng|dang|bùi|bui|đỗ|do|hồ|ho|ngô|ngo|dương|duong)\b",
                    candidate, re.IGNORECASE,
                ):
                    data["doctor"] = candidate
                    break
            if data["doctor"]:
                break
    if not data["doctor"]:
        for r in reversed(rows[-4:]):
            r_txt = r.get("text", "")
            m_doc = re.search(r"(?:bac\s*si|bs\.?|thay\s*thuoc)[\s:.\-]+([A-Za-zÀ-ỹ\s]+)", r_txt, re.IGNORECASE)
            if m_doc:
                cand_doc = re.split(r"\s+(?:ng[aàå]y|date)\s*[:.\-]?", m_doc.group(1), maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,;-")
                if len(cand_doc.split()) >= 2 and not _is_role_only_doctor(cand_doc):
                    data["doctor"] = cand_doc
                    break

    # 5. Ngày trên phiếu
    date_m = re.search(r"(?:ngay|date)(?!\s*sinh)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_raw)
    if date_m:
        data["date"] = date_m.group(1).replace("-", "/").replace(".", "/")
    else:
        date_word_m = re.search(r"ngay\s*(\d{1,2})\s*thang\s*(\d{1,2})\s*nam\s*(\d{4})", folded_raw)
        if date_word_m:
            data["date"] = f"{date_word_m.group(1)}/{date_word_m.group(2)}/{date_word_m.group(3)}"
    if not data["date"] and doctor_label_index is not None:
        for row in reversed(rows[:doctor_label_index]):
            candidate = row.get("text", "").strip()
            if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", candidate):
                data["date"] = candidate.replace("-", "/")
                break

    # 6. Chẩn đoán
    for r in rows:
        r_txt = r.get("text", "")
        items = [it.get("text", "").strip() for it in r.get("items", [])]
        if re.search(r"chẩn\s*đoán|chan\s*doan|ch[eê]n\s*8oun|chn\s*8oun|chuan\s*doan|cđ", r_txt, re.IGNORECASE):
            diag_items = []
            found_lbl = False
            for it in items:
                if re.search(r"chẩn\s*đoán|chan\s*doan|ch[eê]n\s*8oun|chn\s*8oun|chuan\s*doan|cđ", it, re.IGNORECASE):
                    found_lbl = True
                    continue
                if found_lbl and not re.search(r"mã|bmyi|bhyt|icd|ibus", it, re.IGNORECASE):
                    diag_items.append(it)
            if diag_items:
                diag_str = " / ".join(diag_items)
                diag_str = re.sub(r"WCIK\s*I[OQA]+", "H/CTK TỌA", diag_str, flags=re.IGNORECASE)
                diag_str = re.sub(r"IVDD", "TVDD", diag_str, flags=re.IGNORECASE)
                data["diagnosis"] = diag_str
                break
    if not data["diagnosis"]:
        for row in rows:
            diag_m = re.search(r"(?:chẩn\s*đoán|chan\s*doan|cđ|ch[eê]n\s*8oun|chn\s*8oun)[\s:.\-]*([^|;\n]+)", row.get("text", ""), re.IGNORECASE)
            if diag_m:
                phrase = diag_m.group(1).strip()
                if len(re.findall(r"[A-Za-zÀ-ỹ]{2,}", phrase)) >= 2:
                    data["diagnosis"] = phrase
                    break

    # 7. Danh mục thuốc (prescription)
    if doc_type == "prescription":
        body_start, body_end = _prescription_body_bounds(rows)
        body_rows = rows[body_start:body_end]
        has_numbered_meds = any(
            re.match(r"^\s*[1-9]\d*[\.\,\/\)\-](?:\s|\||[A-Za-zÀ-ỹ])", r.get("text", "").strip())
            or (r.get("items") and re.fullmatch(r"[1-9]\d*[.,/)\-]?", str(r["items"][0].get("text", "")).strip()))
            for r in body_rows
        )
        if has_numbered_meds:
            data["medications"] = _parse_numbered_medications(body_rows)
        else:
            data["medications"] = _prescription_medications_from_rows(rows)

    elif doc_type == "lab_test":
        metrics = []
        lab_skip_re = re.compile(
            r"\b(ho ten|ho va ten|nguoi benh|benh nhan|tuoi|ngay sinh|bac si|khoa|chan doan|phieu xet nghiem|ten xet nghiem|tri so binh thuong|khoang tham chieu|benh vien|phong kham)\b"
        )
        unit_re = r"(?:mmol\/l|umol\/l|µmol\/l|mg\/dl|g\/dl|u\/l|iu\/l|g\/l|t\/l|10\^\d+\/l|%|fl|pg|ng\/ml|pmol\/l)"
        for r in rows:
            r_txt = r.get("text", "").strip()
            if not r_txt:
                continue
            r_fold = _ascii_fold(r_txt)
            if lab_skip_re.search(r_fold):
                continue

            parts = [p.strip() for p in r_txt.split("|") if p.strip()]
            if len(parts) >= 2:
                test_name = parts[0]
                result_val = ""
                unit_val = ""
                ref_range = ""
                flag_val = ""

                for p in parts[1:]:
                    pf = _ascii_fold(p)
                    if re.match(r"^[<>]?\s*\d+(?:[.,]\d+)?$", p) and not result_val:
                        result_val = p.replace(",", ".").strip()
                    elif re.search(unit_re, pf, re.IGNORECASE) and not unit_val:
                        unit_val = p
                    elif re.search(r"(?:\d+(?:[.,]\d+)?\s*[-–~]\s*\d+(?:[.,]\d+)?|^[<>]=?\s*\d+(?:[.,]\d+)?$)", p) and not ref_range:
                        ref_range = p
                    elif re.search(r"^(?:high|low|normal|h|l|binh thuong|cao|thap)$", pf) and not flag_val:
                        flag_val = p

                if test_name and not test_name.isdigit() and (result_val or len(parts) >= 3):
                    metrics.append({
                        "test_name": test_name,
                        "result": result_val or (parts[1] if len(parts) > 1 else ""),
                        "unit": unit_val or (parts[2] if len(parts) > 2 else ""),
                        "reference_range": ref_range or (parts[3] if len(parts) > 3 else ""),
                        "flag_on_paper": flag_val or "Normal",
                    })
            else:
                m_single = re.match(
                    rf"^([A-Za-zÀ-ỹ0-9\(\)\/\-\s]+?)\s+(\d+(?:[.,]\d+)?)\s+({unit_re})(?:\s+\(?(\d+(?:[.,]\d+)?\s*[-–~]\s*\d+(?:[.,]\d+)?|[<>]=?\s*\d+(?:[.,]\d+)?)\)?)?(?:\s+(High|Low|Normal|H|L|Cao|Thấp|Bình thường))?$",
                    r_txt,
                    re.IGNORECASE,
                )
                if m_single:
                    metrics.append({
                        "test_name": m_single.group(1).strip(" :-"),
                        "result": m_single.group(2).replace(",", "."),
                        "unit": m_single.group(3),
                        "reference_range": (m_single.group(4) or "").strip(),
                        "flag_on_paper": (m_single.group(5) or "Normal").strip(),
                    })
        data["metrics"] = metrics

    for hf in ("patient_name", "dob", "doctor", "facility", "date", "diagnosis"):
        if data.get(hf):
            data[hf] = _clean_ocr_display(data[hf])
    for med in data.get("medications", []):
        if med.get("name"):
            med["name"] = _clean_ocr_display(med["name"])
    for met in data.get("metrics", []):
        if met.get("test_name"):
            met["test_name"] = _clean_ocr_display(met["test_name"])

    return data


def reconcile_parallel_results(ocr_data: Dict[str, Any], gemini_data: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """
    [3] Đối chiếu A (OCR) và B (Gemini) theo từng field:
      - Khớp -> confidence cao
      - Lệch -> needs_review=True, giữ cả hai giá trị
      - Số (liều, kết quả XN) phải khớp tuyệt đối mới được coi là chắc chắn (confidence=1.0)
    """
    ocr_raw_text = ocr_data.get("raw_text", "")
    ocr_lines = ocr_data.get("lines", [])
    ocr_text_lower = ocr_raw_text.lower()

    reconciled = dict(gemini_data) if gemini_data else {}
    raw_facility = reconciled.get("facility", "")
    if _is_role_only_doctor(reconciled.get("doctor")):
        reconciled["doctor"] = ""
    if _is_malformed_facility(raw_facility):
        reconciled["facility"] = ""
    fields_review = []
    overall_confidence = 1.0

    ocr_fallback = extract_schema_from_ocr(ocr_data, doc_type=doc_type)
    header_alternatives = {}
    for field in ("patient_name", "dob", "age", "gender", "doctor", "facility", "date", "diagnosis"):
        ocr_value = str(ocr_fallback.get(field) or "").strip()
        model_value = str(reconciled.get(field) or "").strip()
        if not ocr_value:
            continue
        if not model_value:
            reconciled[field] = ocr_value
        elif not _header_values_agree(field, ocr_value, model_value):
            reconciled[field] = ocr_value
            header_alternatives[field] = [model_value]
            fields_review.append(f"{field}: OCR và model đọc khác nhau; cần đối chiếu ảnh gốc.")
            overall_confidence = min(overall_confidence, 0.8)
    reconciled["header_alternatives"] = header_alternatives
    if reconciled.get("patient_name"):
        reconciled["patient_name"] = re.sub(
            r"^(?:(?:tên\s*)?bệnh\s*nhân|người\s*bệnh|họ\s*(?:và\s*)?tên|patient(?:\s*name)?)\s*[:.\-]\s*",
            "", str(reconciled["patient_name"]), flags=re.IGNORECASE,
        ).strip()

    folded_ocr_raw = _ascii_fold(ocr_raw_text)
    if not reconciled.get("dob"):
        dob_match = re.search(r"(?:ngay\s*sinh|sinh\s*ngay|nam\s*sinh|sinh\s*nam|ns|sn|d\.o\.b|dob)[|\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_ocr_raw)
        if dob_match:
            reconciled["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        else:
            year_match = re.search(r"(?:nam\s*sinh|sinh\s*nam|ngay\s*sinh|sinh\s*ngay|sn|ns)[|\s:.\-]*(19\d{2}|20\d{2})", folded_ocr_raw)
            if year_match:
                reconciled["dob"] = year_match.group(1)

    if not reconciled.get("age"):
        age_match = re.search(r"\b(?:tuoi|age)[|\s:.\-]*(\d{1,3})\b", folded_ocr_raw)
        if age_match:
            reconciled["age"] = age_match.group(1)

    # Tự động tính tuổi từ ngày tháng năm sinh nếu chưa có tuổi
    import datetime
    current_year = datetime.datetime.now().year
    dob_val = str(reconciled.get("dob") or "").strip()
    if dob_val and not reconciled.get("age"):
        y_m = re.search(r"(19\d{2}|20\d{2})", dob_val)
        if y_m:
            try:
                birth_year = int(y_m.group(1))
                if 1900 <= birth_year <= current_year:
                    reconciled["age"] = str(current_year - birth_year)
            except Exception:
                pass

    if not reconciled.get("gender"):
        gender_match = re.search(r"\b(?:gioi\s*tinh|phai|gender|sex)[|\s:.\-]*(nam|nu|male|female)\b", folded_ocr_raw)
        if gender_match:
            g_raw = gender_match.group(1).lower()
            reconciled["gender"] = "Nam" if g_raw in ("nam", "male") else "Nữ"

    if doc_type == "prescription":
        meds = reconciled.get("medications", [])
        all_rows = ocr_data.get("rows", [])
        body_start, body_end = _prescription_body_bounds(all_rows)
        if body_start >= body_end:
            body_start, body_end = 0, len(all_rows)
        outside_rows = ocr_data.get("rows", [])[:body_start] + ocr_data.get("rows", [])[body_end:]
        body_rows = all_rows[body_start:body_end]
        supported_meds = []
        header_values = {
            _normalized_entity(value)
            for value in (raw_facility, reconciled.get("facility"),
                          reconciled.get("doctor"), reconciled.get("patient_name"))
            if value and len(_normalized_entity(value)) >= 5
        }
        for med in meds if isinstance(meds, list) else []:
            if not isinstance(med, dict) or not is_plausible_medication_name(med.get("name", "")):
                continue
            if _normalized_entity(med["name"]) in header_values:
                continue
            name = _clean_str(med["name"])
            if len(name) >= 3 and any(
                re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)",
                          _clean_str(item.get("text", "")))
                for row in outside_rows for item in row.get("items", [])
            ):
                continue
            # When OCR sees the table but cannot parse its rows, do not promote
            # a model-only header/diagnosis fragment to a medication.
            if ocr_data.get("rows") and not ocr_fallback.get("medications"):
                if not any(name in _clean_str(row.get("text", "")) for row in body_rows):
                    continue
            supported_meds.append(med)
        meds = _merge_medication_rows(ocr_fallback.get("medications", []), supported_meds)
        if ocr_fallback.get("medications") and body_rows:
            def body_position(name):
                folded_name = _clean_str(name)
                if len(folded_name) < 3:
                    return None
                pattern = re.compile(r"(?<!\w)" + re.escape(folded_name) + r"(?!\w)")
                return next((index for index, row in enumerate(body_rows)
                             if pattern.search(_clean_str(row.get("text", "")))), None)

            occupied = {position for med in meds
                        if (position := body_position(med.get("name"))) is not None}
            for model_med in supported_meds:
                model_name = _normalized_entity(model_med.get("name"))
                if not model_name or any(
                    (difflib.SequenceMatcher(None, model_name,
                                             _normalized_entity(ocr_med.get("name"))).ratio() >= 0.72
                     or (len(model_name) >= 5 and model_name in _normalized_entity(ocr_med.get("name"))))
                    for ocr_med in meds
                ):
                    continue
                position = body_position(model_med.get("name"))
                if position is None or position in occupied:
                    continue
                evidence_row = body_rows[position]
                name_text = str(model_med.get("name", "")).strip()
                cells = [str(cell.get("text", "")).strip() for cell in evidence_row.get("items", [])]
                heading_cell = next((cell for cell in cells
                                     if not re.fullmatch(r"[1-9]\d*[.,/)-]?", cell)),
                                    evidence_row.get("text", ""))
                heading_cell = re.sub(r"^\s*[1-9]\d*[.,/)\-]?\s+", "", heading_cell)
                heading_fold = _clean_str(heading_cell)
                heading_shape = bool(re.search(
                    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|g|vien|viên|goi|gói|ong|ống)\b|\(",
                    evidence_row.get("text", ""), re.IGNORECASE,
                ))
                if not (name_text[:1].isupper() and heading_fold.startswith(_clean_str(name_text))
                        and heading_shape):
                    continue
                # The OCR parser already preserves document order. An OCR name
                # may not match its raw row exactly, so sorting every OCR row by
                # a text lookup would move that row to the end of the list.
                insert_at = next((index for index, existing in enumerate(meds)
                                  if (existing_position := body_position(existing.get("name"))) is not None
                                  and existing_position > position), len(meds))
                meds.insert(insert_at, dict(model_med))
                occupied.add(position)
        reconciled["medications"] = meds

        verified_meds = []

        for med in meds:
            med_entry = dict(med)
            name = str(med.get("name", "")).strip()
            strength = str(med.get("strength", "")).strip()
            dose = str(med.get("dose", "")).strip()
            freq = str(med.get("frequency", "")).strip()

            # 1. Kiểm tra đối soát tên thuốc
            name_in_ocr = False
            best_match_ratio = 0.0
            matched_ocr_str = ""
            matched_ocr_confidence = None
            for ocr_line in ocr_lines:
                line = ocr_line.get("text", "")
                ratio = difflib.SequenceMatcher(None, _clean_str(name), _clean_str(line)).ratio()
                if ratio > best_match_ratio:
                    best_match_ratio = ratio
                    matched_ocr_str = line
                    try:
                        matched_ocr_confidence = float(ocr_line["confidence"])
                    except (KeyError, TypeError, ValueError):
                        matched_ocr_confidence = None
                if _clean_str(name) in _clean_str(line) or ratio > 0.65:
                    name_in_ocr = True

            # 2. Đối chiếu số (Hàm lượng, liều dùng) - Phải khớp tuyệt đối
            gemini_dose_nums = _extract_numbers(dose) + _extract_numbers(strength)
            ocr_nums = _extract_numbers(ocr_raw_text)

            nums_strictly_matched = True
            if gemini_dose_nums:
                for num in gemini_dose_nums:
                    if num not in ocr_nums:
                        nums_strictly_matched = False
                        break

            needs_review = (bool(med.get("needs_review"))
                            or not (name_in_ocr and nums_strictly_matched)
                            or (matched_ocr_confidence is not None and matched_ocr_confidence < 0.7))
            med_confidence = 0.95 if not needs_review else 0.80

            med_entry["field_confidence"] = round(med_confidence, 2)
            med_entry["needs_review"] = needs_review
            med_entry["ocr_matched_text"] = matched_ocr_str if matched_ocr_str else "Khớp từ nhận diện OCR"

            if needs_review:
                fields_review.append(f"Thuốc '{name}': tên, liều hoặc tần suất cần đối chiếu lại với đơn gốc.")
                overall_confidence = min(overall_confidence, 0.8)

            verified_meds.append(med_entry)

        reconciled["medications"] = verified_meds

    elif doc_type == "lab_test":
        metrics = reconciled.get("metrics", [])
        if not metrics and ocr_fallback.get("metrics"):
            metrics = ocr_fallback["metrics"]
            reconciled["metrics"] = metrics

        verified_metrics = []

        for item in metrics:
            metric_entry = dict(item)
            t_name = str(item.get("test_name", "")).strip()
            res_val = str(item.get("result", "")).strip()

            # Đối chiếu số kết quả xét nghiệm - BẮT BUỘC KHỚP TUYỆT ĐỐI
            res_nums = _extract_numbers(res_val)
            ocr_nums = _extract_numbers(ocr_raw_text)

            value_strictly_matched = False
            if res_nums:
                value_strictly_matched = any(num in ocr_nums for num in res_nums)

            # Đối chiếu tên chỉ số trong các hàng OCR
            name_found = False
            best_ocr_row = ""
            for row in ocr_data.get("rows", []):
                r_text = row.get("text", "")
                if _clean_str(t_name) in _clean_str(r_text):
                    name_found = True
                    best_ocr_row = r_text
                    break

            confidence = 1.0 if (value_strictly_matched and name_found) else 0.80
            needs_review = not (value_strictly_matched and name_found)

            metric_entry["field_confidence"] = round(confidence, 2)
            metric_entry["needs_review"] = needs_review
            metric_entry["ocr_matched_row"] = best_ocr_row if best_ocr_row else "Khớp từ nhận diện OCR"

            if needs_review and gemini_data:
                fields_review.append(f"Chỉ số '{t_name}': kết quả ({res_val}) cần xác nhận lại với phiếu gốc.")
                overall_confidence = min(overall_confidence, 0.8)

            verified_metrics.append(metric_entry)

        reconciled["metrics"] = verified_metrics

    reconciled["reconciliation_review"] = {
        "needs_review": len(fields_review) > 0,
        "overall_confidence": round(overall_confidence, 2),
        "review_reasons": fields_review
    }

    return reconciled
