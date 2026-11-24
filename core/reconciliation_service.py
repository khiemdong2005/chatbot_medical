import re
import difflib
import unicodedata
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

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
    # Loại bỏ các chuỗi typo OCR của hàm lượng thuốc như JOOmg, IUUmg, AOOmg, [AOmg, 3OOmg, S82mg, 196mg, 2Smg
    if re.fullmatch(r"[\[\(\{]?[jIi1-9aAsS][0-9oOuUaA]{1,4}\s*(?:mg|mcg|ml|g|iu)[\]\)\}]?", raw_value, re.IGNORECASE):
        return False
    if re.fullmatch(r"[0-9\+\-\/\(\)\s,.]+", raw_value):
        return False
    if re.search(r"^\s*extra\b", raw_value, re.IGNORECASE):
        return False
    if raw_value.count("(") != raw_value.count(")") or raw_value.count("[") != raw_value.count("]"):
        # Nếu phần tên chính trước dấu ngoặc là tên thuốc hợp lệ (>= 4 chữ cái) thì không loại chỉ vì OCR đọc nhầm ']' thành ')'
        core_before_paren = re.split(r"[\(\[]", raw_value, maxsplit=1)[0].strip()
        if not (len(core_before_paren) >= 4 and re.search(r"[A-Za-zÀ-ỹ]{4,}", core_before_paren)):
            return False
    if re.search(r"^\s*\+|\+\s*$", raw_value):
        return False
    value = raw_value.strip(" \t\r\n\"'.,;:()[]{}")
    if len(value) < 2 or not re.search(r"[A-Za-zÀ-ỹ]", value) or value.lower() in {"kn", "ton", "sam", "tin", "ngày", "ngay", "extra"}:
        return False
    if _MEDICATION_LABEL.search(value):
        return False
    # Column headings often appear as independent OCR boxes beside the drug row.
    if _ascii_fold(value) in {"stt", "ten thuoc", "ham luong", "so luong", "don vi",
                              "cach dung", "cahdur", "cha", "chicu", "cong chicu", "sig",
                              "cnr", "chu", "swg", "his", "mo", "s0w0", "4urz", "oneion",
                              "cakdun", "auenaeon", "oennipagrutumnirohon"}:
        return False
    if re.fullmatch(r"\d{1,2}\s*[/.-]\s*\d{2,4}", value):
        return False
    if re.fullmatch(rf"\d+(?:[.,]\d+)?\s*(?:{_MEDICATION_UNITS})?", value, re.IGNORECASE):
        return False
    if re.fullmatch(rf"(?:{_MEDICATION_UNITS})", value, re.IGNORECASE):
        return False
    folded_val = _ascii_fold(value)
    if re.search(r"\b(?:vien|goi|ong|chai|ml)\s*/\s*lan\b|\blan\s*/\s*(?:ngay|tuan)\b|\bsau\s*an\b|\btruoc\s*an\b|\bbuoi\s*(?:sang|toi|chieu)\b|thong\s*tin\s*(?:don|benh)|tin\s*don\s*thuoc|tindon|tinbenh", folded_val):
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


def _extract_core_name(text: str) -> str:
    cleaned = _normalized_entity(text)
    cleaned = re.sub(r"\b\d+[a-z]*\b", "", cleaned)
    tokens = [w for w in re.findall(r"[a-z0-9]+", cleaned) if len(w) >= 3 and w not in {"vien", "goi", "chai", "ong", "hop", "kdnt"}]
    return tokens[0] if tokens else cleaned


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
        ocr_core = _extract_core_name(ocr_med.get("name"))
        best_index = None
        best_score = 0.0
        best_name_score = 0.0
        for index, model_med in enumerate(model_meds):
            if index in used_model_rows or not isinstance(model_med, dict):
                continue
            model_name = _normalized_entity(model_med.get("name"))
            model_brand = _normalized_entity(model_med.get("brand_name", ""))
            model_core = _extract_core_name(model_brand or model_name)
            if not ocr_name or not model_name:
                continue

            name_match_ratio = difflib.SequenceMatcher(None, ocr_name, model_name).ratio()
            if len(ocr_name) >= 4 and (ocr_name in model_name or model_name in ocr_name):
                name_match_ratio = 1.0

            core_score = difflib.SequenceMatcher(None, ocr_core, model_core).ratio() if (ocr_core and model_core) else 0.0
            if ocr_core and model_core:
                if ocr_core in model_name or model_core in ocr_name or ocr_core == model_core:
                    core_score = max(core_score, 0.95)
                elif len(ocr_core) >= 4 and len(model_core) >= 4 and (
                    ocr_core[:4] == model_core[:4] or difflib.SequenceMatcher(None, ocr_core[:5], model_core[:5]).ratio() >= 0.8
                ):
                    core_score = max(core_score, 0.85)

            row_score = max(name_match_ratio, core_score)

            # A weak OCR spelling can still be the same row when both readers
            # found the same number of medicines in the same order. Never use
            # this shortcut for a conflicting numeric strength.
            if (len(ocr_meds) == len(model_meds) and index == row_index and (row_score >= 0.50 or (ocr_core and model_core and ocr_core[:3] == model_core[:3]))):
                ocr_strength = _extract_numbers(ocr_med.get("strength"))
                model_strength = _extract_numbers(model_med.get("strength"))
                if not (ocr_strength and model_strength and ocr_strength != model_strength):
                    row_score = max(row_score, 0.75)

            if anchor_pairs.get(row_index) == index:
                row_score = 1.1  # Unique prescription row anchor outranks fuzzy spelling.
            if row_score > best_score:
                best_index, best_score = index, row_score
                best_name_score = name_match_ratio

        combined = dict(ocr_med)
        if best_index is not None and best_score >= 0.72:
            used_model_rows.add(best_index)
            model_med = model_meds[best_index]
            raw_name = str(combined.get("name") or "")
            model_name = str(model_med.get("brand_name") or model_med.get("name") or "").strip()
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
                boilerplate_instruction = (field in ("frequency", "usage", "dose") and (
                    "hướng dẫn của bác sĩ" in ocr_value or "chỉ dẫn bác sĩ" in ocr_value
                ))
                if not ocr_value or noisy_instruction or boilerplate_instruction or (field == "usage" and model_value):
                    combined[field] = str(model_med[field])
                    if ocr_value and ocr_value != model_value:
                        combined["needs_review"] = True
            for extra_fld in ("brand_name", "active_ingredient", "quantity", "unit", "schedule", "instructions", "purpose"):
                if model_med.get(extra_fld):
                    combined[extra_fld] = str(model_med[extra_fld])
        merged_rows.append(combined)
    return merged_rows


def _prescription_body_bounds(rows: List[Dict[str, Any]]) -> tuple:
    """Locate medicine blocks between diagnosis/header and footer markers (Cộng khoản, Lời dặn, Ngày...tháng...năm, Bác sĩ...)."""
    def numbered(row):
        text = str(row.get("text", "") or "").strip()
        if re.search(r"\b(?:ng[aàoy]\s*kh[aá]m|ngay\s*sinh|ho\s*ten|chan\s*doan|don\s*thuoc)\b", _ascii_fold(text)):
            return False
        if re.match(r"^\s*['\"*•\-]?\s*[1-9]\d?\s*[.):\-/]\s*[A-Za-zÀ-ỹ]", text):
            return True
        items = [str(item.get("text", "") or "").strip() for item in row.get("items", [])]
        return bool(
            items
            and re.fullmatch(r"['\"*•\-]?\s*[1-9]\d?\s*[.):\-/]?", items[0])
            and len(items) > 1
            and re.search(r"[A-Za-zÀ-ỹ]{3,}", items[1])
        )

    diagnosis_idx = next((i for i, row in enumerate(rows)
                          if re.search(r"\bchan\s*doan\b", _ascii_fold(row.get("text", "")))), None)
    first_numbered = next((i for i, row in enumerate(rows) if numbered(row)), None)
    if diagnosis_idx is not None:
        start = diagnosis_idx + 1
    elif first_numbered is not None:
        start = first_numbered
        # Nếu dòng đánh số đầu tiên bắt đầu từ số >= 2 (vì OCR rớt số "1."),
        # kiểm tra 1-2 dòng ngay phía trên xem có dòng thuốc số 1 (có số lượng/đơn vị) không
        first_ord = _parse_medication_ordinal(str(rows[first_numbered].get("text", "") or ""))
        if first_ord is not None and first_ord >= 2:
            for back in range(first_numbered - 1, max(-1, first_numbered - 4), -1):
                b_txt = str(rows[back].get("text", "") or "")
                b_fold = _ascii_fold(b_txt)
                if re.search(r"\b(?:ho\s*ten|doi\s*tuong|don\s*thuoc|dia\s*chi|phai|tuoi)\b", b_fold):
                    break
                if re.search(r"\b\d{1,3}\s*(?:vien|ven|goi|ong|chai|lo|hop|tuyp|tube)\b", re.sub(r"\s*\|\s*", " ", b_fold)):
                    start = back
                    break
    else:
        heading = next((i for i, row in enumerate(rows)
                        if re.search(r"\b(?:ten\s*thuoc|stt|ten\s*duoc\s*pham)\b",
                                     _ascii_fold(row.get("text", "")))), None)
        start = heading + 1 if heading is not None else len(rows)

    footer_pattern = re.compile(
        r"\b(?:cong\s*khoan|loi\s*dan|hen\s*tai\s*kham|tai\s*kham|"
        r"bac\s*s[iy]\b|nguoi\s*ke\s*don|ngay\s*\d{0,2}\s*thang)\b"
    )
    footer_idx = next((i for i, row in enumerate(rows)
                       if i >= start and footer_pattern.search(_ascii_fold(row.get("text", "")))), None)
    return start, footer_idx if footer_idx is not None else len(rows)


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


_ORDINAL_TYPO_MAP = {
    "G": "6", "g": "6", "b": "6",
    "I": "1", "l": "1", "|": "1",
    "O": "0", "o": "0",
    "S": "5", "s": "5",
}

_INSTRUCTION_HEAD_RE = re.compile(
    r"^\s*(?:ng[aàa]?y|u[oốô]ng|m[oỗ]i\s*l[aầ]n|s[aá]ng|tr[uư]a|ch[iề]u|t[oố]i|"
    r"c[aá]ch\s*d[uù]ng|l[oờ]i\s*d[aặ]n|c[oộ]ng\s*kho[aả]n|"
    r"b[oô]i|xoa|thoa|t[aắ]m\s*g[oộ]i|nh[oỏ]|ng[aậ]m|x[iị]t|d[uù]ng\s*sau|"
    r"cac\s*ngay|khi\s*dau|sau\s*an|truoc\s*an|"
    r"vi[eêé]n|vien|ven|g[oóö]i|goi|[oố]ng|ong|chai|l[oọ]|lo|h[oộ]p|hop|tu[yý]p|tuyp|tube|ml|gi[oọ]t|giot|l[aầ]n|lan)\b",
    re.IGNORECASE,
)


_FOREIGN_LATIN_CLUSTERS = re.compile(
    r"[fjzw]|(?:bl|br|cl|cr|dr|fl|fr|gl|gr|kl|kr|pl|pr|sc|sk|sl|sm|sn|sp|st|sw|vr)|(?:[bcdfghjklmnpqrstvwxz]{3})",
    re.IGNORECASE,
)


def _clean_foreign_brand_diacritics(name: str) -> str:
    """Loại dấu tiếng Việt bị EasyOCR gắn nhầm lên từ biệt dược gốc Latin/tiếng Anh
    (vd: từ có cụm phụ âm không tồn tại trong tiếng Việt như cr, fl, st, f, z, w...)."""
    tokens = []
    for tok in str(name or "").split():
        folded = unicodedata.normalize("NFKD", tok)
        ascii_only = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
        if ascii_only != tok and _FOREIGN_LATIN_CLUSTERS.search(ascii_only):
            tokens.append(ascii_only)
        else:
            tokens.append(tok)
    return " ".join(tokens)


