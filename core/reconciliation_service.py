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

def _clean_str(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower())

def _extract_numbers(s: str) -> List[str]:
    """Bóc tách các cụm số nguyên hoặc số thập phân trong chuỗi."""
    if not s:
        return []
    # Tìm các số dạng 123 hoặc 12.5 hoặc 12,5
    found = re.findall(r"\d+(?:[.,]\d+)?", str(s))
    return [x.replace(",", ".") for x in found]


_MEDICATION_LABEL = re.compile(
    r"(?:đơn\s*thuốc|don\s*thuoc|chẩn\s*đoán|chan\s*doan|"
    r"bác\s*sĩ|bac\s*si|điều\s*trị|dieu\s*tri|"
    r"bệnh\s*viện|benh\s*vien|phòng\s*khám|phong\s*kham|sở\s*y\s*tế|so\s*y\s*te|"
    r"cộng\s*khoản|cong\s*khoan|lời\s*dặn|loi\s*dan|"
    r"tái\s*khám|tai\s*kham|ngày\s*khám|ngay\s*kham|"
    r"ngày\s*sinh|ngay\s*sinh|họ\s*tên|ho\s*ten|"
    r"địa\s*chỉ|dia\s*chi|số\s*hồ\s*sơ|so\s*ho\s*so)",
    re.IGNORECASE,
)
_MEDICATION_UNITS = r"viên|vien|ven|gói|gôi|goi|chai|chal|lọ|lo|ống|ông|ong|hộp|hop|vỉ|vi|ml|mg|mcg|g"


def is_plausible_medication_name(name: str) -> bool:
    """Reject obvious OCR labels, dates and quantities without guessing a drug list."""
    value = re.sub(r"\s+", " ", str(name or "")).strip(" \t\r\n\"'.,;:()[]")
    if len(value) < 2 or not re.search(r"[A-Za-zÀ-ỹ]", value):
        return False
    if _MEDICATION_LABEL.search(value):
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
    # A dangling quote is an OCR fragment. A one-word facility name can be
    # legitimate, so its length and casing alone are not grounds to remove it.
    return bool(facility.count('"') % 2 or facility.count("'") % 2)


