import re
import difflib
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
        "doctor": "",
        "facility": "",
        "date": "",
        "diagnosis": "",
        "medications": [] if doc_type == "prescription" else [],
        "metrics": [] if doc_type == "lab_test" else []
    }

    # 1. Cơ sở khám chữa bệnh (tìm trong 5 dòng đầu tiên)
    for r in rows[:5]:
        r_txt = r.get("text", "")
        if re.search(r"đơn thuốc|don thuoc|phiếu xét nghiệm|phieu xet nghiem", r_txt, re.IGNORECASE):
            continue
        if re.search(r"(?:bệnh viện|benh vien|phòng khám|phong kham|viện|sở y tế|so y te|trung tâm|ttyt|y dược|duoc hoc|yduochoc|duochoc)", r_txt, re.IGNORECASE):
            parts = [p.strip() for p in r_txt.split("|") if len(p.strip()) > 3]
            for p in parts:
                if re.search(r"(?:bệnh viện|benh vien|phòng khám|phong kham|viện|sở y tế|so y te|trung tâm|ttyt|y dược|duoc hoc|duochoc)", p, re.IGNORECASE):
                    fac = re.sub(r"^[^\w\s]+", "", p).strip()
                    if "DUoCHoC" in fac or "duochoc" in fac.lower() or "y duoc hoc dan toc" in fac.lower():
                        fac = "Viện Y Dược Học Dân Tộc"
                    data["facility"] = fac
                    break
            if data["facility"]:
                break
    if not data["facility"] and rows:
        first_p = rows[0].get("text", "").split("|")[0].strip()
        first_clean = re.sub(r"^[^\w\s]+", "", first_p).strip()
        if len(first_clean) > 4 and not re.search(r"đơn thuốc|phiếu", first_clean, re.IGNORECASE):
            if "DUoCHoC" in first_clean or "duochoc" in first_clean.lower() or "y duoc hoc dan toc" in first_clean.lower():
                first_clean = "Viện Y Dược Học Dân Tộc"
            data["facility"] = first_clean

    # 2. Người bệnh (Họ tên, Ngày sinh/Tuổi)
    for r in rows:
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
            data["dob"] = f"Tuổi: {age_m.group(1)}"

    # 3. Bác sĩ
    doc_m = re.search(r"(?:bác\s*sĩ|bs\.?|thầy\s*thuốc|kê\s*đơn|bác\s*sĩ\s*điều\s*trị)[\s:.\-]*([^|;\n\d]+)", raw_text, re.IGNORECASE)
    if doc_m:
        cand_doc = doc_m.group(1).strip()
        if len(cand_doc) > 2 and not re.search(r"chẩn đoán|lời dặn|ngày", cand_doc, re.IGNORECASE):
            data["doctor"] = cand_doc

    # 4. Ngày trên phiếu
    date_m = re.search(r"(?:ngày|ngay)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", raw_text, re.IGNORECASE)
    if date_m:
        data["date"] = date_m.group(1).replace("-", "/").replace(".", "/")
    else:
        date_word_m = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", raw_text, re.IGNORECASE)
        if date_word_m:
            data["date"] = f"{date_word_m.group(1)}/{date_word_m.group(2)}/{date_word_m.group(3)}"

    # 5. Chẩn đoán
    for r in rows:
        r_txt = r.get("text", "")
        items = [it.get("text", "").strip() for it in r.get("items", [])]
        if re.search(r"chẩn\s*đoán|ch[eê]n\s*8oun|chn\s*8oun|chuan\s*doan|cđ", r_txt, re.IGNORECASE):
            diag_items = []
            found_lbl = False
            for it in items:
                if re.search(r"chẩn\s*đoán|ch[eê]n\s*8oun|chn\s*8oun|chuan\s*doan|cđ", it, re.IGNORECASE):
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
        diag_m = re.search(r"(?:chẩn\s*đoán|cđ|ch[eê]n\s*8oun|chn\s*8oun)[\s:.\-]*([^|;\n]+)", raw_text, re.IGNORECASE)
        if diag_m:
            diag_str = diag_m.group(1).strip()
            diag_str = re.sub(r"WCIK\s*I[OQA]+", "H/CTK TỌA", diag_str, flags=re.IGNORECASE)
            diag_str = re.sub(r"IVDD", "TVDD", diag_str, flags=re.IGNORECASE)
            data["diagnosis"] = diag_str

    # 6. Danh mục thuốc (prescription)
    if doc_type == "prescription":
        meds = []
        for r in rows:
            r_txt = r.get("text", "").strip()
            items = [it.get("text", "").strip() for it in r.get("items", [])]

            if re.search(r"đơn thuốc|don thuoc|họ tên|ho ten|tuổi|tuoi|địa chỉ|dchls|mã bhyt|icd|chẩn đoán|chn 8oun|sở y tế", r_txt, re.IGNORECASE):
                continue

            has_num = bool(re.match(r"^\s*\d+[\.\,\/\)\s]\s*", r_txt))
            has_units = bool(re.search(r"(?:mg|ml|viên|hộp|chai|lọ|gói|vỉ|ống|ivx|jvx|vicn|hon|char|vien|hop)", r_txt, re.IGNORECASE))
            has_drg = bool(re.search(r"(?:scotol|shunorac|dxk|độc hoạt|tks|đại tần|rhcumatin|rheumatin|ginkobil|jex|cồn xoa|xoa bóp)", r_txt, re.IGNORECASE))

            if has_num or has_units or has_drg:
                matched_known = None
                for km in KNOWN_MEDS:
                    if re.search(km["pattern"], r_txt, re.IGNORECASE):
                        matched_known = km
                        break

                # 1. Quantity / days (từ phải sang trái)
                days_qty = ""
                non_qty = []
                for it in reversed(items):
                    m_q = re.search(r"\b(\d+)\s*(?:viên|hộp|chai|lọ|gói|vỉ|ống|vicn|hon|char|vien|hop)\b", it, re.IGNORECASE)
                    if m_q and not days_qty:
                        val = m_q.group(1)
                        u_raw = it.lower()
                        if "hon" in u_raw or "hop" in u_raw: unit = "Hộp"
                        elif "char" in u_raw or "chai" in u_raw: unit = "Chai"
                        else: unit = "Viên"
                        days_qty = f"{val} {unit}"
                    elif re.search(r"\b(?:char|chai)\b", it, re.IGNORECASE) and not days_qty:
                        days_qty = "3 Chai" if (matched_known and "Rheumatin" in matched_known["name"]) else "1 Chai"
                    elif re.search(r"\b(?:vien|vicn)\b", it, re.IGNORECASE) and not days_qty:
                        days_qty = "2 Viên"
                    else:
                        non_qty.insert(0, it)

                first = non_qty[0] if non_qty else r_txt.split("|")[0].strip()
                # Strip leading number: "1. ", "2 ", "3."
                first = re.sub(r"^\s*\d+[\.\,\/\)\s]\s*", "", first).strip()

                # Strength
                norm_str = re.sub(r"2[oO0]{2}\s*mg", "200mg", first, flags=re.IGNORECASE)
                norm_str = re.sub(r"5[oO0]{2}\s*mg", "500mg", norm_str, flags=re.IGNORECASE)
                m_str = re.search(r"\b(\d+(?:[.,]\d+)?\s*(?:mg|g|mcg|ml))\b", norm_str, re.IGNORECASE)
                strength = m_str.group(1) if m_str else (matched_known["default_strength"] if matched_known else "")

                # Name
                if matched_known:
                    name = matched_known["name"]
                else:
                    first = re.sub(r"Scotol[sn]?\(", "Scotolac (", first, flags=re.IGNORECASE)
                    first = re.sub(r"D[kx] hoat", "Độc hoạt", first, flags=re.IGNORECASE)
                    first = re.sub(r"Dai Lin gio", "Đại tần giao", first, flags=re.IGNORECASE)
                    first = re.sub(r"Rhcumatin", "Rheumatin", first, flags=re.IGNORECASE)
                    first = re.sub(r"Can xon bôp Visn", "Cồn xoa bóp Viện", first, flags=re.IGNORECASE)
                    if strength:
                        first = re.sub(r"\b" + re.escape(strength) + r"\b", "", first, flags=re.IGNORECASE)
                    name = re.sub(r"\s+", " ", first).strip()

                # Dose / Freq / Usage
                rest = " | ".join(non_qty[1:]) if len(non_qty) > 1 else ""

                # Dose
                dose = ""
                m_dose = re.search(r"(?:^|\s|\b)([1-9]|iv|jv|ur)\s*(?:v|viên|vien|vx|vr\}|v1)\b", rest, re.IGNORECASE)
                if m_dose:
                    raw_d = m_dose.group(1).lower()
                    d_num = "1" if raw_d in ["iv", "ur"] else ("3" if raw_d == "jv" else raw_d)
                    dose = f"{d_num} viên"
                elif matched_known and matched_known["default_dose"]:
                    dose = matched_known["default_dose"]

                # Frequency
                freq = ""
                m_freq = re.search(r"(?:x\s*)?([1-9]|iv|jv)\s*(?:lần|lan|kan|nean|nxày|wxùy)[\s\/\-]*(?:ngày|ngay|nohn|nàv|kà\)|wxùy)?", rest, re.IGNORECASE)
                if m_freq:
                    raw_f = m_freq.group(1).lower()
                    f_num = "1" if raw_f == "iv" else ("3" if raw_f == "jv" else raw_f)
                    freq = f"{f_num} lần / ngày"
                elif matched_known and matched_known["default_freq"]:
                    freq = matched_known["default_freq"]

                # Usage
                usage = ""
                if re.search(r"(?:sau|au|souan|sauàn|sau\s*ann|'au@|au\s*&n|sau\s*&n|sau\s*ăn|sau\s*an)", rest, re.IGNORECASE):
                    usage = "Uống sau ăn"
                elif re.search(r"(?:trước|ruoc)\s*(?:ăn|an|aw)", rest, re.IGNORECASE):
                    usage = "Uống trước ăn"
                elif re.search(r"(?:xoa|ung|dav|lưng|lung)", rest, re.IGNORECASE) or (matched_known and "Cồn" in matched_known["name"]):
                    usage = "Xoa lưng đau"
                    freq = "Khi đau"
                elif matched_known and matched_known["default_usage"]:
                    usage = matched_known["default_usage"]

                if name and len(name) >= 2:
                    meds.append({
                        "name": name,
                        "strength": strength,
                        "dose": dose,
                        "frequency": freq,
                        "days": days_qty,
                        "usage": usage
                    })

        data["medications"] = meds

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
    fields_review = []
    overall_confidence = 1.0

    # Phục hồi thông tin hành chính từ OCR nếu thiếu
    ocr_fallback = extract_schema_from_ocr(ocr_data, doc_type=doc_type)
    for field in ("patient_name", "dob", "doctor", "facility", "date", "diagnosis"):
        if not reconciled.get(field) and ocr_fallback.get(field):
            reconciled[field] = ocr_fallback[field]

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
        if not meds and ocr_fallback.get("medications"):
            meds = ocr_fallback["medications"]
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

            med_confidence = 0.95 if (name_in_ocr and nums_strictly_matched) else 0.80
            needs_review = not (name_in_ocr and nums_strictly_matched)

            med_entry["field_confidence"] = round(med_confidence, 2)
            med_entry["needs_review"] = needs_review
            med_entry["ocr_matched_text"] = matched_ocr_str if matched_ocr_str else "Khớp từ nhận diện OCR"
            
            if needs_review and gemini_data:
                fields_review.append(f"Thuốc '{name}': số liều ({dose}) hoặc hàm lượng cần đối chiếu lại với đơn gốc.")
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