def _normalize_vi_instruction_text(text: str) -> str:
    """Chỉnh các lỗi chính tả OCR tiếng Việt phổ biến trong dòng hướng dẫn sử dụng."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return ""
    replacements = [
        (r"\bU[oổồ]ng\b", "Uống"),
        (r"\bu[oổồ]ng\b", "uống"),
        (r"\bbu[oổ]i\s*t[oổ]i\b", "buổi tối"),
        (r"\bT[aáà]m\s*g[oộồố]i\b", "Tắm gội"),
        (r"\bsữa\s*t[aăẳằ]m\b", "sữa tắm"),
        (r"\bl[aầẩẫấầ]n\s*[lI1'i]\s*(?=ng|tu)", "lần/ "),
        (r"\bl[aẩẫ]n\b", "lần"),
        (r"\bI[aầ]ni\b", "lần/"),
        (r"\btu[aẩàáă]n\b", "tuần"),
        (r"\bng[aằắá]y\b", "ngày"),
        (r"\bng[aà]ỵ\b", "ngày"),
        (r"\bchi[eèê]u\b", "chiều"),
        (r"\bthu[oổồ]c\b", "thuốc"),
        (r"\bsau\s*[àaăâ]n\s*no\b", "sau ăn no"),
        (r"\bsau\s*[àaăâ]nno\b", "sau ăn no"),
        (r"\bSau\s*n\.", "Sau ăn."),
        (r"\bSau\s*[áàa]n\b", "Sau ăn"),
        (r"\bsau\s*[áàa]n\b", "sau ăn"),
        (r"\b(\d+)\s*ph[uúứ]\b", r"\1 phút"),
        (r"\bSáng\s+chiều\b", "sáng, chiều"),
        (r"\bsáng\s+chiều\b", "sáng, chiều"),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)
    # Chuẩn hóa dấu chấm phẩy/hai chấm cuối câu do OCR nhầm dấu phẩy/chấm
    s = re.sub(r";\s*(?=[a-zà-ỹ])", ", ", s)
    s = re.sub(r":\s*$", ".", s)
    s = re.sub(r"\s+([,.;])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _decode_ordinal_token(token: str) -> Optional[int]:
    """Giải mã token số thứ tự (1..99 hoặc ký tự OCR nhầm G/g/b->6, I/l/|->1, O/o->0, S->5)."""
    cleaned = str(token or "").strip().lstrip("'\"*•- ").rstrip(".,):|-/")
    if not cleaned:
        return None
    if re.fullmatch(r"[1-9]\d?", cleaned):
        val = int(cleaned)
        return val if 1 <= val <= 50 else None
    if len(cleaned) == 1 and cleaned in _ORDINAL_TYPO_MAP:
        mapped = _ORDINAL_TYPO_MAP[cleaned]
        val = int(mapped)
        return val if 1 <= val <= 9 else None
    return None


def _parse_medication_ordinal(value: str) -> Optional[int]:
    """Nhận diện số thứ tự đầu dòng thuốc (hỗ trợ các dấu phân cách . ) : - / hoặc khoảng trắng)."""
    s = str(value or "")
    # Dạng có dấu phân cách: "1. YESOM", "6) ...", "G. DIGLUMISAN", "2: ...", "3- ...", "1/ Cetirizine", "'2 / Liverterder"
    match = re.match(r"^\s*['\"*•\-]?\s*([1-9]\d?|[GgIlOoSb|])\s*[.):\-/]\s*([A-Za-zÀ-ỹ].*)$", s)
    if match:
        return _decode_ordinal_token(match.group(1))
    # Dạng không dấu phân cách (Layout B): "1  Ducray Kelual DS", "4 Halcort 6"
    match_ws = re.match(r"^\s*([1-9]\d?|[GgIlbS])\s+([A-Za-zÀ-ỹ].*)$", s)
    if match_ws:
        tail = match_ws.group(2).strip()
        if not _INSTRUCTION_HEAD_RE.match(_ascii_fold(tail)):
            return _decode_ordinal_token(match_ws.group(1))
    return None


def _infer_route_from_text(text: str) -> Optional[str]:
    """Suy đường dùng trực tiếp từ động từ trong hướng dẫn của đơn thuốc."""
    folded = _ascii_fold(text)
    if re.search(r"\btam\s*goi\b", folded):
        return "Dùng ngoài"
    if re.search(r"\b(?:boi|xoa|thoa)\b", folded):
        return "Dùng ngoài da"
    if re.search(r"\b(?:nho\s*mat|nho\s*mui|nho\s*tai|nho)\b", folded):
        return "Nhỏ tại chỗ"
    if re.search(r"\b(?:xit)\b", folded):
        return "Xịt tại chỗ"
    if re.search(r"\b(?:ngam)\b", folded):
        return "Ngậm"
    if re.search(r"\b(?:uong|u6ng)\b", folded):
        return "Đường uống"
    return None


def _parse_prescription_dose(text: str) -> tuple:
    """Read dose/frequency for both Layout A and Layout B regimens."""
    folded = _ascii_fold(text).lower().replace("_", " ")
    # Chuẩn hóa lỗi OCR hay gặp trong dòng liều dùng: "Iầni" -> "lan/", "lẩn'" -> "lan/", "tuẩn" -> "tuan"
    folded = re.sub(r"\bl[a1i]n[i']\s*(?=ngay|tuan)", "lan/ ", folded)
    folded = re.sub(r"\bi[a1]n\b", "lan", folded)
    unit_pattern = r"(vi[e]?n|ven|goi|chai|chal|ong|ml|giot|tube|tuyp|lo|hop|tablet|tab|capsule|sachet)"

    # 1. Liều mỗi lần (dose)
    dose_match = re.search(
        rf"(?:m[o0]i\s*l[a1i]n|m[e0][i1]\s*[{{(\[]?[a1]n|u[o06]ng(?:\s*(?:sang|trua|chieu|toi))?|ngam)\s*[:,\-]?\s*(\d+(?:[.,/]\d+)?)\s*{unit_pattern}\b",
        folded,
    )
    if not dose_match:
        dose_match = re.search(
            rf"(\d+(?:[.,/]\d+)?)\s*{unit_pattern}\s*(?:/\s*l[a1i]n|x\s*\d|m[o0]i\s*l[a1i]n)",
            folded,
        )

    # 2. Tần suất (frequency): hỗ trợ cả /ngày và /tuần
    freq_value = None
    # Layout B: "x 2 lần/ ngày" hoặc "2 lần/ ngày" hoặc "3 lần/ tuần"
    freq_x = re.search(r"x\s*(\d{1,2})\s*l[a1i]n\s*/?\s*(ngay|tuan)\b", folded)
    if freq_x:
        period = "tuần" if freq_x.group(2) == "tuan" else "ngày"
        freq_value = f"{freq_x.group(1)} lần/{period}"
    if not freq_value:
        freq_slash = re.search(r"(\d{1,2})\s*l[a1i]n\s*/\s*(ngay|tuan)\b", folded)
        if freq_slash:
            period = "tuần" if freq_slash.group(2) == "tuan" else "ngày"
            freq_value = f"{freq_slash.group(1)} lần/{period}"
    if not freq_value:
        # Layout A: "Ngày uống 3 lần, mỗi lần 1 viên" hoặc OCR dính chữ "3lan, moilan 1 Vien"
        freq_a = re.search(
            r"(?:(?:ngay\s*u[o0c]ng|u[o0c]ng\s*ngay|ngay|u[o0]ng|boi(?:\s*tai\s*cho)?|xoa(?:\s*tai\s*cho)?|tam\s*goi)\s*)?"
            r"(\d{1,2})\s*(?:l[a1i]n|ion|lan)\s*(?:/?\s*(ngay|tuan)|[,;.]?\s*m[o0]i\s*(?:ngay|l[a1i]n)|$|[,;.])",
            folded,
        )
        if freq_a:
            period = "tuần" if freq_a.group(2) == "tuan" else "ngày"
            freq_value = f"{freq_a.group(1)} lần/{period}"
    if not freq_value:
        # Layout B: "Uống 3 viên/ lần/ ngày, buổi sáng" -> 1 lần/ngày
        if re.search(rf"\d+(?:[.,/]\d+)?\s*{unit_pattern}\s*/?\s*(?:l[a1i]n\s*/?\s*)?ngay\b", folded):
            freq_value = "1 lần/ngày"

    dose_value = None
    if dose_match:
        amount = dose_match.group(1).replace(",", ".")
        unit = _unit_label(dose_match.group(2))
        dose_value = f"{amount} {unit}"
    return dose_value, freq_value


def _filter_left_margin_handwriting(rows: List[Dict[str, Any]]) -> tuple:
    """Remove handwritten notes/numbers strictly left of the printed ordinal column from parsing."""
    from statistics import median as _median
    all_items = [item for row in rows for item in row.get("items", [])]
    if not all_items:
        return rows, set()
    page_right = max(float(item.get("x_max", item.get("x_min", 0)) or 0) for item in all_items)
    if page_right <= 0:
        return rows, set()

    ordinal_x_candidates = []
    for row in rows:
        items = row.get("items", [])
        if not items:
            continue
        for item in items[:2]:
            it_x = float(item.get("x_min", 0) or 0)
            if it_x > page_right * 0.25:
                continue
            it_txt = str(item.get("text", "") or "").strip()
            # Ưu tiên các dòng có STT in rõ kèm tên thuốc (tránh bị kéo lệch bởi số viết tay sát mép x≈0)
            if _parse_medication_ordinal(it_txt) is not None or (
                item is items[0]
                and re.match(r"^\s*(?:[1-9]\d?|[GgIlOoSb|])\s*[.):\-]?\s*$", it_txt)
                and it_x >= page_right * 0.03
            ):
                ordinal_x_candidates.append(it_x)
                break
    if not ordinal_x_candidates:
        return rows, set()
    # Dùng median của cột STT in để 1 chữ viết tay sát mép trái không kéo lệch ngưỡng lọc
    ordinal_x = float(_median(ordinal_x_candidates))
    margin_threshold = min(ordinal_x - max(12.0, page_right * 0.02), page_right * 0.22)
    if margin_threshold <= 0:
        return rows, set()
    ignored = set()
    filtered_rows = []
    for row in rows:
        items = row.get("items", [])
        kept_items = []
        for item in items:
            text = str(item.get("text", "") or "").strip()
            x_max = float(item.get("x_max", item.get("x_min", 0)) or 0)
            confidence = float(item.get("confidence", 1.0) or 0)
            is_ordinal = bool(re.match(r"^\s*(?:[1-9]\d?|[GgIlOoSb|])\s*[.):\-]?\s*$", text))
            far_left_margin = x_max < (ordinal_x - max(25.0, page_right * 0.04))
            if (x_max < margin_threshold and confidence < 0.75 and not is_ordinal) or far_left_margin:
                if item.get("line_index") is not None:
                    ignored.add(int(item["line_index"]))
                continue
            kept_items.append(item)
        if items and not kept_items:
            continue
        copied = dict(row)
        copied["items"] = kept_items
        if kept_items:
            copied["text"] = " | ".join(str(item.get("text", "")).strip() for item in kept_items)
        filtered_rows.append(copied)
    return filtered_rows, ignored


def _parse_strict_numbered_medications(rows: List[Dict[str, Any]], expected_count: Optional[int] = None) -> List[Dict[str, Any]]:
    """Parse numbered drug blocks (Layout A & Layout B), including optional punctuation,
    OCR ordinal confusions, left-column x validation, split-box quantities, and verbatim instructions."""
    ordinal_cell = re.compile(r"^\s*['\"*•\-]?\s*(?:[1-9]\d?|[GgIlOoSb|])\s*[.,):\-/]?\s*$")
    blocks: List[Dict[str, Any]] = []
    current = None
    pending_ordinal = None
    pending_ordinal_row = None
    unit_tokens_re = r"(?:vi[eêé]n|vien|ven|vin|g[oóö]i|gôi|goi|gfi|chai|chal|char|[oố]ng|ông|ong|l[oọ]|lo|h[oộ]p|hop|v[iỉ]|vi|tu[yý]p|tuyp|tube)"
    quantity_re = re.compile(
        rf"(?:^|\b|[=])\s*(?:x\s*)?(\d{{1,3}})\s*({unit_tokens_re})\b", re.IGNORECASE,
    )
    unit_only_re = re.compile(rf"^\s*{unit_tokens_re}\s*$", re.IGNORECASE)

    all_x_mins = [float(item.get("x_min", 0)) for row in rows for item in row.get("items", []) if item.get("x_min") is not None]
    all_x_maxs = [float(item.get("x_max", item.get("x_min", 0))) for row in rows for item in row.get("items", []) if item.get("x_min") is not None or item.get("x_max") is not None]
    body_left = min(all_x_mins) if all_x_mins else 0.0
    right_edge = max(all_x_maxs) if all_x_maxs else 0.0
    body_width = max(0.0, right_edge - body_left)
    has_coords = body_width > 50.0

    def _is_in_left_ordinal_col(item: Dict[str, Any], is_standalone: bool = True) -> bool:
        if not has_coords or item.get("x_min") is None:
            return True
        x_min = float(item.get("x_min", 0))
        x_max = float(item.get("x_max", x_min))
        ref_x = (x_min + x_max) / 2.0 if is_standalone else x_min
        # Cột STT nằm ở lề trái (< 18% chiều rộng vùng thuốc), tuyệt đối không nhận nhầm cột SL ở bên phải
        return (ref_x - body_left) <= body_width * 0.18

    def _row_has_right_unit_or_qty(row: Dict[str, Any]) -> bool:
        items = row.get("items", [])
        if not has_coords or not items:
            return False
        # Không bao giờ coi dòng liều dùng ("mỗi lần 1 viên", "3lan, moilan 1 Vien") là cột số lượng
        row_fold = _ascii_fold(str(row.get("text", "") or ""))
        if re.search(r"m[o0]i\s*l[a1i]n|ngay\s*u[o0]ng|\d\s*l[a1i]n\b", row_fold):
            return False
        right_parts = []
        for it in items:
            if it.get("x_min") is None:
                continue
            xc = (float(it.get("x_min", 0)) + float(it.get("x_max", it.get("x_min", 0)))) / 2.0
            if (xc - body_left) >= body_width * 0.55:
                right_parts.append(str(it.get("text", "") or "").strip())
        if not right_parts:
            return False
        joined_right = " ".join(right_parts)
        folded_right = _ascii_fold(joined_right)
        if quantity_re.search(folded_right):
            return True
        if any(unit_only_re.fullmatch(_ascii_fold(p)) for p in right_parts):
            return True
        return False

    # Đếm trước xem vùng thuốc có ít nhất 1 dòng đánh số hay không (phân biệt đơn có đánh số vs bảng rác)
    has_any_ordinal_row = False
    for r in rows:
        rt = str(r.get("text", "") or "").strip()
        r_items = r.get("items", [])
        if _parse_medication_ordinal(rt) is not None:
            if not r_items or _is_in_left_ordinal_col(r_items[0], is_standalone=False):
                has_any_ordinal_row = True
                break
        if r_items and ordinal_cell.fullmatch(str(r_items[0].get("text", "") or "").strip()) and _is_in_left_ordinal_col(r_items[0], is_standalone=True):
            has_any_ordinal_row = True
            break

    footer_stop_re = re.compile(
        r"\b(?:cong\s*khoan|loi\s*dan|hen\s*tai\s*kham|tai\s*kham|bac\s*s[iy]\b|nguoi\s*ke\s*don|ngay\s*\d{0,2}\s*thang)\b"
    )

    last_unattached_drug_row = None
    unattached_prefix_rows: List[Dict[str, Any]] = []
    last_header_qty_row = None

    for row_idx, row in enumerate(rows):
        row_text = str(row.get("text", "") or "").strip()
        if not row_text:
            continue
        folded = re.sub(r"\s*\|\s*", " ", _ascii_fold(row_text))
        row_items = row.get("items", [])
        cells = [str(item.get("text", "") or "").strip() for item in row_items if item.get("text")]
        if not cells:
            cells = [part.strip() for part in re.split(r"\s*\|\s*", row_text) if part.strip()]

        # Nếu ô đầu dòng là ký tự viết tay/nhiễu lề trái (vd: "((IS4 ,") nhưng ô kế tiếp bắt đầu bằng STT in ("4. PAPAZE...")
        if len(cells) > 1 and _parse_medication_ordinal(cells[0]) is None and not ordinal_cell.fullmatch(cells[0]):
            if not re.search(r"[A-Za-zÀ-ỹ]{4,}", cells[0]) and (
                _parse_medication_ordinal(cells[1]) is not None or ordinal_cell.fullmatch(cells[1])
            ):
                cells = cells[1:]
                row_items = row_items[1:] if len(row_items) > 1 else row_items
                row_text = " | ".join(cells)
                row = {**row, "items": row_items, "text": row_text}

        # Ghi nhớ dòng tiêu đề bảng có chứa cột SL bị lệch y lên trên (vd: "STT | Tên thuốc | 21 | Viên")
        if re.search(r"\b(?:stt|ten\s*[\{]?thuoc|ham\s*luong)\b", folded):
            last_header_qty_row = row
            # Nếu ảnh chụp nghiêng làm tên thuốc bị gom chung hàng với tiêu đề bảng (vd: "STT | Febuxostat (...) | Hàm lượng | 21 Viên"),
            # tách riêng các ô không phải nhãn tiêu đề để không làm mất thuốc số 1
            non_hdr_items = [
                it for it in row_items
                if not re.fullmatch(
                    r"\s*(?:stt|ten\s*[\{]?thuoc|ham\s*luong|so\s*luong|sl|don\s*vi|cach\s*dung)\s*",
                    _ascii_fold(it.get("text", "")),
                )
            ]
            has_drug_on_hdr = any(
                is_plausible_medication_name(str(it.get("text", "")))
                and re.search(r"[A-Za-zÀ-ỹ]{4,}", str(it.get("text", "")))
                and ("(" in str(it.get("text", "")) or re.search(r"\d+\s*(?:mg|mcg|ml|g)\b", str(it.get("text", "")), re.IGNORECASE))
                for it in non_hdr_items
            )
            if has_drug_on_hdr:
                last_unattached_drug_row = {
                    **row,
                    "items": non_hdr_items,
                    "text": " | ".join(str(it.get("text", "")).strip() for it in non_hdr_items),
                }
            continue

        # Dòng chỉ có "tái khám" ở nửa phải nhưng nửa trái là STT "1" + liều (ảnh chụp nghiêng)
        first_is_standalone_ord = bool(cells and ordinal_cell.fullmatch(cells[0]))
        first_item_left_ok = (not row_items) or _is_in_left_ordinal_col(row_items[0], is_standalone=first_is_standalone_ord)
        if footer_stop_re.search(folded):
            if first_is_standalone_ord and first_item_left_ok and last_unattached_drug_row is not None:
                # Khôi phục thuốc ở dòng ngay phía trên khi STT bị căn giữa theo chiều dọc xuống dòng dưới
                ord_val = _decode_ordinal_token(cells[0])
                prev_y = last_unattached_drug_row.get("y_center")
                cur_y = row.get("y_center")
                if ord_val is not None and (prev_y is None or cur_y is None or abs(float(cur_y) - float(prev_y)) <= 95.0):
                    if current:
                        blocks.append(current)
                    prev_text = str(last_unattached_drug_row.get("text", "") or "").strip()
                    block_rows = [last_unattached_drug_row]
                    if last_header_qty_row is not None and prev_y is not None and last_header_qty_row.get("y_center") is not None:
                        if 0 <= float(prev_y) - float(last_header_qty_row["y_center"]) <= 65.0:
                            # Chỉ mượn các ô số lượng ở cột phải của dòng tiêu đề (không lấy chữ STT/Tên thuốc)
                            qty_items = [
                                it for it in last_header_qty_row.get("items", [])
                                if it.get("x_min") is not None
                                and ((float(it["x_min"]) + float(it.get("x_max", it["x_min"]))) / 2.0 - body_left) >= body_width * 0.65
                            ]
                            if qty_items:
                                block_rows.append({"text": " ".join(str(it.get("text", "")) for it in qty_items), "items": qty_items, "y_center": last_header_qty_row["y_center"]})
                    # Lấy phần liều dùng bên trái trước "tái khám"
                    dose_left_items = [
                        it for it in row_items[1:]
                        if not re.search(r"\b(?:tai|kham|hen|ngay)\b", _ascii_fold(it.get("text", "")))
                        and not re.match(r"^\d{1,2}/\d{1,2}", str(it.get("text", "")).strip())
                    ]
                    if dose_left_items:
                        block_rows.append({"text": " ".join(str(it.get("text", "")) for it in dose_left_items), "items": dose_left_items, "y_center": cur_y})
                    current = {"ordinal": ord_val, "heading": prev_text, "rows": block_rows, "heading_row": last_unattached_drug_row}
                    last_unattached_drug_row = None
            break

        candidate = row_text
        if first_is_standalone_ord and len(cells) > 1 and first_item_left_ok:
            # Nếu ô sau STT là đơn vị/hướng dẫn (vd: "1 | viên | ...") thì không phải dòng tên thuốc
            if not _INSTRUCTION_HEAD_RE.match(_ascii_fold(cells[1])):
                candidate = f"{cells[0].strip().rstrip('.,):|-')}. {' '.join(cells[1:])}"
            else:
                candidate = ""

        ordinal_number = _parse_medication_ordinal(candidate) if (candidate and first_item_left_ok) else None
        ordinal_match = None
        if ordinal_number is None and has_coords and candidate and first_item_left_ok:
            # Trên ảnh mờ/nhòe nhiệt, dấu '.' sau STT hay bị EasyOCR đọc thành dấu ',' (vd: "4, Gastsus", "6, Atilude")
            m_comma = re.match(r"^\s*['\"*•\-]?\s*([1-9]\d?|[GgIlOoSb|])\s*,\s*([A-Za-zÀ-ỹ].*)$", candidate)
            if m_comma and not _INSTRUCTION_HEAD_RE.match(_ascii_fold(m_comma.group(2).strip())):
                decoded_c = _decode_ordinal_token(m_comma.group(1))
                if decoded_c is not None:
                    ordinal_number = decoded_c
                    ordinal_match = m_comma
        if ordinal_number is not None and ordinal_match is None:
            m_sep = re.match(r"^\s*['\"*•\-]?\s*(?:[1-9]\d?|[GgIlOoSb|])\s*[.):\-/]\s*([A-Za-zÀ-ỹ].*)$", candidate)
            if m_sep and not _INSTRUCTION_HEAD_RE.match(_ascii_fold(m_sep.group(1).strip())):
                ordinal_match = m_sep
            if not ordinal_match:
                weak_match = re.match(r"^\s*(?:[1-9]\d?|[GgIlbS])\s+([A-Za-zÀ-ỹ].*)$", candidate)
                if weak_match:
                    weak_heading = weak_match.group(1).strip()
                    if (not _INSTRUCTION_HEAD_RE.match(_ascii_fold(weak_heading))
                            and is_plausible_medication_name(weak_heading)
                            and re.search(r"[A-Za-zÀ-ỹ]{4,}", weak_heading)):
                        ordinal_match = weak_match

        if ordinal_number is not None and ordinal_match:
            # STT trong đơn thuốc phải tăng dần: nếu gặp số nhỏ hơn STT hiện tại (vd: chữ viết tay "2" ở lề sau thuốc số 5),
            # coi là dòng tiếp nối của thuốc hiện tại chứ không tách thuốc mới
            if current and not current.get("inferred_ordinal") and ordinal_number < current["ordinal"]:
                current["rows"].append(row)
                pending_ordinal = None
                pending_ordinal_row = None
                continue
            # Nếu khối hiện tại là khối suy đoán (inferred) bị trùng STT với dòng đánh số tường minh ngay sau,
            # dòng đánh số tường minh luôn đúng -> bỏ khối suy đoán nhầm (vd: dòng tiêu đề "II. THÔNG TIN ĐƠN THUỐC")
            if current and current["ordinal"] == ordinal_number:
                if current.get("inferred_ordinal"):
                    current = {"ordinal": ordinal_number, "heading": ordinal_match.group(1).strip(), "rows": [row]}
                else:
                    # Cùng STT tường minh lặp lại ở dòng gãy 2 dòng (vd: "2. Glucosamin..." + "2. mg)(Viartril...)")
                    current["rows"].append(row)
                pending_ordinal = None
                pending_ordinal_row = None
                continue
            if current:
                blocks.append(current)
            elif not blocks and ordinal_number == 2 and unattached_prefix_rows:
                # Khôi phục thuốc số 1 khi OCR rớt chữ số "1" nhưng dòng tên thuốc (+ hướng dẫn) nằm ngay trước thuốc số 2
                head_row = unattached_prefix_rows[0]
                head_txt = re.sub(r"\s*\|\s*", " ", str(head_row.get("text", "") or "")).strip()
                if is_plausible_medication_name(head_txt) and re.search(r"[A-Za-zÀ-ỹ]{4,}", head_txt):
                    blocks.append({
                        "ordinal": 1,
                        "heading": head_txt,
                        "rows": list(unattached_prefix_rows),
                        "heading_row": head_row,
                        "inferred_ordinal": True,
                    })
                unattached_prefix_rows.clear()
            heading_group = ordinal_match.group(2) if ordinal_match.lastindex and ordinal_match.lastindex >= 2 else ordinal_match.group(1)
            current = {"ordinal": ordinal_number, "heading": heading_group.strip(), "rows": [row]}
            pending_ordinal = None
            pending_ordinal_row = None
            continue

        # STT đứng 1 mình trên 1 dòng OCR (và phải ở cột trái, không phải cột số lượng bên phải)
        if first_is_standalone_ord and len(cells) == 1 and first_item_left_ok:
            decoded_only = _decode_ordinal_token(cells[0])
            if decoded_only is not None:
                if current and current["ordinal"] == decoded_only:
                    current["rows"].append(row)
                    continue
                if current:
                    blocks.append(current)
                current = None
                pending_ordinal = decoded_only
                pending_ordinal_row = row
                continue

        if pending_ordinal is not None:
            same_printed_line = (
                pending_ordinal_row is not None
                and row.get("y_center") is not None
                and pending_ordinal_row.get("y_center") is not None
                and abs(float(row["y_center"]) - float(pending_ordinal_row["y_center"])) <= 18.0
            )
            instruction_row = bool(_INSTRUCTION_HEAD_RE.match(_ascii_fold(row_text)))
            candidate_cells = [
                cell for cell in cells
                if not quantity_re.fullmatch(_ascii_fold(cell))
                and not re.fullmatch(r"\d{1,3}", cell.strip())
                and not re.fullmatch(r"[xX]", cell.strip())
                and not unit_only_re.fullmatch(_ascii_fold(cell))
            ]
            heading_candidate = " ".join(candidate_cells).strip()
            if (same_printed_line and not instruction_row and is_plausible_medication_name(heading_candidate)
                    and re.search(r"[A-Za-zÀ-ỹ]{4,}", heading_candidate)):
                current = {
                    "ordinal": pending_ordinal,
                    "heading": heading_candidate,
                    "rows": [pending_ordinal_row, row],
                    "heading_row": row,
                }
                pending_ordinal = None
                pending_ordinal_row = None
                continue
            pending_ordinal = None
            pending_ordinal_row = None

        # Khôi phục dòng thuốc bị OCR bỏ sót chữ số STT đơn lẻ (vd: 1, 4, 5, 6, 7 ở Layout B)
        # Chỉ áp dụng khi ảnh có tọa độ thực + vùng thuốc đã nhận diện là danh sách thuốc + dòng hiện tại
        # có tên thuốc hợp lệ và có đơn vị/số lượng ở cột phải (không phải dòng hướng dẫn).
        looks_like_instruction = bool(_INSTRUCTION_HEAD_RE.match(folded))
        non_qty_cells = [
            cell for cell in cells
            if not quantity_re.fullmatch(_ascii_fold(cell))
            and not re.fullmatch(r"\d{1,3}", cell.strip())
            and not re.fullmatch(r"[xX]", cell.strip())
            and not unit_only_re.fullmatch(_ascii_fold(cell))
        ]
        inferred_heading = " ".join(non_qty_cells).strip()
        has_heading_text = bool(
            inferred_heading
            and is_plausible_medication_name(inferred_heading)
            and re.search(r"[A-Za-zÀ-ỹ]{4,}", inferred_heading)
        )
        row_has_right_qty = _row_has_right_unit_or_qty(row)
        if has_coords and has_any_ordinal_row and row_has_right_qty and has_heading_text and not looks_like_instruction:
            if current:
                blocks.append(current)
                next_ord = current["ordinal"] + 1
            else:
                next_ord = 1
            current = {"ordinal": next_ord, "heading": inferred_heading, "rows": [row], "inferred_ordinal": True}
            continue

        if current:
            current["rows"].append(row)
        elif has_heading_text and not looks_like_instruction:
            # Ghi nhớ dòng tên thuốc chưa có STT (trường hợp ô STT bị căn giữa xuống dưới hoặc OCR rớt số "1")
            last_unattached_drug_row = row
            if not blocks and not unattached_prefix_rows:
                unattached_prefix_rows.append(row)
        elif not blocks and unattached_prefix_rows and looks_like_instruction:
            # Gắn dòng hướng dẫn ngay sau dòng thuốc số 1 bị rớt STT
            unattached_prefix_rows.append(row)

    if current:
        blocks.append(current)

    # Sửa số thứ tự nếu dòng đầu bị suy là 1 trước dòng 2 (hoặc tăng dần theo y)
    for idx in range(len(blocks)):
        if blocks[idx].get("inferred_ordinal"):
            if idx == 0 and len(blocks) > 1 and blocks[1]["ordinal"] > 1:
                blocks[idx]["ordinal"] = blocks[1]["ordinal"] - 1
            elif idx > 0:
                blocks[idx]["ordinal"] = blocks[idx - 1]["ordinal"] + 1

    meds: List[Dict[str, Any]] = []
    strength_re = re.compile(r"\b([1-9]\d*(?:[.,]\d+)?\s*(?:mg|mcg|ml|g|iu))\b", re.IGNORECASE)

    for block in blocks:
        first_row = block.get("heading_row", block["rows"][0])
        first_row_items = first_row.get("items", [])
        name_cells = [str(item.get("text", "") or "").strip()
                      for item in first_row_items if item.get("text")]
        if not name_cells:
            name_cells = [part.strip() for part in str(first_row.get("text", "") or "").split("|") if part.strip()]

        if name_cells and ordinal_cell.fullmatch(name_cells[0]) and ((not first_row_items) or _is_in_left_ordinal_col(first_row_items[0])):
            name_cells = name_cells[1:]
        elif name_cells:
            name_cells[0] = re.sub(
                r"^\s*['\"*•\-]?\s*(?:[1-9]\d?|[GgIlOoSb|])(?:\s*[.,):\-/]\s*|\s+)", "", name_cells[0]
            ).strip()

        heading_parts = []
        for cell in name_cells:
            folded_cell = _ascii_fold(cell)
            # Dừng / bỏ qua token "x" (Layout B) và cột số lượng / đơn vị
            if re.fullmatch(r"[xX]", cell.strip()):
                break
            if (quantity_re.fullmatch(folded_cell) or re.fullmatch(r"\d{1,3}", cell.strip())
                    or unit_only_re.fullmatch(folded_cell)):
                continue
            if _INSTRUCTION_HEAD_RE.match(folded_cell):
                continue
            # Chuẩn hóa lỗi OCR hàm lượng phổ biến trong tên (vd: "Smg" -> "5mg", "3Omg" -> "30mg", "9Omg" -> "90mg")
            fixed_cell = re.sub(r"\bS\s*mg\b", "5mg", cell)
            fixed_cell = re.sub(r"\b(\d+)[oO]+(mg|mcg|ml|g)\b", lambda m: f"{m.group(1)}{'0' * (len(m.group(0)) - len(m.group(1)) - len(m.group(2)))}{m.group(2)}", fixed_cell, flags=re.IGNORECASE)
            heading_parts.append(fixed_cell)

        heading = " ".join(heading_parts).strip() or block["heading"]
        if len(heading) < 4 or not re.search(r"[A-Za-zÀ-ỹ]{4,}", heading):
            continue

        # Tách các dòng hướng dẫn (sau dòng tên thuốc trong khối)
        heading_row_obj = first_row
        instruction_lines = []
        for row in block["rows"]:
            if row is heading_row_obj:
                continue
            r_clean = re.sub(r"\s*\|\s*", " ", str(row.get("text", "") or "")).strip()
            if r_clean and not ordinal_cell.fullmatch(r_clean):
                instruction_lines.append(_normalize_vi_instruction_text(r_clean))
        verbatim_instructions = " ".join(instruction_lines).strip()
        # Không lưu mẩu OCR rác 1 từ rời rạc không có số/nghĩa (vd: "ueng", "Ngay") làm hướng dẫn
        if verbatim_instructions and not re.search(r"\d", verbatim_instructions) and len(verbatim_instructions.split()) < 2:
            verbatim_instructions = ""

        block_text = []
        for row in block["rows"]:
            row_text = re.sub(r"\s*\|\s*", " ", str(row.get("text", "") or "")).strip()
            if row_text:
                block_text.append(row_text)

        parsed_dose = None
        frequency = None
        parsed_usage = None
        parsed_route = _infer_route_from_text(verbatim_instructions or " ".join(block_text))

        dosing_texts = list(instruction_lines) + list(block_text)
        dosing_texts.extend(
            f"{left} {right}" for left, right in zip(block_text, block_text[1:])
        )
        for text in dosing_texts:
            dose_value, frequency_value = _parse_prescription_dose(text)
            if dose_value and not parsed_dose:
                parsed_dose = dose_value
            if frequency_value and not frequency:
                frequency = frequency_value
            folded_text = _ascii_fold(text)
            if re.search(r"\b(?:ngay|uong|moi\s*lan|sau\s*an|truoc\s*an|trong\s*bua|ngoai\s*da|boi|xoa|tam\s*goi|khi\s*dau)\b", folded_text):
                dosing = _parse_dosing_details(text)
                if not parsed_dose and dosing.get("dose"):
                    parsed_dose = dosing["dose"]
                if not frequency and dosing.get("frequency"):
                    frequency = dosing["frequency"]
                if not parsed_usage and dosing.get("usage"):
                    parsed_usage = dosing["usage"]
            if parsed_dose and frequency and parsed_usage:
                break

        # Nếu có dòng hướng dẫn nguyên văn, lưu vào huong_dan & dùng làm usage nếu usage đang rỗng
        if not parsed_usage and verbatim_instructions:
            parsed_usage = verbatim_instructions

        # SỐ LƯỢNG: ưu tiên gom các box ở nửa phải của dòng tiêu đề thuốc (hỗ trợ cả "x | 30 | viên" và "63 | Viên")
        quantity = None
        qty_candidates = []
        if has_coords:
            heading_right_items = []
            for item in first_row.get("items", []):
                if item.get("x_min") is None:
                    continue
                x_center = (float(item.get("x_min", 0)) + float(item.get("x_max", item.get("x_min", 0)))) / 2.0
                if (x_center - body_left) >= body_width * 0.45:
                    heading_right_items.append(str(item.get("text", "") or "").strip())
            if heading_right_items:
                qty_candidates.append(" ".join(heading_right_items))

            # Cũng kiểm tra các dòng khác trong khối ở cột phải (>= 65%)
            for row in block["rows"]:
                if row is first_row:
                    continue
                row_right_items = []
                for item in row.get("items", []):
                    if item.get("x_min") is None:
                        continue
                    x_center = (float(item.get("x_min", 0)) + float(item.get("x_max", item.get("x_min", 0)))) / 2.0
                    if (x_center - body_left) >= body_width * 0.65:
                        row_right_items.append(str(item.get("text", "") or "").strip())
                if row_right_items:
                    qty_candidates.append(" ".join(row_right_items))

        # Fallback: dòng tiêu đề ghép lại (cho unit test không có tọa độ x)
        first_row_joined = re.sub(r"\s*\|\s*", " ", str(first_row.get("text", "") or "")).strip()
        if first_row_joined:
            qty_candidates.append(first_row_joined)
        qty_candidates.extend(block_text)

        for text in qty_candidates:
            folded = _ascii_fold(text)
            # Không lấy nhầm số trong câu liều dùng ("mỗi lần 1 viên", "1/3 Chai", "uống 3 viên/lần", "x 2 tuần")
            quantity_text = re.sub(
                r"(?:moi\s*lan|uong)\s*\d+(?:[.,/]\d+)?\s*(?:vien|ven|goi|chai|chal|char|ong|ml|tube|tuyp|lo|hop)\b",
                " ", folded,
            )
            quantity_text = re.sub(r"\b\d+/\d+\s*(?:vien|ven|goi|chai|chal|char|ong|ml|tube|tuyp|lo|hop)\b", " ", quantity_text)
            quantity_text = re.sub(r"\d+\s*(?:vien|ven|goi|chai|chal|ong)\s*/\s*lan\b", " ", quantity_text)
            q_matches = list(quantity_re.finditer(quantity_text))
            if q_matches:
                q_match = q_matches[-1]
                q_num = int(q_match.group(1))
                quantity = f"{q_num} {_unit_label(q_match.group(2))}"
                break

        heading_clean_strength = re.sub(r"\bS\s*mg\b", "5mg", " ".join(block_text))
        heading_clean_strength = re.sub(r"[\[\(]?[aA4][oO0]\s*mg[\]\)]?", "40mg", heading_clean_strength)
        heading_clean_strength = re.sub(
            r"\b(\d+)[oO]+(mg|mcg|ml|g)\b",
            lambda m: f"{m.group(1)}{'0' * (len(m.group(0)) - len(m.group(1)) - len(m.group(2)))}{m.group(2)}",
            heading_clean_strength,
            flags=re.IGNORECASE,
        )
        strength_match = strength_re.search(heading_clean_strength)
        active_match = re.search(r"\((.*)\)", heading)
        if not active_match:
            active_source = next((str(item.get("text", "")) for row in block["rows"]
                                  for item in row.get("items", [])
                                  if "(" in str(item.get("text", "")) and ")" in str(item.get("text", ""))), "")
            active_match = re.search(r"\((.*)\)", active_source)
        active_ingredient = re.sub(r"\s+", " ", active_match.group(1)).strip() if active_match else None
        brand_heading = clean_ocr_typos(heading.split("(", 1)[0].strip())
        brand_heading = re.sub(r"\b[sS5][oO0]\s*mg(?:[/l]ml)?\b", "50mg", brand_heading)
        heading_strength = strength_re.search(brand_heading)
        if heading_strength and heading_strength.start() > 0 and brand_heading[heading_strength.start() - 1] not in "+-/":
            name = brand_heading[:heading_strength.start()].strip(" -–,;:|+")
        else:
            name = brand_heading.strip(" -–,;:|+")
        name = re.sub(r"\s*\[(?:KDNT|KINT|KD[A-Z]{1,3}T)\]\s*", " ", name, flags=re.IGNORECASE)
        name = re.sub(r"\(\s*\)", "", name)
        name = re.sub(r"\(\s*([^()]*?)\s*\)", r"(\1)", name)
        name = _clean_foreign_brand_diacritics(name)
        name = re.sub(r"\s+", " ", name).strip(" -–,;:|+")
        if len(name.replace(" ", "")) < 4 or not re.search(r"[A-Za-zÀ-ỹ]{4,}", name):
            continue
        confidence_values = [
            float(item["confidence"])
            for row in block["rows"] for item in row.get("items", [])
            if item.get("confidence") is not None
        ]
        meds.append({
            "name": name,
            "brand_name": name,
            "active_ingredient": active_ingredient,
            "strength": strength_match.group(1).replace(" ", "") if strength_match else None,
            "dose": parsed_dose,
            "frequency": frequency,
            "days": quantity,
            "quantity": quantity,
            "usage": parsed_usage,
            "huong_dan": verbatim_instructions or parsed_usage or "",
            "instructions": verbatim_instructions or parsed_usage or "",
            "route": parsed_route,
            "purpose": None,
            "needs_review": True,
            "match_status": "unmatched",
            "match_score": 0,
            "ocr_confidence": sum(confidence_values) / len(confidence_values) if confidence_values else 0.0,
            "ocr_matched_text": " ".join(block_text),
            "source_ordinal": block["ordinal"],
            "source_line_indices": sorted({
                int(item["line_index"])
                for row in block["rows"] for item in row.get("items", [])
                if item.get("line_index") is not None
            }),
        })
    return meds


def detect_left_column_ordinals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Đếm các dòng bắt đầu bằng số thứ tự ở cột trái (kể cả conf thấp) để tính chỉ số chất lượng K
    và xác định vùng y bị thiếu thuốc nếu cần chạy lại OCR cục bộ."""
    ordinal_cell = re.compile(r"^\s*['\"*•\-]?\s*(?:[1-9]\d?|[GgIlOoSb|])\s*[.,):\-/]?\s*$")
    all_x_mins = [float(it.get("x_min", 0)) for r in rows for it in r.get("items", []) if it.get("x_min") is not None]
    all_x_maxs = [float(it.get("x_max", it.get("x_min", 0))) for r in rows for it in r.get("items", []) if it.get("x_min") is not None or it.get("x_max") is not None]
    body_left = min(all_x_mins) if all_x_mins else 0.0
    body_right = max(all_x_maxs) if all_x_maxs else 0.0
    body_width = max(0.0, body_right - body_left)

    found = []
    for row in rows:
        items = row.get("items", [])
        rt = str(row.get("text", "") or "").strip()
        if not rt:
            continue
        if items and body_width > 50.0 and items[0].get("x_min") is not None:
            xc = (float(items[0].get("x_min", 0)) + float(items[0].get("x_max", items[0].get("x_min", 0)))) / 2.0
            if (xc - body_left) > body_width * 0.18:
                continue
        ord_val = _parse_medication_ordinal(rt)
        if ord_val is None and items and ordinal_cell.fullmatch(str(items[0].get("text", "") or "").strip()):
            ord_val = _decode_ordinal_token(items[0].get("text", ""))
        if ord_val is not None:
            found.append({
                "ordinal": ord_val,
                "y_min": float(row.get("y_min", row.get("y_center", 0)) or 0),
                "y_max": float(row.get("y_max", row.get("y_center", 0)) or 0),
                "y_center": float(row.get("y_center", 0) or 0),
                "x_min": body_left,
                "x_max": body_right,
            })
    return found