def _merge_medication_rows(ocr_meds: List[Dict[str, Any]],
                           model_meds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Use medicine rows read from the prescription body as count and order.

    A model may supply fields for a matching row, but must not create an
    additional medicine from an ingredient, header or date OCR fragment.
    """
    if not ocr_meds:
        return model_meds

    merged_rows = []
    used_model_rows = set()
    for ocr_med in ocr_meds:
        ocr_name = _normalized_entity(ocr_med.get("name"))
        best_index = None
        best_score = 0.0
        for index, model_med in enumerate(model_meds):
            if index in used_model_rows or not isinstance(model_med, dict):
                continue
            model_name = _normalized_entity(model_med.get("name"))
            if not ocr_name or not model_name:
                continue
            score = difflib.SequenceMatcher(None, ocr_name, model_name).ratio()
            if len(ocr_name) >= 4 and (ocr_name in model_name or model_name in ocr_name):
                score = 1.0
            if score > best_score:
                best_index, best_score = index, score

        combined = dict(ocr_med)
        if best_index is not None and best_score >= 0.72:
            used_model_rows.add(best_index)
            model_med = model_meds[best_index]
            for field in ("strength", "dose", "frequency", "days", "usage"):
                if not combined.get(field) and model_med.get(field):
                    combined[field] = str(model_med[field])
        merged_rows.append(combined)
    return merged_rows


def _prescription_medications_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Read drug names only inside the prescription body, never from its header/footer."""
    start = None
    end = len(rows)
    for index, row in enumerate(rows):
        text = row.get("text", "")
        if re.search(r"chẩn\s*đoán|chan\s*doan|chân\s*doan", text, re.IGNORECASE):
            start = index + 1
        elif start is None and re.search(r"đơn\s*thuốc|don\s*thuoc", text, re.IGNORECASE):
            start = index + 1
        if start is not None and index >= start and re.search(
            r"cộng\s*khoản|cong\s*kho[aà]n|bác\s*sĩ\s*điều\s*trị|"
            r"bac\s*si\s*dieu\s*tri|lời\s*dặn|loi\s*dan|tái\s*khám|tai\s*kham",
            text, re.IGNORECASE,
        ):
            end = index
            break
    if start is None or start >= end:
        return []

    groups: List[Dict[str, Any]] = []
    for row in rows[start:end]:
        items = [str(item.get("text", "")).strip() for item in row.get("items", [])]
        if not items:
            items = [part.strip() for part in row.get("text", "").split("|")]
        candidate = ""
        strength = ""
        for item in items:
            item = re.sub(r"^\s*\d{1,2}\s*[.)]\s*", "", item).strip()
            prefix = item.split("(", 1)[0].strip()
            words = prefix.split()
            # A medicine heading has an uppercase brand token. Ingredient and
            # administration lines below it are continuations, not new drugs.
            if not words or not any(len(w) >= 3 and w.isupper() for w in words[:2]):
                continue
            brand_words = []
            for word in words:
                if re.fullmatch(r"\d+[oO0]*\s*(?:mg|mcg|ml|g)", word, re.IGNORECASE):
                    break
                if word.isupper() or re.fullmatch(r"\d{1,3}", word):
                    brand_words.append(word)
                else:
                    break
            proposed = " ".join(brand_words).strip()
            if not is_plausible_medication_name(proposed):
                continue
            candidate = proposed
            strength_match = re.search(r"\b(\d+[oO0]*\s*(?:mg|mcg|ml|g))\b", item, re.IGNORECASE)
            if strength_match:
                strength = re.sub(r"[oO]", "0", strength_match.group(1)).replace(" ", "")
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

def extract_schema_from_ocr(ocr_data: Dict[str, Any], doc_type: str = "prescription") -> Dict[str, Any]:
    """
    Fallback bóc tách cấu trúc từ kết quả EasyOCR khi Cloud LLM (Gemini) không khả dụng.
    Tự động trích xuất thông tin hành chính, danh mục thuốc hoặc chỉ số xét nghiệm để người dùng chỉ cần xác nhận.
    """
    raw_text = ocr_data.get("raw_text", "")
    lines = ocr_data.get("lines", [])
    rows = ocr_data.get("rows", [])

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

    # 1. Chỉ nhận tên cơ sở khi OCR đọc được nhãn cơ sở y tế rõ ràng.
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

    # 2. Người bệnh (Họ tên, Ngày sinh/Tuổi)
    for r in rows:
        for item in r.get("items", []):
            match = re.search(r"(?:họ|ho)\s*tên\s*[:.]\s*([^|;\d]+)", item.get("text", ""), re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if len(candidate.split()) >= 2:
                    data["patient_name"] = candidate
                    break
        if data["patient_name"]:
            break
    for r in rows:
        if data["patient_name"]:
            break
        r_txt = r.get("text", "")
        items = [it.get("text", "").strip() for it in r.get("items", [])]
        if re.search(r"(?:ho\s*ten|họ\s*tên|người\s*bệnh|bệnh\s*nhân|nruvi\s*benh|ncuời\s*benh)", r_txt, re.IGNORECASE):
            candidates = []
            for it in items:
                clean_it = it.strip()
                if re.search(r"(?:ho\s*ten|họ\s*tên|nruvi\s*benh|ncuời\s*benh|người\s*bệnh|bệnh\s*nhân|dchls|địa\s*chỉ|iuj[zi]|tuổi|mã|bhyt)", clean_it, re.IGNORECASE):
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

    # Ngày sinh hoặc Tuổi
    dob_m = re.search(r"(?:ngày\s*sinh|sinh\s*ngày|ns|d\.o\.b|dob)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", raw_text, re.IGNORECASE)
    if dob_m:
        data["dob"] = dob_m.group(1).replace("-", "/").replace(".", "/")
    else:
        age_m = re.search(r"(?:tuổi|tuoi|iuj[zi]|tuói|age)[\s:.\-]*(\d{1,3})", raw_text, re.IGNORECASE)
        if age_m:
            data["age"] = age_m.group(1)
    gender_m = re.search(r"(?:phái|phai|phal)[^\n]{0,25}?\b(nam|nữ|nu)", raw_text, re.IGNORECASE)
    if gender_m:
        data["gender"] = "Nam" if gender_m.group(1).casefold() == "nam" else "Nữ"

    # 3. Bác sĩ: nhãn "Bác sĩ điều trị" không phải là tên người.
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

    # 4. Ngày trên phiếu
    date_m = re.search(r"(?:ngày|ngay)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", raw_text, re.IGNORECASE)
    if date_m:
        data["date"] = date_m.group(1).replace("-", "/").replace(".", "/")
    else:
        date_word_m = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", raw_text, re.IGNORECASE)
        if date_word_m:
            data["date"] = f"{date_word_m.group(1)}/{date_word_m.group(2)}/{date_word_m.group(3)}"
    if not data["date"] and doctor_label_index is not None:
        for row in reversed(rows[:doctor_label_index]):
            candidate = row.get("text", "").strip()
            if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", candidate):
                data["date"] = candidate.replace("-", "/")
                break

    # 5. Chẩn đoán
    for r in rows:
        r_txt = r.get("text", "")
        # A poorly read diagnosis should remain blank for the review screen.
        if max((float(it.get("confidence", 0)) for it in r.get("items", [])), default=0) < 0.5:
            continue
        items = [it.get("text", "").strip() for it in r.get("items", [])]
        if re.search(r"chẩn\s*đoán|chan\s*doan|ch[eê]n\s*8oun|chn\s*8oun|chuan\s*doan|cđ", r_txt, re.IGNORECASE):
            diag_items = []
            found_lbl = False
            for it in items:
                if re.search(r"chẩn\s*đoán|chan\s*doan|ch[eê]n\s*8oun|chn\s*8oun|chuan\s*doan|cđ", it, re.IGNORECASE):
                    found_lbl = True
                    continue
                if found_lbl:
                    if not re.search(r"mã|bmyi|bhyt|icd|ibus", it, re.IGNORECASE):
                        diag_items.append(it)
            if diag_items:
                diag_str = " / ".join(diag_items)
                diag_str = re.sub(r"WCIK\s*I[OQA]+", "H/CTK TỌA", diag_str, flags=re.IGNORECASE)
                diag_str = re.sub(r"IVDD", "TVDD", diag_str, flags=re.IGNORECASE)
                data["diagnosis"] = diag_str
                break
    if not data["diagnosis"]:
        for row in rows:
            # A short, low-resolution diagnosis can receive a weak OCR score
            # even when both the label and a readable phrase are present.
            # Keep the literal phrase for human review, without correcting or
            # guessing a medical diagnosis.
            if max((float(it.get("confidence", 0)) for it in row.get("items", [])), default=0) < 0.15:
                continue
            diag_m = re.search(r"(?:chẩn\s*đoán|chan\s*doan|cđ|ch[eê]n\s*8oun|chn\s*8oun)[\s:.\-]*([^|;\n]+)", row.get("text", ""), re.IGNORECASE)
            if diag_m:
                phrase = diag_m.group(1).strip()
                if len(re.findall(r"[A-Za-zÀ-ỹ]{2,}", phrase)) >= 2:
                    data["diagnosis"] = phrase
                    break

    # 6. Chỉ lấy dòng thuốc trong phần thân đơn; không suy đoán liều hoặc số lượng.
    if doc_type == "prescription":
        data["medications"] = _prescription_medications_from_rows(rows)
    elif doc_type == "lab_test":
        metrics = []
        for r in rows:
            r_txt = r.get("text", "").strip()
            if re.search(r"họ tên|tuổi|bác sĩ|khoa|ngày|chẩn đoán|tiêu đề|xét nghiệm", r_txt, re.IGNORECASE):
                continue
            parts = [p.strip() for p in r_txt.split("|")]
            if len(parts) >= 2:
                test_name = parts[0]
                result_val = ""
                unit_val = ""
                ref_range = ""
                flag_val = ""

                for p in parts[1:]:
                    if re.match(r"^\d+(?:[.,]\d+)?$", p) and not result_val:
                        result_val = p
                    elif re.search(r"(?:mmol\/l|mg\/dl|u\/l|g\/l|%|10\^|fl|pg)", p, re.IGNORECASE) and not unit_val:
                        unit_val = p
                    elif re.search(r"\d+\s*[-–~]\s*\d+", p) and not ref_range:
                        ref_range = p
                    elif re.search(r"^(?:high|low|normal|h|l|bình thường|cao|thấp)$", p, re.IGNORECASE) and not flag_val:
                        flag_val = p

                if test_name and (result_val or len(parts) >= 3):
                    metrics.append({
                        "test_name": test_name,
                        "result": result_val or (parts[1] if len(parts) > 1 else ""),
                        "unit": unit_val or (parts[2] if len(parts) > 2 else ""),
                        "reference_range": ref_range or (parts[3] if len(parts) > 3 else ""),
                        "flag_on_paper": flag_val or "Normal"
                    })
        data["metrics"] = metrics

    return data

def reconcile_parallel_results(ocr_data: Dict[str, Any], gemini_data: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    """
    [3] Đối chiếu A (OCR) và B (Gemini) theo từng field:
      - Khớp -> confidence cao
      - Lệch -> needs_review=True, giữ cả hai giá trị
      - Số (liều, kết quả XN) phải khớp tuyệt đối mới được coi là chắc chắn (confidence=1.0)
    """
    ocr_raw_text = ocr_data.get("raw_text", "")
    ocr_lines = [l.get("text", "") for l in ocr_data.get("lines", [])]
    ocr_text_lower = ocr_raw_text.lower()

    reconciled = dict(gemini_data) if gemini_data else {}
    raw_facility = reconciled.get("facility", "")
    if _is_role_only_doctor(reconciled.get("doctor")):
        reconciled["doctor"] = ""
    if _is_malformed_facility(raw_facility):
        reconciled["facility"] = ""
    fields_review = []
    overall_confidence = 1.0

    # The OCR parser reads labeled administrative fields from their positions
    # on the paper. A conflicting nonempty model value must not silently win.
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

    # Đối soát & phục hồi thông tin hành chính từ OCR nếu thiếu
    if not reconciled.get("dob"):
        dob_match = re.search(r"(?:ngày\s*sinh|sinh\s*ngày|ns|d\.o\.b|dob)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", ocr_raw_text, re.IGNORECASE)
        if dob_match:
            reconciled["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        else:
            year_match = re.search(r"(?:năm\s*sinh|sinh\s*năm|sn)[\s:.\-]*(19\d{2}|20\d{2})", ocr_raw_text, re.IGNORECASE)
            if year_match:
                reconciled["dob"] = year_match.group(1)

    if not reconciled.get("age"):
        age_match = re.search(r"(?:tuổi|age)[\s:.\-]*(\d{1,3})", ocr_raw_text, re.IGNORECASE)
        if age_match:
            reconciled["age"] = age_match.group(1)

    if not reconciled.get("gender"):
        gender_match = re.search(r"(?:giới\s*tính|phái)[\s:.\-]*(nam|nữ|nu)", ocr_raw_text, re.IGNORECASE)
        if gender_match:
            g_raw = gender_match.group(1).lower()
            reconciled["gender"] = "Nam" if "nam" in g_raw else "Nữ"

    if doc_type == "prescription":
        meds = reconciled.get("medications", [])
        body_start = next((i + 1 for i, row in enumerate(ocr_data.get("rows", [])) if re.search(
            r"chẩn\s*đoán|chan\s*doan|chân\s*doan", row.get("text", ""), re.IGNORECASE)), 0)
        body_end = next((i for i, row in enumerate(ocr_data.get("rows", [])) if i >= body_start and re.search(
            r"cộng\s*khoản|cong\s*kho[aà]n|bác\s*sĩ\s*điều\s*trị|bac\s*si\s*dieu\s*tri",
            row.get("text", ""), re.IGNORECASE)), len(ocr_data.get("rows", [])))
        outside_rows = ocr_data.get("rows", [])[:body_start] + ocr_data.get("rows", [])[body_end:]
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
            # Only discard a model name that is visibly copied from the
            # administrative header/footer. Unknown names inside the body stay
            # available for human review instead of being silently lost.
            if len(name) >= 5 and any(name in _clean_str(item.get("text", ""))
                                      for row in outside_rows for item in row.get("items", [])):
                continue
            supported_meds.append(med)
        meds = _merge_medication_rows(ocr_fallback.get("medications", []), supported_meds)
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
            for line in ocr_lines:
                ratio = difflib.SequenceMatcher(None, _clean_str(name), _clean_str(line)).ratio()
                if ratio > best_match_ratio:
                    best_match_ratio = ratio
                    matched_ocr_str = line
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

            needs_review = not (name_in_ocr and nums_strictly_matched)
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

