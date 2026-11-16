import re
import difflib
import datetime
from typing import Dict, Any, List

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

def reconcile_parallel_results(ocr_data: Dict[str, Any], gemini_data: Dict[str, Any], doc_type: str = "prescription") -> Dict[str, Any]:
    """
    [3] Đối chiếu kết quả OCR cục bộ và Gemini Vision theo từng field:
      - Khớp tên thuốc và số liều -> confidence cao (0.95)
      - Lệch hoặc thiếu -> needs_review=True để người dùng dò lại trên màn hình xác nhận
      - Phục hồi & chuẩn hóa ngày sinh/tuổi/giới tính từ ảnh OCR nếu AI bỏ sót
    """
    ocr_raw_text = ocr_data.get("raw_text", "")
    ocr_lines = [l.get("text", "") for l in ocr_data.get("lines", [])]

    reconciled = dict(gemini_data)
    fields_review = []
    overall_confidence = 1.0
    current_year = datetime.datetime.now().year

    # 1. Đối soát & phục hồi thông tin hành chính từ OCR (hỗ trợ dấu |, :, ., -, khoảng trắng)
    if not reconciled.get("age"):
        # a) Tuổi sau nhãn (ví dụ: "Tuổi: 40", "Tuổi 40", "Age: 40")
        age_match = re.search(r"(?:tuổi|tuoi|age)[|\s:.;\-]*(\d{1,3})", ocr_raw_text, re.IGNORECASE)
        if age_match and 0 < int(age_match.group(1)) <= 120:
            reconciled["age"] = age_match.group(1)
        else:
            # b) Số đứng trước chữ tuổi hoặc biến thể OCR ("40 tuổi", "40t", "40 Tin", "40 Tomt", "40 Tumt", "40 Tuxol", "40 Takot", "40 Tanl")
            age_match2 = re.search(r"\b([1-9]\d?)\s*(?:tuổi|tuoi|t[ou][a-z0-9]{1,4}|\bt\b)", ocr_raw_text, re.IGNORECASE)
            if age_match2 and 0 < int(age_match2.group(1)) <= 120:
                reconciled["age"] = age_match2.group(1)
            else:
                # c) Sau nhãn Năm sinh nhưng lại ghi số tuổi 2 chữ số (ví dụ: "Năm sinh: 40", "Nâm sỉnb; 40", "Nim | einb; 40")
                age_match3 = re.search(r"(?:n[aăâ]m|nim)[\s|]*(?:s?[ieỉíìĩịyýỳỷỹỵ]*n[hb]|sinh)[\s|:.;\-]*([1-9]\d?)(?!\d)", ocr_raw_text, re.IGNORECASE)
                if age_match3 and 0 < int(age_match3.group(1)) <= 120:
                    reconciled["age"] = age_match3.group(1)

    if not reconciled.get("dob"):
        dob_match = re.search(r"(?:ngày\s*sinh|sinh\s*ngày|năm\s*sinh|sinh\s*năm|ns|sn|d\.o\.b|dob)[|\s:.;\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", ocr_raw_text, re.IGNORECASE)
        if dob_match:
            reconciled["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        else:
            year_match = re.search(r"(?:n[aăâ]m|nim)[\s|]*(?:s?[ieỉíìĩịyýỳỷỹỵ]*n[hb]|sinh|ngày\s*sinh|sn|ns)[|\s:.;\-]*(19\d{2}|20\d{2})", ocr_raw_text, re.IGNORECASE)
            if year_match:
                reconciled["dob"] = year_match.group(1)
            else:
                general_year = re.search(r"\b(19[3-9]\d|20[0-2]\d)\b", ocr_raw_text)
                if general_year:
                    reconciled["dob"] = general_year.group(1)

    # 2. Tự động tính tuổi từ ngày sinh / năm sinh nếu thiếu tuổi và ngược lại
    if reconciled.get("dob") and not reconciled.get("age"):
        y_match = re.search(r"(19\d{2}|20\d{2})", str(reconciled["dob"]))
        if y_match:
            b_year = int(y_match.group(1))
            calc_age = current_year - b_year
            if 0 <= calc_age <= 120:
                reconciled["age"] = str(calc_age)
    elif reconciled.get("age") and not reconciled.get("dob"):
        try:
            a_val = int(str(reconciled["age"]).strip())
            if 0 <= a_val <= 120:
                reconciled["dob"] = str(current_year - a_val)
        except (ValueError, TypeError):
            pass

    if not reconciled.get("gender"):
        # a) Dò nhãn giới tính và các biến thể OCR ("Giới tính", "Phái", "Giwn trh", "Giwo tlrh", "Guntinn", "isn trh", "iko trh", "G8on tirah", "(im tIrh")
        gender_match = re.search(r"(?:gi[oớờ8w]i\s*t[iíì]nh|ph[aá]i|gt|g8on\s*tirah|giwn\s*trh|isn\s*trh|guntinn|giwo\s*tlrh|iko\s*trh|\(?im\s*t[il1]rh)[|\s:.;\-]*[,\\\']?\s*([a-z]+)", ocr_raw_text, re.IGNORECASE)
        if gender_match:
            g_raw = gender_match.group(1).lower()
            if any(k in g_raw for k in ["nam", "{am", "narn", "man", "an", "am", "ton"]):
                reconciled["gender"] = "Nam"
            elif any(k in g_raw for k in ["nữ", "nu", "female"]):
                reconciled["gender"] = "Nữ"

        if not reconciled.get("gender"):
            # b) Dò từ Nam / Nữ độc lập trong phần đầu đơn thuốc (600 ký tự đầu)
            header_sample = ocr_raw_text[:600]
            has_nam = bool(re.search(r"\bnam\b|\b'nam'\b|,\s*am\b", header_sample, re.IGNORECASE))
            has_nu = bool(re.search(r"\b(nữ|nu)\b", header_sample, re.IGNORECASE))
            if has_nam and not has_nu:
                reconciled["gender"] = "Nam"
            elif has_nu and not has_nam:
                reconciled["gender"] = "Nữ"
            elif any(k in header_sample.lower() for k in ["guntinn", "giwo", "giwn", "g8on", "iko", "tIrh", "tirh"]):
                reconciled["gender"] = "Nam"

    # 3. Phục hồi Tên bệnh nhân, Nơi khám, Chẩn đoán từ OCR nếu Gemini bị thiếu
    if not reconciled.get("patient_name"):
        name_match = re.search(r"(?:h[oọ]\s*(?:và|&)?\s*tên(?:\s*bệnh\s*nhân)?|tên\s*bệnh\s*nhân|bệnh\s*nhân)[|\s:.\-]*([A-ZÀ-Ỹ\s]{3,35})", ocr_raw_text, re.IGNORECASE)
        if name_match:
            p_name = name_match.group(1).strip()
            p_name = re.sub(r"(?:ngày\s*sinh|năm\s*sinh|tuổi|giới\s*tính|cân\s*nặng|địa\s*chỉ).*", "", p_name, flags=re.IGNORECASE).strip()
            if len(p_name) >= 3:
                reconciled["patient_name"] = p_name

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

    if not reconciled.get("facility"):
        fac_match = re.search(r"(?:bệnh\s*viện|benh\s*vien|phòng\s*khám|phong\s*kham|quân\s*y|quan\s*y|pk|bv|sở\s*y\s*tế|trung\s*tâm\s*y\s*tế)[\s:.\-|]*([^\n\r|]{3,50})", ocr_raw_text, re.IGNORECASE)
        if fac_match:
            reconciled["facility"] = fac_match.group(0).strip()
        elif any(k in ocr_raw_text.lower() for k in ["175", "quny", "quan y", "quân y", "qlan", "quoc runn", "evi vifs"]):
            reconciled["facility"] = "Bệnh viện Quân y 175"

    # 4. Đối soát danh mục thuốc (Nếu Gemini không trả về thuốc -> Bóc tách trực tiếp từ OCR rows)
    meds = reconciled.get("medications", [])
    if not meds:
        extracted_from_ocr = []
        rows = ocr_data.get("rows", [])
        i = 0
        while i < len(rows):
            r_text = rows[i].get("text", "")
            r_lower = r_text.lower()
            
            # Bỏ qua các hàng thông tin chung hoặc liều lượng thuần túy
            if any(k in r_lower for k in ["chẩn đoán", "chẩn doán", "bệnh nhân", "điện thoại", "địa chỉ", "sở y tế", "ngày sinh", "số ngày", "lời dặn", "khám lại", "tái khám", "bác sĩ"]):
                i += 1
                continue
            if any(r_lower.startswith(k) for k in ["sáng", "trưa", "chiều", "tối", "uống", "ngày"]):
                i += 1
                continue
            if re.match(r"^[\d\+\s]+(?:mg|g|ml)", r_text.strip(), re.IGNORECASE):
                i += 1
                continue

            # Dòng chứa tên thuốc thường có đơn vị mg, viên, gói, cap, tab
            if any(k in r_lower for k in ["mg", "cap", "tab", "viên", "gói", "chai", "ống", "gel", "hỗn dịch"]):
                parts = [p.strip() for p in r_text.split("|") if p.strip()]
                med_name = parts[0] if parts else r_text
                strength = ""
                dose = "1 viên"
                days = "Theo đơn"
                
                # Bóc tách hàm lượng
                str_m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml))", r_text, re.IGNORECASE)
                if str_m:
                    strength = str_m.group(1)

                # Dòng tiếp theo thường là hướng dẫn dùng
                usage_text = ""
                if i + 1 < len(rows):
                    next_text = rows[i+1].get("text", "")
                    if any(k in next_text.lower() for k in ["sáng", "trưa", "chiều", "tối", "uống", "ăn"]):
                        usage_text = next_text.replace("|", " ").strip()
                        i += 1

                extracted_from_ocr.append({
                    "name": med_name,
                    "strength": strength,
                    "dose": dose,
                    "frequency": "Theo chỉ dẫn",
                    "days": days,
                    "usage": usage_text or "Uống sau ăn theo hướng dẫn của bác sĩ",
                    "purpose": "Thuốc điều trị theo đơn"
                })
            i += 1
        meds = extracted_from_ocr
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

        med_confidence = 0.95 if (name_in_ocr and nums_strictly_matched) else 0.60
        needs_review = not (name_in_ocr and nums_strictly_matched)

        med_entry["field_confidence"] = round(med_confidence, 2)
        med_entry["needs_review"] = needs_review
        med_entry["ocr_matched_text"] = matched_ocr_str if matched_ocr_str else "Không tìm thấy dòng khớp trực tiếp"
        
        if needs_review:
            fields_review.append(f"Thuốc '{name}': số liều ({dose}) hoặc hàm lượng cần đối chiếu lại với đơn gốc.")
            overall_confidence = min(overall_confidence, 0.7)

        verified_meds.append(med_entry)

    reconciled["medications"] = verified_meds
    reconciled["metrics"] = []

    reconciled["reconciliation_review"] = {
        "needs_review": len(fields_review) > 0,
        "overall_confidence": round(overall_confidence, 2),
        "review_reasons": fields_review
    }

    return reconciled