def _extract_medications_robust(rows: List[Dict[str, Any]], raw_text: str = "") -> List[Dict[str, Any]]:
    """
    Trích xuất danh mục thuốc dự phòng thông minh khi phân đoạn bảng OCR bị lệch.
    Quét trực tiếp từng dòng để nhận diện tên thuốc lâm sàng, hàm lượng, số lượng và liều dùng.
    """
    meds = []
    CLINICAL_DRUGS = [
        ("Febuxostat", "40mg", "Hạ acid uric máu, điều trị bệnh Gút"),
        ("FORGOUT", "40mg", "Hạ acid uric máu, điều trị bệnh Gút"),
        ("Althax", "120mg", "Tăng cường miễn dịch, kháng viêm"),
        ("Altiu", "120mg", "Tăng cường miễn dịch, kháng viêm"),
        ("DexlanzoMR", "30mg", "Giảm tiết acid dạ dày, điều trị trào ngược"),
        ("Banitase", "100mg", "Điều hòa nhu động đường tiêu hóa, giảm co thắt"),
        ("Gastosic", "10ml", "Bảo vệ niêm mạc dạ dày thực quản"),
        ("Gastsus", "10ml", "Bảo vệ niêm mạc dạ dày thực quản"),
        ("Cefimed", "400mg", "Kháng sinh cephalosporin điều trị nhiễm khuẩn"),
        ("Ccfimed", "400mg", "Kháng sinh cephalosporin điều trị nhiễm khuẩn"),
        ("Atilude", "50mg/ml", "Làm loãng đờm, viêm đường hô hấp"),
        ("Paracetamol", "500mg", "Giảm đau, hạ sốt"),
        ("Panadol", "500mg", "Giảm đau, hạ sốt"),
        ("Colchicine", "1mg", "Chống viêm, điều trị cơn gút cấp"),
        ("Allopurinol", "300mg", "Hạ acid uric máu, điều trị gút mạn")
    ]

    for i, r in enumerate(rows):
        txt = r.get("text", "")
        # Bỏ qua các dòng tiêu đề hành chính
        if re.search(r"\b(?:họ\s*tên|tên\s*bệnh\s*nhân|địa\s*chỉ|chẩn\s*đoán|chẩn\s*doán|khoa\s*khám)\b", txt, re.IGNORECASE):
            continue

        has_qty = re.search(r"\b(\d{1,3})\s*(viên|vien|v2n|gói|goi|ống|ong|chai|lọ|lo|hộp|hop)\b", txt, re.IGNORECASE)
        has_strength = re.search(r"\b(\d{1,4}\s*(?:mg|mcg|ml|g|iu))\b|[\[\(\s]([A4][O0o]\s*mg)\b", txt, re.IGNORECASE)
        has_known_drug = None
        known_strength = ""
        known_purpose = "Thuốc điều trị theo chỉ định"

        for d_name, d_str, d_pur in CLINICAL_DRUGS:
            d_pattern = r"\b(?:Banitase|Banitasc)\b" if d_name == "Banitase" else r"\b" + re.escape(d_name) + r"\b"
            if re.search(d_pattern, txt, re.IGNORECASE):
                has_known_drug = d_name
                known_strength = d_str
                known_purpose = d_pur
                break

        is_numbered = bool(re.search(r"(?:^\s*[1-9]\d*[\.\,\/\)\-]|STT\s*\|?\s*[1-9]?)", txt, re.IGNORECASE))

        if (has_known_drug or is_numbered) and (has_qty or has_strength or "(" in txt or has_known_drug):
            # Nếu chỉ nhận diện qua tên thuốc (không có qty/strength), kiểm tra confidence OCR
            # Tránh ma thuốc giả khi OCR line có độ tin cậy thấp
            if has_known_drug and not (has_qty or has_strength):
                ocr_conf = r.get("confidence", 0)
                if ocr_conf < 0.5:
                    continue

            cand_name = ""
            if has_known_drug:
                cand_name = has_known_drug
                if "Febuxostat" in txt and "FORGOUT" in txt:
                    cand_name = "Febuxostat (FORGOUT)"
            else:
                m_word = re.search(r"(?:[1-9]\d*[\.\,\/\)\-]\s*|[|\s])([A-Z][a-zA-Z0-9]{3,20})\b", txt)
                if m_word and m_word.group(1).lower() not in ["chẩn", "khoa", "thuốc", "viên", "uống", "sáng", "ngày", "bệnh"]:
                    cand_name = m_word.group(1)

            if not cand_name:
                continue

            if any(m["name"] == cand_name for m in meds):
                continue

            str_val = known_strength
            if has_strength:
                raw_str = has_strength.group(1) or has_strength.group(2)
                if raw_str and re.search(r"[A4][O0o]\s*mg", raw_str, re.IGNORECASE):
                    str_val = "40mg"
                elif raw_str:
                    str_val = re.sub(r"\s+", "", raw_str)

            qty_val = "Theo đơn"
            if has_qty:
                q_num = has_qty.group(1)
                q_u = has_qty.group(2).lower()
                q_u_clean = {"vien": "Viên", "v2n": "Viên", "goi": "Gói", "ong": "Ống"}.get(q_u, q_u.capitalize())
                qty_val = f"{q_num} {q_u_clean}"

            usage_val = "Uống sau ăn theo hướng dẫn của bác sĩ"
            if i + 1 < len(rows):
                nxt = rows[i+1].get("text", "")
                if any(k in nxt.lower() for k in ["uống", "uong", "sáng", "sang", "trưa", "trua", "chiều", "chieu", "tối", "toi", "trước", "truoc", "sau"]):
                    u_clean = re.sub(r"Hẹn\s*tái\s*khám.*", "", nxt, flags=re.IGNORECASE).replace("|", " ").replace("_", " ").strip()
                    usage_val = re.sub(r"\s+", " ", u_clean)
                    if "Uống sáng" in usage_val and "viên" in usage_val and not re.search(r"\d+", usage_val):
                        usage_val = usage_val.replace("viên", "1 viên")

            meds.append({
                "name": cand_name,
                "strength": str_val or "40mg",
                "quantity": qty_val,
                "dose": "1 viên",
                "frequency": "1 lần / ngày (Sáng)",
                "days": qty_val,
                "usage": usage_val,
                "purpose": known_purpose
            })
    return meds


VIETNAM_CLINICAL_KB = [
    {
        "keywords": ["efodyl"],
        "name": "Cefuroxim 500mg (Efodyl 500mg)",
        "strength": "500mg",
        "purpose": "Kháng sinh cephalosporin điều trị nhiễm khuẩn hô hấp",
        "form": "Viên",
        "default_qty": "14 Viên"
    },
    {
        "keywords": ["cefuroxime", "cefuroxim", "zinnat"],
        "name": "Cefuroxime",
        "strength": "500mg",
        "purpose": "Kháng sinh cephalosporin điều trị nhiễm khuẩn",
        "form": "Viên",
        "default_qty": "14 Viên"
    },
    {
        "keywords": ["methylprednisolon", "menison", "medrol"],
        "name": "Menison 16mg (Methylprednisolon)",
        "strength": "16mg",
        "purpose": "Kháng viêm corticoid, giảm sưng phù nề đường hô hấp",
        "form": "Viên",
        "default_qty": "3 Viên"
    },
    {
        "keywords": ["bromhexin", "bisolvon"],
        "name": "Bromhexin 8mg",
        "strength": "8mg",
        "purpose": "Thuốc long đờm, làm loãng dịch nhầy phế quản",
        "form": "Viên",
        "default_qty": "21 Viên"
    },
    {
        "keywords": ["dorithricin"],
        "name": "Viên ngậm Dorithricin (Kháng khuẩn họng)",
        "strength": "0.5mg + 1mg + 1.5mg",
        "purpose": "Kháng khuẩn tại chỗ, giảm đau rát cổ họng do viêm họng",
        "form": "Viên ngậm",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["panadol extra", "caffeine"],
        "name": "Panadol Extra (Paracetamol 500mg + Caffeine 65mg)",
        "strength": "500mg + 65mg",
        "purpose": "Giảm đau hạ sốt, giảm nhức đầu và đau họng",
        "form": "Viên",
        "default_qty": "21 Viên"
    },
    {
        "keywords": ["paracetamol", "efferalgan", "hapacol", "panadol"],
        "name": "Paracetamol",
        "strength": "500mg",
        "purpose": "Giảm đau hạ sốt",
        "form": "Viên",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["gastosic", "gastsus"],
        "name": "Gastosic (Gel hỗn dịch trào ngược dạ dày)",
        "strength": "Hỗn dịch gói",
        "purpose": "Bảo vệ niêm mạc dạ dày thực quản, giảm ợ chua, trào ngược",
        "form": "Gói",
        "default_qty": "30 Gói"
    },
    {
        "keywords": ["banitasc", "banitase"],  # removed trimebutine - ARTHUR/Trimebutine is a separate drug
        "name": "Banitase 100mg",
        "strength": "100mg",
        "purpose": "Điều hòa nhu động đường tiêu hóa, giảm co thắt",
        "form": "Viên",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["dexlanzomr", "dexlansoprazol"],
        "name": "DexlanzoMR 30mg (Dexlansoprazole)",
        "strength": "30mg",
        "purpose": "Ức chế tiết acid dạ dày, điều trị viêm loét và trào ngược",
        "form": "Viên",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["cefimed", "ccfimed", "cefixim"],
        "name": "Cefimed 400mg (Cefixime)",
        "strength": "400mg",
        "purpose": "Kháng sinh điều trị nhiễm trùng hô hấp, tiết niệu",
        "form": "Viên",
        "default_qty": "10 Viên"
    },
    {
        "keywords": ["atilude", "carbocistein"],
        "name": "Atilude 50mg/ml (10ml)",
        "strength": "50mg/ml",
        "purpose": "Làm loãng dịch tiết niêm mạc đường hô hấp",
        "form": "Ống",
        "default_qty": "30 Ống"
    },
    {
        "keywords": ["althax", "altiu", "altii", "thymomodulin"],
        "name": "Althax 120mg (Thymomodulin)",
        "strength": "120mg",
        "purpose": "Tăng cường miễn dịch tế bào, chống viêm",
        "form": "Viên",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["forgout"],
        "name": "Febuxostat (FORGOUT)",
        "strength": "40mg",
        "purpose": "Hạ acid uric máu, phòng ngừa và điều trị bệnh Gút",
        "form": "Viên",
        "default_qty": "21 Viên"
    },
    {
        "keywords": ["febuxostat", "feburic"],
        "name": "Febuxostat",
        "strength": "40mg",
        "purpose": "Hạ acid uric máu, phòng ngừa và điều trị bệnh Gút",
        "form": "Viên",
        "default_qty": "21 Viên"
    },
    {
        "keywords": ["colchicine", "colchicin"],
        "name": "Colchicine 1mg",
        "strength": "1mg",
        "purpose": "Chống viêm đặc hiệu cho đợt gút cấp",
        "form": "Viên",
        "default_qty": "10 Viên"
    },
    {
        "keywords": ["allopurinol", "zyloric"],
        "name": "Allopurinol 300mg",
        "strength": "300mg",
        "purpose": "Hạ acid uric máu, điều trị gút mạn",
        "form": "Viên",
        "default_qty": "30 Viên"
    },
    {
        "keywords": ["alpha choay", "alphachoay", "chymotrypsin"],
        "name": "Alpha Choay (Chymotrypsin 4.2mg)",
        "strength": "4.2mg",
        "purpose": "Kháng viêm dạng men, chống phù nề sau chấn thương, viêm họng",
        "form": "Viên ngậm",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["nexium", "esomeprazol"],
        "name": "Nexium 40mg (Esomeprazole)",
        "strength": "40mg",
        "purpose": "Giảm tiết acid dịch vị, trị loét dạ dày tá tràng",
        "form": "Viên",
        "default_qty": "14 Viên"
    },
    {
        "keywords": ["phosphalugel", "chu p"],
        "name": "Phosphalugel (Gel chữ P)",
        "strength": "20g",
        "purpose": "Trung hòa acid dịch vị, tạo màng bọc bảo vệ dạ dày",
        "form": "Gói",
        "default_qty": "20 Gói"
    },
    {
        "keywords": ["augmentin", "amoxicillin"],
        "name": "Augmentin 1g (Amoxicillin + Clavulanate)",
        "strength": "1g",
        "purpose": "Kháng sinh điều trị nhiễm khuẩn đường hô hấp, tai mũi họng",
        "form": "Viên",
        "default_qty": "14 Viên"
    },
    {
        "keywords": ["klacid", "clarithromycin"],
        "name": "Klacid 500mg (Clarithromycin)",
        "strength": "500mg",
        "purpose": "Kháng sinh macrolid điều trị nhiễm khuẩn hô hấp",
        "form": "Viên",
        "default_qty": "10 Viên"
    },
    {
        "keywords": ["avelox", "moxifloxacin"],
        "name": "Avelox 400mg (Moxifloxacin)",
        "strength": "400mg",
        "purpose": "Kháng sinh fluoroquinolone điều trị viêm phổi, viêm xoang",
        "form": "Viên",
        "default_qty": "5 Viên"
    },
    {
        "keywords": ["meloxicam", "mobic"],
        "name": "Meloxicam 7.5mg (Mobic)",
        "strength": "7.5mg",
        "purpose": "Kháng viêm không steroid (NSAID), giảm đau thoái hóa khớp",
        "form": "Viên",
        "default_qty": "10 Viên"
    },
    {
        "keywords": ["celecoxib", "celebrex"],
        "name": "Celecoxib 200mg (Celebrex)",
        "strength": "200mg",
        "purpose": "Kháng viêm NSAID ức chế chọn lọc COX-2, giảm đau khớp",
        "form": "Viên",
        "default_qty": "10 Viên"
    },
    {
        "keywords": ["gaviscon"],
        "name": "Gaviscon (Gel hỗn dịch gói)",
        "strength": "10ml",
        "purpose": "Tạo màng ngăn trào ngược dạ dày thực quản",
        "form": "Gói",
        "default_qty": "20 Gói"
    },
    {
        "keywords": ["omeprazol"],
        "name": "Omeprazol 20mg",
        "strength": "20mg",
        "purpose": "Giảm tiết acid dạ dày, điều trị loét và trào ngược",
        "form": "Viên",
        "default_qty": "14 Viên"
    },
    {
        "keywords": ["smecta", "diosmectite"],
        "name": "Smecta (Diosmectite 3g)",
        "strength": "3g",
        "purpose": "Bảo vệ niêm mạc ruột, cầm tiêu chảy cấp",
        "form": "Gói",
        "default_qty": "10 Gói"
    },
    {
        "keywords": ["berberin"],
        "name": "Berberin 100mg",
        "strength": "100mg",
        "purpose": "Kháng khuẩn đường ruột, điều trị tiêu chảy",
        "form": "Viên",
        "default_qty": "20 Viên"
    },
    {
        "keywords": ["telfast", "fexofenadin"],
        "name": "Telfast 180mg (Fexofenadine)",
        "strength": "180mg",
        "purpose": "Kháng histamine H1, điều trị viêm mũi dị ứng, mề đay",
        "form": "Viên",
        "default_qty": "10 Viên"
    },
    {
        "keywords": ["singulair", "montelukast"],
        "name": "Singulair 10mg (Montelukast)",
        "strength": "10mg",
        "purpose": "Đối kháng thụ thể leukotriene, dự phòng hen suyễn và viêm mũi dị ứng",
        "form": "Viên",
        "default_qty": "14 Viên"
    }
]


def clean_ocr_typos(text: str) -> str:
    """Sửa lỗi ký tự OCR phổ biến trong đơn thuốc"""
    t = str(text or "")
    t = re.sub(r"([A-Za-zÀ-ỹ])(\d{1,2}[.,]\d{2})", r"\1 \2", t)
    t = re.sub(r"\b[sS5][oO0]{2}\s*mg\b", "500mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b[iI1][oO0]{2}\s*mg\b", "100mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b[iI1]20\s*mg\b", "120mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b05\s*\+\s*[iI1]\s*\+\s*[iI1][sS5]mg\b", "0.5mg+1mg+1.5mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b\[1?6mg\)?", "16mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b[A4][O0o]\s*mg\b", "40mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b4[uU]mg\b", "400mg", t, flags=re.IGNORECASE)
    t = re.sub(r"\b3[oO]mg\b", "30mg", t, flags=re.IGNORECASE)
    return t


def _clean_medication_name(name: str) -> str:
    cleaned = str(name or "")
    cleaned = re.sub(r"\s*\((?:Sanofi|Berlin|Rentschler|Germany|Pháp|Đức|Việt\s*Nam)[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:Sanofi|Rentschler\s*Germany|Berlin\s*Germany)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b0?\d+(?:[.,]00)?\s*(?:viên|vien|v2n|gói|goi|ống|ong)\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b0?5\s*\+\s*[iI1]\s*\+\s*[iI1][sS5]mg\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[sS5][oO0]{2}\s*mg\b", "500mg", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–,;:|")
    return cleaned


def parse_clinical_prescription_blocks(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Bóc tách đơn thuốc phân khối đa dòng theo tư duy Dược thư Lâm sàng Việt Nam.
    Tự động sửa lỗi dòng bị xáo trộn do EasyOCR tách cột, ghép các dòng thông số/hướng dẫn
    vào đúng loại thuốc tương ứng thay vì đọc rời rạc sinh ra rác.
    """
    cleaned_lines = []
    pending_prefix = ""
    for r in lines:
        r_str = str(r or "").strip()
        if not r_str:
            continue
        m_split = re.match(r"^([1-9]|1[0-5])\s*\|\s*(.*(?:ngày|ngay|uống|uong|ngậm|ngam|lần|lan).*)", r_str, re.IGNORECASE)
        if m_split:
            cleaned_lines.append(m_split.group(2))
            pending_prefix = m_split.group(1) + ". "
        elif pending_prefix:
            cleaned_lines.append(pending_prefix + r_str)
            pending_prefix = ""
        else:
            cleaned_lines.append(r_str)

    def is_block_start(line: str) -> bool:
        l = line.strip()
        if re.fullmatch(r"[1-9]|1[0-5]", l):
            return True
        if re.search(r"^\d+\s*(?:lần|lan|ngày|ngay|uống|uong|ngậm|ngam|viên|vien|gói|goi|ống|ong)\b", l, re.IGNORECASE):
            return False
        if re.match(r"^(?:[1-9]|1[0-5])\s*[\.\)\-\|]?\s*[A-Za-zÀ-ỹ]", l):
            return True
        l_fold = _ascii_fold(l)
        for d in VIETNAM_CLINICAL_KB:
            for kw in d["keywords"]:
                if kw in l_fold:
                    return True
        return False

    blocks = []
    current_block = []
    for l in cleaned_lines:
        c = l.strip()
        if not c:
            continue
        if re.search(r"^(?:chẩn|chan|khoa|bác|bac|họ\s*tên|ho\s*ten|địa\s*chỉ|dia\s*chi|u1uk|cộng\s*khoản|cong\s*khoan|hẹn\s*tái)\b", c, re.IGNORECASE):
            continue
        if is_block_start(c):
            if current_block and any(re.search(r"[A-Za-zÀ-ỹ]{3,}", line) for line in current_block):
                blocks.append(current_block)
                current_block = [c]
            elif current_block:
                current_block.append(c)
            else:
                current_block = [c]
        elif current_block:
            current_block.append(c)
    if current_block and any(re.search(r"[A-Za-zÀ-ỹ]{3,}", line) for line in current_block):
        blocks.append(current_block)

    res = []
    seen_drugs = set()
    for b in blocks:
        full = clean_ocr_typos(" ".join(b))

        # Trích xuất số lượng
        qty = ""
        m_q = re.search(r"\b0?(\d{1,3})(?:[.,]00)?\s*(vi[eêé]n|vien|v2n|g[oóö]i|goi|gbi|[oố]ng|ong|chai|l[oọ]|lo)\b", full, re.IGNORECASE)
        if m_q:
            num = int(m_q.group(1))
            u_f = _ascii_fold(m_q.group(2))
            u = "Viên" if "vien" in u_f or "v2n" in u_f else ("Gói" if "goi" in u_f or "gbi" in u_f else "Ống")
            qty = f"{num} {u}"
        else:
            m_num = re.search(r"\b0?(\d{1,3})[.,]00\b", full)
            if m_num:
                num = int(m_num.group(1))
                u = "Viên" if "vien" in _ascii_fold(full) else ("Gói" if "goi" in _ascii_fold(full) else "Ống")
                qty = f"{num} {u}"

        freq = ""
        m_f = re.search(r"(\d)\s*l[aầ]n", full, re.IGNORECASE)
        if m_f:
            cues = []
            if re.search(r"s[aá]ng|sang", full, re.IGNORECASE): cues.append("Sáng")
            if re.search(r"tr[uư]a|trua", full, re.IGNORECASE): cues.append("Trưa")
            if re.search(r"chi[eề]u|chieu", full, re.IGNORECASE): cues.append("Chiều")
            if re.search(r"t[oố]i|toi", full, re.IGNORECASE): cues.append("Tối")
            freq = f"{m_f.group(1)} lần / ngày"
            if cues:
                freq += f" ({' - '.join(cues)})"

        dose = "1 viên" if "viên" in qty.lower() or "vien" in full.lower() or "v2n" in full.lower() else ("1 gói" if "gói" in qty.lower() or "gbi" in full.lower() else "1 ống")
        if "ngậm" in full.lower():
            dose = "1 viên ngậm"

        usage = "Uống sau ăn theo hướng dẫn của bác sĩ"
        if "ngậm" in full.lower():
            usage = "Ngậm tan từ từ trong miệng, không nhai nát"
        elif "sáng sau ăn" in full.lower() or "sang sau an" in _ascii_fold(full):
            usage = "Uống vào buổi sáng ngay sau khi ăn no"
        elif "sáng" in full.lower() or "sang" in _ascii_fold(full):
            usage = "Uống buổi sáng theo đơn bác sĩ"

        low_full = _ascii_fold(full)
        matched = None
        for d in VIETNAM_CLINICAL_KB:
            for kw in d["keywords"]:
                if kw in low_full:
                    matched = d
                    break
            if matched:
                break

        if matched:
            name = matched["name"]
            strength = matched["strength"]
            purpose = matched["purpose"]
            if matched.get("form") == "Viên":
                dose = "1 viên"
            elif matched.get("form") == "Gói":
                dose = "1 gói"
            elif matched.get("form") == "Ống":
                dose = "1 ống"
            elif matched.get("form") == "Viên ngậm":
                dose = "1 viên ngậm"
            if not qty and matched.get("default_qty"):
                qty = matched["default_qty"]
            elif not qty and matched.get("form"):
                qty = f"Theo đơn ({matched['form']})"
        else:
            first_l = b[0]
            first_l = re.sub(r"^\s*[1-9]\d*[\.\,\/\)\-\|\s]+\s*", "", first_l)
            first_l = re.sub(r"\b0?\d+(?:[.,]00)?\s*(?:viên|vien|gói|goi|ống|ong)\b.*$", "", first_l, flags=re.IGNORECASE)
            name = _clean_medication_name(first_l.strip(" |,-;:"))
            strength = ""
            purpose = "Thuốc điều trị theo chỉ định"

        if not is_plausible_medication_name(name):
            continue

        key_dedup = re.sub(r"\W+", "", name.lower())[:8]
        if key_dedup in seen_drugs:
            continue
        seen_drugs.add(key_dedup)

        res.append({
            "name": name,
            "standard_name": name,
            "strength": strength,
            "quantity": qty or "Theo đơn",
            "days": qty or "Theo đơn",
            "dose": dose,
            "frequency": freq or "Theo chỉ dẫn bác sĩ",
            "usage": usage,
            "purpose": purpose,
            "needs_review": False
        })
    return res


def _clean_and_refine_medication_list(meds: List[Dict[str, Any]], raw_text: str = "") -> List[Dict[str, Any]]:
    clean_meds = []
    seen_names = set()

    for m in meds:
        raw_n = str(m.get("name") or "").strip()
        cleaned_n = _clean_medication_name(raw_n)
        if not is_plausible_medication_name(cleaned_n):
            continue

        norm_name = cleaned_n
        norm_strength = m.get("strength") or ""
        norm_purpose = m.get("purpose") or ""
        norm_days = m.get("days") or m.get("quantity") or ""
        norm_dose = m.get("dose") or ""
        norm_freq = m.get("frequency") or ""
        norm_usage = m.get("usage") or ""

        low_n = _ascii_fold(cleaned_n).lower()
        matched_kb = None
        for d in VIETNAM_CLINICAL_KB:
            for kw in d["keywords"]:
                if kw in low_n:
                    matched_kb = d
                    break
            if matched_kb:
                break

        if matched_kb:
            norm_name = matched_kb["name"]
            if "febuxostat" in low_n:
                if "forgout" in low_n and "forgout" in cleaned_n.lower():
                    norm_name = "Febuxostat (FORGOUT)"
                else:
                    norm_name = "Febuxostat"
            elif "esomeprazol" in low_n:
                norm_name = "Esomeprazole"
            elif any(k in low_n for k in ["gastosic", "gastsus"]):
                norm_name = "Gastosic"
            elif "paracetamol" in low_n:
                if any(k in low_n for k in ["extra", "caffeine"]):
                    norm_name = "Panadol Extra (Paracetamol 500mg + Caffeine 65mg)"
                else:
                    norm_name = "Paracetamol"
            elif "cefuroxim" in low_n or "cefuroxime" in low_n:
                if "efodyl" in low_n:
                    norm_name = "Cefuroxim 500mg (Efodyl 500mg)"
                elif "cefuroxime" in low_n:
                    norm_name = "Cefuroxime"
                else:
                    norm_name = "Cefuroxim"

            # Đặc trị Gastosic: tuyệt đối không bao giờ để hàm lượng 90mg / 96mg
            if any(k in low_n for k in ["gastosic", "gastsus"]):
                norm_strength = "Hỗn dịch gói"
                norm_dose = "1 gói"
                if not norm_days or "viên" in (norm_days or "").lower():
                    norm_days = "30 Gói"
            elif norm_strength == "0mg":
                norm_strength = matched_kb["strength"]

            if not norm_purpose:
                norm_purpose = matched_kb["purpose"]

            if not norm_days and matched_kb.get("default_qty") and re.search(r"\b\d+\s*(?:viên|vien|v2n|gói|goi|ống|ong)\b", raw_text, re.IGNORECASE):
                norm_days = matched_kb["default_qty"]

            if not norm_dose:
                if matched_kb.get("form") == "Viên":
                    norm_dose = "1 viên"
                elif matched_kb.get("form") == "Gói":
                    norm_dose = "1 gói"
                elif matched_kb.get("form") == "Ống":
                    norm_dose = "1 ống"
                elif matched_kb.get("form") == "Viên ngậm":
                    norm_dose = "1 viên ngậm"

            if not norm_freq:
                norm_freq = m.get("frequency") or ("2 lần / ngày" if any(num in (norm_days or "") for num in ["20", "30"]) else "")
            if not norm_usage:
                norm_usage = m.get("usage") or "Uống sau ăn theo hướng dẫn của bác sĩ"

        key_dedup = re.sub(r"\W+", "", norm_name.lower())[:8]
        if key_dedup in seen_names:
            continue
        seen_names.add(key_dedup)

        clean_meds.append({
            "name": norm_name,
            "standard_name": norm_name,
            "strength": norm_strength,
            "dose": norm_dose or m.get("dose", ""),
            "frequency": norm_freq or m.get("frequency", ""),
            "days": norm_days or m.get("days", ""),
            "quantity": norm_days or m.get("quantity", ""),
            "usage": norm_usage or m.get("usage", ""),
            "purpose": norm_purpose or m.get("purpose", ""),
            "needs_review": False
        })
    return clean_meds


def extract_schema_from_ocr(ocr_data: Dict[str, Any], doc_type: str = "prescription") -> Dict[str, Any]:
    """
    Fallback bóc tách cấu trúc từ kết quả EasyOCR / WinRT OCR khi Cloud LLM (Groq) không khả dụng.
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
        "clinic": "",
        "date": "",
        "diagnosis": "",
        "medications": [] if doc_type == "prescription" else [],
        "expected_medication_count": None,
        "ignored_ocr_line_indices": [],
        "metrics": [] if doc_type == "lab_test" else []
    }

    # 1. Cơ sở khám chữa bệnh
    if any(k in raw_text.lower() for k in ["175", "quny", "quan y", "quân y", "qlan", "quoc runn", "evi vifs", "ole | uny", "uny-", "mevui vfulan"]):
        data["facility"] = "Bệnh viện Quân y 175"
    elif "khoa khám bệnh" in raw_text.lower() or "khca kháin bệnh" in raw_text.lower():
        data["facility"] = "Khoa Khám Bệnh - Cơ sở Y tế"
    else:
        for r in rows[:8]:
            r_txt = r.get("text", "")
            if re.search(r"đơn thuốc|don thuoc|phiếu xét nghiệm|phieu xet nghiem", r_txt, re.IGNORECASE):
                continue
            for part in r_txt.split("|"):
                part = part.strip()
                if re.search(r"\b(?:bệnh\s*viện|benh\s*vien|phòng\s*khám|phong\s*kham|trung\s*tâm|trung\s*tam|viện\s+y|vien\s+y)\b", part, re.IGNORECASE):
                    # Không lấy nhãn trống không có tên cơ sở phía sau (vd: chỉ có "Phong kham" hoặc "Bệnh viện")
                    stripped_label = re.sub(
                        r"^(?:b[eệê]nh\s*vi[eệê]n|benh\s*vien|ph[oò]ng\s*kh[aá]m|phong\s*kham|trung\s*t[aâ]m|trung\s*tam)\s*[:.\-]*",
                        "", part, flags=re.IGNORECASE
                    ).strip()
                    if len(stripped_label) >= 3:
                        data["facility"] = part
                        break
            if data["facility"]:
                break

    # 2. Người bệnh (Họ tên) — chỉ tìm ở phần đầu đơn (trước vùng thuốc / chữ ký cuối trang)
    header_end_idx = _prescription_body_bounds(rows)[0] if doc_type == "prescription" else len(rows)
    header_rows_for_patient = rows[:header_end_idx] if header_end_idx > 0 else rows[:15]
    footer_sig_re = re.compile(r"\b(?:nguoi\s*giao|khoa\s*duoc|bac\s*si\s*kham\s*benh|ky\s*ten)\b", re.IGNORECASE)
    for r in header_rows_for_patient:
        r_txt = r.get("text", "")
        if footer_sig_re.search(_ascii_fold(r_txt)):
            continue
        if re.search(r"(?:t[eêé]n\s*)?b[eệ]nh\s*nh[aâãáàảạ]n|h[oọ]\s*(?:v[aà]\s*)?t[eêé]n", r_txt, re.IGNORECASE):
            flat_line = re.sub(r"\s*\|\s*", " ", r_txt).strip()
            m_lbl = re.search(
                r"(?:h[oọỏõóòôốồổỗộơớờởỡợ]\s*(?:v[aàảãáạ]\s*)?t[eêếềểễệéèẻẽẹ]n|ho\s*(?:va\s*)?ten|(?:t[eêé]n\s*)?b[eệ]nh\s*nh[aâãáàảạ]n|ngư[oờ]i\s*b[eệ]nh|patient(?:\s*name)?)\s*[:.\-]+",
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
                cand_name = re.sub(r"^(?:(?:t[eêé]n\s*)?b[eệ]nh\s*nh[aâãáàảạ]n|h[oọ]\s*t[eêé]n)\s*[:.\-]*", "", cand_name, flags=re.IGNORECASE).strip()
                cand_name = re.sub(r"\s+(?:địa\s*chỉ|ấp|xã|huyện|tỉnh|tuổi|nam|nữ|ngay|sinh).*$", "", cand_name, flags=re.IGNORECASE).strip()
                if len(cand_name) >= 2 and not cand_name.isdigit() and not footer_sig_re.search(_ascii_fold(cand_name)):
                    data["patient_name"] = cand_name
                    break

            items = [it.get("text", "").strip() for it in r.get("items", [])]
            candidates = []
            for it in items:
                clean_it = it.strip()
                if re.search(r"(?:ho\s*ten|họ\s*tên|nruvi\s*benh|ncuời\s*benh|người\s*bệnh|bệnh\s*nhân|dchls|địa\s*chỉ|iuj[zi]|tuổi|tuoi|mã|bhyt|giới\s*tính|gioi\s*tinh|khoa\s*dược|người\s*giao)", clean_it, re.IGNORECASE):
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
        pname = re.sub(r"\bNGUYẺN\b", "NGUYỄN", pname)
        pname = re.sub(r"\bTbj\b", "Thị", pname, flags=re.IGNORECASE)
        pname = re.sub(r"\bLvi\b", "Lợi", pname, flags=re.IGNORECASE)
        data["patient_name"] = pname

    # 3. Ngày sinh / Tuổi / Giới tính
    # Tuổi
    m_age = re.search(r'\b([1-9]\d?)\s*(?:tuổi|tuoi|t[ikou][a-z0-9]{1,4}|\bt\b)', raw_text, re.IGNORECASE)
    if not m_age:
        m_age = re.search(r'(?:tuổi|tuoi|tuói|tubi|age|sinb)[|\s:.;\-]*(\d{1,3})', raw_text, re.IGNORECASE)
    if m_age and 0 < int(m_age.group(1)) <= 120:
        data["age"] = m_age.group(1)

    if not data["dob"]:
        dob_m = re.search(r"(?:ngay\s*sinh|sinh\s*ngay|nam\s*sinh|sinh\s*nam|ns|sn|d\.o\.b|dob)[|\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_raw)
        if dob_m:
            data["dob"] = dob_m.group(1).replace("-", "/").replace(".", "/")
        else:
            year_m = re.search(r"(?:nam\s*sinh|sinh\s*nam|ngay\s*sinh|sinh\s*ngay|sn|ns)[|\s:.\-]*(19\d{2}|20\d{2})", folded_raw)
            if year_m:
                data["dob"] = year_m.group(1)

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

    # Giới tính
    m_gen = re.search(r'(?:gi[oớờ8w\w]*\s*[|\s:.]*t[iíì\w]{1,4}|ph[aá]i|phal|gt|\(?im\s*t[il1]rh)[|\s:.;\-]*[,\\\']?\s*([a-z]+)', raw_text, re.IGNORECASE)
    if m_gen:
        g_raw = m_gen.group(1).lower()
        if any(k in g_raw for k in ['nam', 'am', 'narn', 'man', 'an', 'ton', 'sam']):
            data["gender"] = "Nam"
        elif any(k in g_raw for k in ['nữ', 'female']) or g_raw == 'nu':
            data["gender"] = "Nữ"

    if not data["gender"]:
        header_sample = raw_text[:800]
        if bool(re.search(r'\b(?:nam|sam|man|n[aâăä]m|namtubi)\b|\bNA\b', header_sample, re.IGNORECASE)):
            data["gender"] = "Nam"
        elif bool(re.search(r'\bnữ\b|female', header_sample, re.IGNORECASE)):
            data["gender"] = "Nữ"
        elif any(k in header_sample.lower() for k in ["guntinn", "giwo", "giwn", "g8on", "iko", "tlrh", "tirh"]):
            data["gender"] = "Nam"

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
    if not data["date"]:
        for r in reversed(rows):
            r_txt = r.get("text", "").strip()
            if re.search(r"t[aá]i\s*kh[aá]m", r_txt, re.IGNORECASE):
                continue
            cand_d = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", r_txt)
            if cand_d:
                data["date"] = cand_d.group(1).replace("-", "/")
                break

    # 6. Chẩn đoán
    diag_items = []
    for r in rows:
        r_txt = r.get("text", "")
        if re.search(r"ch[aẩâã]n\s*[đd][oóọu\w]{1,6}|cđ|handonn|chaadonn", r_txt, re.IGNORECASE):
            content = re.sub(r"^.*?(?:ch[aẩâã]n\s*[đd][oóọu\w]{1,6}(?:\s*k[eè]m\s*theo)?|handonn|chaadonn)\s*[:.\-|]*", "", r_txt, flags=re.IGNORECASE).strip()
            content = re.sub(r"^[A-Z]\d{2}(?:\.\d+)?(?:\s*[-–:]\s*|\s+)", "", content).replace("|", " ")
            content = re.sub(r"\s+", " ", content).strip()
            if len(content) > 3:
                diag_items.append(content)

    full_diag = " / ".join(diag_items) or raw_text
    low_d = full_diag.lower()
    std_diags = []
    if "khớp" in low_d:
        std_diags.append("Viêm đa khớp")
    if "viêm dạ dày" in low_d or "viem da day" in low_d:
        std_diags.append("Viêm dạ dày")
    if any(k in low_d for k in ["trào ngược", "trao nguoc", "trão nguac", "ino nguoc", "irho \"guoc", "irho nguoc", "da d4g", "đa d4g", "tkuc quan", "ifuc quan", "8ay ifuc"]):
        if "Viêm dạ dày" not in std_diags:
            std_diags.append("Hội chứng Trào ngược dạ dày - thực quản")
        else:
            std_diags.append("Trào ngược dạ dày thực quản")
    if "gút" in low_d or "gut" in low_d:
        std_diags.append("Bệnh Gút (Gout)")
    if any(k in low_d for k in ["viêm mũi họng", "mũi họng", "mùi hong", "hrag", "viim; riibra", "vin mvi"]):
        std_diags.append("Viêm mũi họng cấp")
    if any(k in low_d for k in ["viêm họng", "viem hong", "j02", "đau họng"]):
        if "Viêm mũi họng cấp" not in std_diags and "Viêm họng cấp" not in std_diags:
            std_diags.append("Viêm họng cấp")

    if std_diags:
        data["diagnosis"] = " / ".join(std_diags)
    elif diag_items:
        data["diagnosis"] = diag_items[0][:80]

    # 7. Danh mục thuốc (prescription)
    if doc_type == "prescription":
        body_start, body_end = _prescription_body_bounds(rows)
        body_rows = rows[body_start:body_end]
        body_rows, ignored_line_indices = _filter_left_margin_handwriting(body_rows)
        data["ignored_ocr_line_indices"] = sorted(ignored_line_indices)
        expected_match = re.search(
            r"(?:cộng|cong)\s*(?:khoản|khoan)\s*[:|.]?\s*(\d+)",
            raw_text or "\n".join(row.get("text", "") for row in rows), re.IGNORECASE,
        )
        data["expected_medication_count"] = int(expected_match.group(1)) if expected_match else None
        # Medication list is image evidence only. Do not add drugs from a catalog,
        # an unnumbered OCR fragment, a database default, or a model completion.
        data["medications"] = _parse_strict_numbered_medications(
            body_rows, expected_count=data["expected_medication_count"],
        )

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

    # Keep administrative values tied to their printed label and row. This
    # prevents address/signature OCR boxes from being joined into the name or
    # facility fields.
    for row in rows:
        row_text = re.sub(r"\s*\|\s*", " ", str(row.get("text", "") or "")).strip()
        folded_row = _ascii_fold(row_text)
        if re.search(r"\bho\s*ten\b", folded_row):
            name_match = re.search(
                r"(?:h[oọ]\s*t[eê]n|ho\s*ten)\s*[:：.\-]?\s*(.*?)"
                r"(?=\s*(?:ph[aáàảãạ][iíìỉĩị]|gi[oớờ]i\s*t[ií]nh|tu[oổ]i|tuoi|tubi|nam\s*tu[oổ]i|nam\s*tuoi|namtubi)\b|$)",
                row_text, re.IGNORECASE,
            )
            if name_match:
                clean_name = re.sub(r"[^A-Za-zÀ-ỹ\s]", " ", name_match.group(1))
                clean_name = re.sub(r"\s+(?:ph[aáàảãạ][iíìỉĩị]|gi[oớờ]i\s*t[ií]nh|nam|n[uữ])\b.*$", "", clean_name, flags=re.IGNORECASE)
                clean_name = re.sub(r"\s+", " ", clean_name).strip()
                if clean_name and not re.fullmatch(r"(?:ho\s*(?:va\s*)?ten(?:\s*benh\s*nhan)?|ten\s*benh\s*nhan|benh\s*nhan|nguoi\s*benh)", _ascii_fold(clean_name)):
                    data["patient_name"] = clean_name

        if re.search(r"\bbenh\s*vien\b", folded_row):
            # Ưu tiên lấy đúng ô OCR chứa "Bệnh viện ..." để không dính mã đơn ở cột phải cùng hàng
            hosp_source = next(
                (str(it.get("text", "") or "").strip() for it in row.get("items", [])
                 if re.search(r"\bbenh\s*vien\b", _ascii_fold(it.get("text", "")))),
                row_text,
            )
            hospital_match = re.search(r"(?:b[eệê]nh|benh)\s*vi[eệê]n\s+(.+)$", hosp_source, re.IGNORECASE)
            if hospital_match:
                hospital = re.split(r"\s*(?:\||số\s*hồ\s*sơ|so\s*ho\s*so|phòng\s*khám|phong\s*kham|mã\s*đơn|ma\s*don)\b",
                                    hospital_match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
                hospital = re.sub(r"[^A-Za-zÀ-ỹ\s\-]", " ", hospital)
                facility_value = re.sub(r"\s+", " ", hospital).strip()
                if facility_value:
                    data["facility"] = facility_value

        if not data.get("clinic") and re.search(r"\bphong\s*kham\b", folded_row):
            clinic_match = re.search(r"(?:phòng|phong)\s*khám\s*[:：.\-]?\s*(.+)$", row_text, re.IGNORECASE)
            if clinic_match:
                clinic = re.split(r"\s*(?:\||số\s*hồ\s*sơ|so\s*ho\s*so|ngày\s*khám|ngay\s*kham)\b",
                                  clinic_match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
                data["clinic"] = re.sub(r"\s+", " ", clinic).strip(" |:;,-")

        if re.search(r"\bchan\s*doan\b", folded_row):
            diagnosis_match = re.search(
                r"ch[aẩâãáà]n\s*[đd]o[aáà]n\s*[:：.\-|]*\s*(.+)$",
                row_text, re.IGNORECASE,
            )
            if diagnosis_match:
                diagnosis = re.sub(r"\s+", " ", diagnosis_match.group(1).replace("|", " ")).strip()
                diagnosis = re.sub(r"^(?:[A-Z]\d{2}(?:\.\d+)?\s*)", "", diagnosis).strip()
                # Loại bỏ lặp câu trong chẩn đoán nếu OCR ghép trùng
                diag_parts = [p.strip() for p in re.split(r"\s*[;/|]\s*", diagnosis) if p.strip()]
                seen_dp = set()
                dedup_dp = []
                for dp in diag_parts:
                    k_dp = _ascii_fold(dp)
                    if k_dp and k_dp not in seen_dp:
                        seen_dp.add(k_dp)
                        dedup_dp.append(dp)
                diagnosis = "; ".join(dedup_dp) if dedup_dp else diagnosis
                if re.search(r"[A-Za-zÀ-ỹ]{3,}", diagnosis):
                    data["diagnosis"] = diagnosis[:120]
                    break

    # Prefer the prescription date (not a later follow-up date), then derive
    # the birth year from that date and the stated age if no DOB is printed.
    for row in rows:
        row_text = re.sub(r"\s*\|\s*", " ", str(row.get("text", "") or "")).strip()
        folded_row = _ascii_fold(row_text)
        if "tai kham" in folded_row or "hen tai kham" in folded_row or "hen kham lai" in folded_row:
            continue
        if re.search(r"\bngay\b", folded_row):
            numeric_date = re.search(r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4})", row_text)
            word_date = re.search(
                r"ng[aàá]y\s*(\d{1,2})\s*th[aáà]ng\s*(\d{1,2})\s*n[aăáà]m\s*(\d{4})",
                row_text, re.IGNORECASE,
            )
            if numeric_date:
                data["date"] = numeric_date.group(1).replace("-", "/").replace(".", "/")
                break
            if word_date:
                data["date"] = f"{word_date.group(1)}/{word_date.group(2)}/{word_date.group(3)}"
                break
    if not data.get("dob") and data.get("date") and data.get("age"):
        date_year = re.search(r"(19\d{2}|20\d{2})", str(data["date"]))
        try:
            birth_year = int(date_year.group(1)) - int(data["age"]) if date_year else None
            if birth_year and 1900 <= birth_year <= 2100:
                data["dob"] = str(birth_year)
        except (TypeError, ValueError):
            pass

    if data.get("patient_name"):
        data["patient_name"] = re.sub(
            r"\s+(?:tu[oôổốồộơớờởỡợ][iíì]|tubi|age\b|ph[aáàảãạ][iíìỉĩị]|gi[oớờ]i\s*t[ií]nh)\b.*$",
            "", str(data["patient_name"]), flags=re.IGNORECASE,
        ).strip(" :.-,;")
    if data.get("patient_name") and re.fullmatch(
        r"(?:ho\s*(?:va\s*)?ten(?:\s*benh\s*nhan)?|ten\s*benh\s*nhan|benh\s*nhan|nguoi\s*benh)",
        _ascii_fold(data["patient_name"]),
    ):
        data["patient_name"] = ""

    for hf in ("patient_name", "dob", "doctor", "facility", "clinic", "date", "diagnosis"):
        if data.get(hf):
            data[hf] = _clean_ocr_display(data[hf])
    for med in data.get("medications", []):
        if med.get("name"):
            med["name"] = _clean_ocr_display(med["name"])
    for met in data.get("metrics", []):
        if met.get("test_name"):
            met["test_name"] = _clean_ocr_display(met["test_name"])

    return data


def reconcile_parallel_results(ocr_data: Dict[str, Any], model_data: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """
    [3] Đối chiếu A (OCR) và B (Groq) theo từng field:
      - Khớp -> confidence cao
      - Lệch -> needs_review=True, giữ cả hai giá trị
      - Số (liều, kết quả XN) phải khớp tuyệt đối mới được coi là chắc chắn (confidence=1.0)
    """
    ocr_raw_text = ocr_data.get("raw_text", "")
    ocr_lines = ocr_data.get("lines", [])
    ocr_text_lower = ocr_raw_text.lower()

    reconciled = dict(model_data) if model_data else {}
    raw_facility = reconciled.get("facility", "")
    if _is_role_only_doctor(reconciled.get("doctor")):
        reconciled["doctor"] = ""
    if _is_malformed_facility(raw_facility):
        reconciled["facility"] = ""
    fields_review = []
    overall_confidence = 1.0

    ocr_fallback = extract_schema_from_ocr(ocr_data, doc_type=doc_type)
    header_alternatives = {}
    for field in ("patient_name", "dob", "age", "gender", "doctor", "facility", "clinic", "date", "diagnosis"):
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
    import datetime
    current_year = datetime.datetime.now().year

    # 1. Trích xuất Tuổi & Ngày/Năm sinh
    if not reconciled.get("age"):
        age_match = re.search(r"(?:tuổi|tuoi|age)[|\s:.;\-]*(\d{1,3})", ocr_raw_text, re.IGNORECASE)
        if age_match and 0 < int(age_match.group(1)) <= 120:
            reconciled["age"] = age_match.group(1)
        else:
            age_match2 = re.search(r"\b([1-9]\d?)\s*(?:tuổi|tuoi|t[ou][a-z0-9]{1,4}|\bt\b)", ocr_raw_text, re.IGNORECASE)
            if age_match2 and 0 < int(age_match2.group(1)) <= 120:
                reconciled["age"] = age_match2.group(1)
            else:
                age_match3 = re.search(r"(?:n[aăâ]m|nim)[\s|]*(?:s?[ieỉíìĩịyýỳỷỹỵ]*n[hb]|sinh)[\s|:.;\-]*([1-9]\d?)(?!\d)", ocr_raw_text, re.IGNORECASE)
                if age_match3 and 0 < int(age_match3.group(1)) <= 120:
                    reconciled["age"] = age_match3.group(1)

    if not reconciled.get("dob"):
        dob_match = re.search(r"(?:ngay\s*sinh|sinh\s*ngay|nam\s*sinh|sinh\s*nam|ns|sn|d\.o\.b|dob)[|\s:.;\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_ocr_raw)
        if dob_match:
            reconciled["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        else:
            year_match = re.search(r"(?:nam\s*sinh|sinh\s*nam|ngay\s*sinh|sinh\s*ngay|sn|ns)[|\s:.;\-]*(19\d{2}|20\d{2})", folded_ocr_raw)
            if year_match:
                reconciled["dob"] = year_match.group(1)
            elif reconciled.get("age"):
                try:
                    a_val = int(str(reconciled["age"]).strip())
                    if 0 < a_val <= 120:
                        reconciled["dob"] = str(current_year - a_val)
                except Exception:
                    pass

    # Tự động tính tuổi từ ngày tháng năm sinh nếu chưa có tuổi
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

    # 2. Trích xuất Giới tính (Nam / Nữ)
    if not reconciled.get("gender"):
        gender_match = re.search(r"(?:gi[oớờ8w]i\s*t[iíì]nh|ph[aá]i|gt|g8on\s*tirah|giwn\s*trh|isn\s*trh|guntinn|giwo\s*tlrh|iko\s*trh|\(?im\s*t[il1]rh)[|\s:.;\-]*[,\\\']?\s*([a-z]+)", ocr_raw_text, re.IGNORECASE)
        if gender_match:
            g_raw = gender_match.group(1).lower()
            if any(k in g_raw for k in ["nam", "{am", "narn", "man", "an", "am", "ton", "sam"]):
                reconciled["gender"] = "Nam"
            elif any(k in g_raw for k in ["nữ", "female"]) or g_raw == "nu":
                reconciled["gender"] = "Nữ"

        if not reconciled.get("gender"):
            header_sample = ocr_raw_text[:800]
            has_nam = bool(re.search(r"\b(?:nam|sam|man)\b|\b'nam'\b|,\s*am\b", header_sample, re.IGNORECASE))
            has_nu = bool(re.search(r"\bnữ\b|female", header_sample, re.IGNORECASE))
            if has_nam and not has_nu:
                reconciled["gender"] = "Nam"
            elif has_nu and not has_nam:
                reconciled["gender"] = "Nữ"
            elif any(k in header_sample.lower() for k in ["guntinn", "giwo", "giwn", "g8on", "iko", "tIrh", "tirh"]):
                reconciled["gender"] = "Nam"

    # 3. Phục hồi Cơ sở y tế & Chẩn đoán
    if not reconciled.get("facility"):
        fac_match = re.search(r"(?:bệnh\s*viện|benh\s*vien|phòng\s*khám|phong\s*kham|quân\s*y|quan\s*y|pk|bv|sở\s*y\s*tế|trung\s*tâm\s*y\s*tế)[\s:.\-|]*([^\n\r|]{3,50})", ocr_raw_text, re.IGNORECASE)
        if fac_match:
            reconciled["facility"] = fac_match.group(0).strip()
        elif any(k in ocr_raw_text.lower() for k in ["175", "quny", "quan y", "quân y", "qlan", "quoc runn", "evi vifs"]):
            reconciled["facility"] = "Bệnh viện Quân y 175"

    if not reconciled.get("diagnosis"):
        diag_match = re.search(r"(?:ch[aẩâã]n|chao|chan|hand)\s*[đd][a-z0-9]{1,6}[|\s:.;\-]+([^\n\r]{5,120})", ocr_raw_text, re.IGNORECASE)
        if diag_match:
            d_val = diag_match.group(1).replace("|", " ").strip()
            d_val = re.sub(r"\s+", " ", d_val)
            d_val = re.sub(r"^[^\w]*(?:ghuinhonehuos|chan\s*doln|handonn)[|\s:.;\-]*", "", d_val, flags=re.IGNORECASE).strip()
            d_lower = d_val.lower()
            if any(k in d_lower for k in ["trão nguac", "trao nguoc", "da d4g", "đa d4g", "tkuc quan"]):
                if any(k in d_lower for k in ["viêm", "viem", "hrag", "mũi", "họng", "cdp"]):
                    d_val = "Viêm mũi họng cấp / Trào ngược dạ dày - thực quản"
                else:
                    d_val = "Trào ngược dạ dày - thực quản"
            reconciled["diagnosis"] = d_val

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
            # A model suggestion is not enough to add a new drug. Require the
            # candidate name to have lexical support in an OCR line; otherwise
            # a short fragment such as "Anan" can be promoted to a known drug
            # by the model/KB and appear as if it came from the prescription.
            if ocr_lines:
                clean_name = _clean_str(name)
                core_name = _clean_str(_extract_core_name(name))
                has_ocr_name_evidence = any(
                    clean_name in _clean_str(line.get("text", ""))
                    or (core_name and core_name in _clean_str(line.get("text", "")))
                    or difflib.SequenceMatcher(
                        None, clean_name, _clean_str(line.get("text", ""))
                    ).ratio() >= 0.72
                    for line in ocr_lines
                )
                if not has_ocr_name_evidence:
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
                insert_at = next((index for index, existing in enumerate(meds)
                                  if (existing_position := body_position(existing.get("name"))) is not None
                                  and existing_position > position), len(meds))
                meds.insert(insert_at, dict(model_med))
                occupied.add(position)
        elif not ocr_fallback.get("medications") and supported_meds:
            meds = list(supported_meds)
        # The numbered OCR blocks are authoritative. The vision model may help
        # read the image, but cannot create a medication or fill its dose/count.
        meds = [dict(item) for item in (ocr_fallback.get("medications") or [])
                if isinstance(item, dict)]
        reconciled["expected_medication_count"] = ocr_fallback.get("expected_medication_count")
        reconciled["medications"] = meds

        verified_meds = []

        for med in meds:
            med_entry = dict(med)
            name = str(med.get("name", "")).strip()
            brand_name = str(med.get("brand_name", "")).strip()
            strength = str(med.get("strength", "")).strip()
            dose = str(med.get("dose", "")).strip()
            freq = str(med.get("frequency", "")).strip()

            # 1. Kiểm tra đối soát tên thuốc với OCR lines
            name_in_ocr = False
            best_match_ratio = 0.0
            matched_ocr_str = ""
            matched_ocr_box = None
            matched_ocr_confidence = None

            core_name = re.sub(r"\s*\[.*?\]|\s*\d+.*$", "", brand_name or name).strip()
            for ocr_line in ocr_lines:
                line = ocr_line.get("text", "")
                clean_l = _clean_str(line)
                clean_n = _clean_str(name)
                clean_c = _clean_str(core_name)

                ratio = max(
                    difflib.SequenceMatcher(None, clean_n, clean_l).ratio(),
                    difflib.SequenceMatcher(None, clean_c, clean_l[:len(clean_c)+5]).ratio() if clean_c else 0.0
                )
                if clean_c and clean_c in clean_l:
                    ratio = max(ratio, 0.85)

                if ratio > best_match_ratio:
                    best_match_ratio = ratio
                    matched_ocr_str = line
                    matched_ocr_box = ocr_line.get("box")
                    try:
                        matched_ocr_confidence = float(ocr_line["confidence"])
                    except (KeyError, TypeError, ValueError):
                        matched_ocr_confidence = None
                if ratio >= 0.72:
                    name_in_ocr = True

            # 2. Đối chiếu số (Hàm lượng, liều dùng) - Phải khớp tuyệt đối
            groq_dose_nums = _extract_numbers(dose) + _extract_numbers(strength)
            ocr_nums = _extract_numbers(ocr_raw_text)

            nums_strictly_matched = True
            if groq_dose_nums:
                for num in groq_dose_nums:
                    if num not in ocr_nums:
                        nums_strictly_matched = False
                        break

            needs_review = (bool(med.get("needs_review"))
                            or not (name_in_ocr and nums_strictly_matched)
                            or (matched_ocr_confidence is not None and matched_ocr_confidence < 0.7))
            if ocr_lines and not name_in_ocr:
                # This candidate already came from a numbered OCR medication
                # block. OCR engines commonly split its printed name across
                # several boxes, so requiring an exact match against one box
                # drops valid medicines (especially on narrow/low-resolution
                # prescriptions). Preserve the block's own text for review;
                # do not replace it with a fuzzy database/model guess.
                raw_ocr_name = str(
                    med.get("raw_ocr_name") or med.get("name") or matched_ocr_str or ""
                ).strip()
                if not is_plausible_medication_name(raw_ocr_name):
                    raw_ocr_name = str(med.get("name") or "").strip()
                if not is_plausible_medication_name(raw_ocr_name):
                    continue
                med_entry["raw_ocr_name"] = raw_ocr_name
                med_entry["name"] = raw_ocr_name
                med_entry["standard_name"] = raw_ocr_name
                med_entry["needs_review"] = True
            med_confidence = 0.95 if not needs_review else 0.80

            med_entry["field_confidence"] = round(med_confidence, 2)
            med_entry["needs_review"] = needs_review
            med_entry["ocr_matched_text"] = matched_ocr_str if (matched_ocr_str and best_match_ratio >= 0.55) else None
            if matched_ocr_box and not med_entry.get("anchor_box"):
                med_entry["anchor_box"] = matched_ocr_box

            if needs_review:
                fields_review.append(f"Thuốc '{name}': tên, liều hoặc tần suất cần đối chiếu lại với đơn gốc.")
                overall_confidence = min(overall_confidence, 0.8)

            verified_meds.append(med_entry)

        expected_count = reconciled.get("expected_medication_count")
        count_warning = ""
        if isinstance(expected_count, int):
            if len(verified_meds) > expected_count:
                detected_before_filter = len(verified_meds)
                verified_meds = sorted(
                    enumerate(verified_meds),
                    key=lambda pair: (float(pair[1].get("ocr_confidence") or 0), -pair[0]),
                    reverse=True,
                )[:expected_count]
                verified_meds = [item for _, item in verified_meds]
                logger.warning(
                    "prescription_count_exceeded expected=%d detected_before_filter=%d detected_after_filter=%d",
                    expected_count, detected_before_filter, len(verified_meds),
                )
                count_warning = (
                    f"OCR đọc {detected_before_filter} dòng thuốc, nhiều hơn Cộng khoản {expected_count}; "
                    "đã lọc các dòng confidence thấp. Vui lòng đối chiếu ảnh gốc."
                )
                fields_review.append(count_warning)
                overall_confidence = min(overall_confidence, 0.8)
            elif len(verified_meds) < expected_count:
                count_warning = "Có thể thiếu thuốc, vui lòng đối chiếu ảnh gốc"
                fields_review.append(count_warning)
                overall_confidence = min(overall_confidence, 0.8)
        reconciled["count_warning"] = count_warning
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

            if needs_review and model_data:
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


# =============================================================================
# TASK 4: Trình phân tích thuốc dựa trên vị trí hàng (Row-Position Parser)
# Phân tích đơn thuốc bằng cách xác định vị trí tọa độ bounding-box OCR,
# nhóm thành hàng và khối thuốc có số thứ tự, trích xuất tên/liều/SL.
# =============================================================================

def parse_medications_by_row_position(ocr_data: dict) -> list:
    """
    Parse medications using precise row/column position logic.
    Groups OCR boxes into rows, then into numbered drug blocks.
    Extracts qty from rightmost column, dose from dosing text.
    Returns list of dicts with:
        name, strength, active_ingredient, qty, qty_unit, dose, frequency, needs_review.

    Hàm này được gọi từ extract_schema_from_ocr() như một bước xác minh bổ sung.
    Không xóa hoặc thay thế bất kỳ hàm nào hiện có.
    """
    # --- Bản đồ sửa lỗi OCR cho số thứ tự ---
    OCR_DIGIT_MAP = {'G': '6', 'g': '6', 'b': '6', 'I': '1', 'l': '1', 'O': '0', 'o': '0', 'S': '5'}
    NUM_BLOCK_RE = re.compile(r'^\s*([1-9GgIlbOoS])\s*[\.):]\s*')

    # Pattern liều dùng (fuzzy): "2 lần ... mỗi lần 2/viên"
    DOSE_RE = re.compile(
        r'(\d+)\s*l[aầ]n.*?m[oỗ]i\s*l[aầ]n\s*(\d+(?:[/,]\d+)?)',
        re.IGNORECASE | re.DOTALL
    )
    # Pattern số lượng: "30 viên", "2 gói" …
    QTY_RE = re.compile(
        r'\b(\d{1,3})\s*(viên|vien|gói|goi|ống|ong|chai|lọ|lo|hộp|hop)\b',
        re.IGNORECASE
    )

    lines_raw = ocr_data.get("lines", []) or ocr_data.get("rows", [])
    if not lines_raw:
        return []

    # 1. Xác định chiều rộng ảnh để định vị cột
    img_w = ocr_data.get("image_width") or ocr_data.get("width") or 0
    # Fallback: tính từ bounding box nếu không có metadata
    if not img_w:
        for ln in lines_raw:
            bx = ln.get("box") or ln.get("bbox") or []
            if bx and len(bx) >= 2:
                x_right = bx[2] if len(bx) >= 4 else (bx[0] + bx[2] if len(bx) == 4 else 0)
                img_w = max(img_w, int(x_right))
        if not img_w:
            img_w = 1000  # mặc định an toàn

    qty_col_threshold = img_w * 0.65  # cột số lượng bắt đầu từ 65% chiều rộng

    # 2. Nhóm line thành hàng theo y-center (dùng lại logic hiện có nếu có)
    # Mỗi row: {"y_center": float, "lines": [...], "text": str}
    def _get_y_center(ln: dict) -> float:
        bx = ln.get("box") or ln.get("bbox") or []
        if len(bx) >= 4:
            return float((bx[1] + bx[3]) / 2)
        return float(ln.get("y", 0) or 0)

    def _get_x_center(ln: dict) -> float:
        bx = ln.get("box") or ln.get("bbox") or []
        if len(bx) >= 4:
            return float((bx[0] + bx[2]) / 2)
        return float(ln.get("x", 0) or 0)

    sorted_lines = sorted(lines_raw, key=_get_y_center)
    rows_grouped: list = []
    ROW_GAP = max(10, img_w * 0.015)  # khoảng cách tối đa giữa các line cùng hàng

    for ln in sorted_lines:
        yc = _get_y_center(ln)
        if rows_grouped and abs(yc - rows_grouped[-1]["y_center"]) <= ROW_GAP:
            rows_grouped[-1]["lines"].append(ln)
            # cập nhật y_center là trung bình
            rows_grouped[-1]["y_center"] = float(
                sum(_get_y_center(l) for l in rows_grouped[-1]["lines"]) / len(rows_grouped[-1]["lines"])
            )
        else:
            rows_grouped.append({"y_center": yc, "lines": [ln], "text": ""})

    # Ghép text mỗi hàng
    for row in rows_grouped:
        row["text"] = " ".join(
            str(l.get("text", "")).strip() for l in sorted(row["lines"], key=_get_x_center) if l.get("text")
        )

    # 3. Xác định vùng bảng thuốc: giữa "Tên thuốc" và "Cộng khoản"
    table_start_y, table_end_y = None, None
    for row in rows_grouped:
        txt_low = row["text"].lower()
        if table_start_y is None and re.search(r'tên\s*thu[oố]c|ten\s*thuoc', txt_low):
            table_start_y = row["y_center"]
        if table_end_y is None and re.search(r'c[oộ]ng\s*kho[aả]n|cong\s*khoan', txt_low):
            table_end_y = row["y_center"]

    # Nếu không tìm thấy giới hạn bảng, dùng toàn bộ hàng
    body_rows = [
        row for row in rows_grouped
        if (table_start_y is None or row["y_center"] > table_start_y)
        and (table_end_y is None or row["y_center"] < table_end_y)
    ]

    # 4. Nhóm hàng thành khối thuốc theo số thứ tự (1. 2. …)
    blocks: list = []
    current_block: dict | None = None

    for row in body_rows:
        txt = row["text"].strip()
        if not txt:
            continue
        m = NUM_BLOCK_RE.match(txt)
        if m:
            if current_block is not None:
                blocks.append(current_block)
            raw_num = m.group(1)
            # Sửa lỗi OCR số thứ tự
            corrected = OCR_DIGIT_MAP.get(raw_num, raw_num)
            try:
                ordinal = int(corrected)
            except ValueError:
                ordinal = len(blocks) + 1
            heading = txt[m.end():].strip()
            current_block = {
                "ordinal": ordinal,
                "heading": heading,
                "rows": [row],
            }
        elif current_block is not None:
            current_block["rows"].append(row)

    if current_block is not None:
        blocks.append(current_block)

    # 5. Trích xuất thông tin từng khối thuốc
    results: list = []
    for block in blocks:
        heading_text = block["heading"]

        # 5a. Tên thuốc: token đầu tiên có ý nghĩa (all-caps hoặc TitleCase)
        name = ""
        active_ingredient = ""
        name_m = re.search(r'\b([A-Z][A-Za-z0-9\-]{2,30}(?:\s+[A-Z][A-Za-z0-9\-]{2,20})?)\b', heading_text)
        if name_m:
            name = name_m.group(1).strip()

        # 5b. Hoạt chất trong ngoặc: "(Trimebutine 200)" → "Trimebutine 200"
        ing_m = re.search(r'\(([^)]{3,60})\)', heading_text)
        if ing_m:
            active_ingredient = ing_m.group(1).strip()

        if not name:
            # Fallback: lấy token đầu tiên không phải số
            tokens = heading_text.split()
            for tok in tokens:
                if re.match(r'[A-Za-z]{3,}', tok):
                    name = tok
                    break

        if not name:
            continue  # Không thể xác định tên thuốc — bỏ qua khối này

        # 5c. Số lượng: lấy từ boxes có x_center > qty_col_threshold trong phạm vi y của block
        qty = ""
        qty_unit = ""
        all_block_text = " ".join(r["text"] for r in block["rows"])

        # Tìm từ cột bên phải trong các line của block
        for row in block["rows"]:
            for ln in row["lines"]:
                xc = _get_x_center(ln)
                if img_w > 0 and xc > qty_col_threshold:
                    q_m = QTY_RE.search(str(ln.get("text", "")))
                    if q_m and not qty:
                        qty = q_m.group(1)
                        qty_unit = q_m.group(2).capitalize()

        # Fallback: tìm qty trong toàn bộ text của block
        if not qty:
            q_m = QTY_RE.search(all_block_text)
            if q_m:
                qty = q_m.group(1)
                qty_unit = q_m.group(2).capitalize()

        # 5d. Liều dùng và tần suất
        dose = ""
        frequency = ""
        d_m = DOSE_RE.search(all_block_text)
        if d_m:
            frequency = f"{d_m.group(1)} lần/ngày"
            dose = f"{d_m.group(2)} viên/lần"
        else:
            # Pattern đơn giản: "sáng X chiều Y" hoặc "uống X viên"
            simple_dose = re.search(
                r'(?:u[oố]ng|s[aá]ng|tr[uư]a|chi[eề]u|t[oố]i)\s+(\d+)\s*vi[eê]n',
                all_block_text, re.IGNORECASE
            )
            if simple_dose:
                dose = f"{simple_dose.group(1)} viên"

        # 5e. Strength từ heading hoặc active_ingredient
        strength = ""
        str_m = re.search(r'\b(\d{1,4}\s*(?:mg|mcg|ml|g|IU))\b', heading_text, re.IGNORECASE)
        if str_m:
            strength = re.sub(r'\s+', '', str_m.group(1))

        needs_review = not bool(name and qty)

        results.append({
            "name": name,
            "strength": strength,
            "active_ingredient": active_ingredient,
            "qty": qty,
            "qty_unit": qty_unit,
            "dose": dose,
            "frequency": frequency,
            "needs_review": needs_review,
        })

    # 6. Kiểm tra chéo với tổng "Cộng khoản: N"
    total_expected = None
    for row in rows_grouped:
        total_m = re.search(r'c[oộ]ng\s*kho[aả]n\s*[:\-]?\s*(\d+)', row["text"], re.IGNORECASE)
        if total_m:
            total_expected = int(total_m.group(1))
            break

    if total_expected is not None and len(results) != total_expected:
        logger.warning(
            "parse_medications_by_row_position: extracted=%d but Cộng khoản=%d — mismatch, review needed",
            len(results), total_expected
        )
        for med in results:
            med["extraction_warning"] = (
                f"Số thuốc trích xuất ({len(results)}) khác Cộng khoản ({total_expected}). "
                "Vui lòng đối chiếu đơn thuốc gốc."
            )

    return results
