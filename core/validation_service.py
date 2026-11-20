import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# Các cặp tương tác thuốc bất lợi phổ biến
DRUG_INTERACTIONS = [
    {
        "pair": {"Paracetamol", "Ibuprofen"},
        "level": "Cảnh báo nhẹ / Thận trọng",
        "description": "Dùng chung Paracetamol và NSAID (Ibuprofen) cần chú ý liều lượng để tránh tăng gánh nặng lên gan và dạ dày."
    },
    {
        "pair": {"Ibuprofen", "Aspirin"},
        "level": "Nguy cơ cao",
        "description": "Hai thuốc NSAID dùng đồng thời làm tăng nguy cơ loét và xuất huyết tiêu hóa."
    },
    {
        "pair": {"Amoxicillin", "Metformin"},
        "level": "Theo dõi",
        "description": "Kháng sinh có thể ảnh hưởng hệ vi sinh đường ruột và hấp thu chuyển hóa."
    }
]

def calculate_lab_flag(value_str: str, ref_range_str: str) -> str:
    """
    [5.B] TỰ TÍNH LẠI CỜ CAO/THẤP TỪ GIÁ TRỊ VÀ KHOẢNG THAM CHIẾU:
    Ví dụ ref: "3.9 - 6.4" hoặc "< 5.2" hoặc "> 50".
    Tuyệt đối KHÔNG mặc định trả về 'Normal' khi thiếu khoảng tham chiếu hoặc giá trị phi số.
    """
    val_clean = str(value_str or "").replace(",", ".").strip()
    if not val_clean or not str(ref_range_str or "").strip():
        return "UNKNOWN"

    low_text = val_clean.lower()
    if any(tok in low_text for tok in (
        "âm tính", "am tinh", "dương tính", "duong tinh",
        "negative", "positive", "reactive", "non-reactive", "trace", "vết", "nhóm máu", "nhom mau"
    )):
        return "UNKNOWN"

    m_val = re.match(r"^[<>≤≥]?\s*(-?\d+(?:\.\d+)?)\b", val_clean)
    if not m_val:
        return "UNKNOWN"
    try:
        val = float(m_val.group(1))
    except Exception:
        return "UNKNOWN"

    ref = str(ref_range_str).replace(",", ".").strip()

    # Trường hợp 1: Dạng khoảng "min - max" (ví dụ 3.9 - 6.4)
    range_match = re.findall(r"(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)", ref)
    if range_match:
        low = float(range_match[0][0])
        high = float(range_match[0][1])
        if val < low:
            return "Low"
        elif val > high:
            return "High"
        else:
            return "Normal"

    # Trường hợp 2: Dạng nhỏ hơn "< 5.2" hoặc "<= 5.2"
    lt_match = re.findall(r"[<≤]\s*(\d+(?:\.\d+)?)", ref)
    if lt_match:
        high = float(lt_match[0])
        if val > high:
            return "High"
        return "Normal"

    # Trường hợp 3: Dạng lớn hơn "> 50" hoặc ">= 50"
    gt_match = re.findall(r"[>≥]\s*(\d+(?:\.\d+)?)", ref)
    if gt_match:
        low = float(gt_match[0])
        if val < low:
            return "Low"
        return "Normal"

    return "UNKNOWN"

def validate_prescription_rules(medications: List[Dict[str, Any]], user_allergies: List[str] = None) -> Dict[str, Any]:
    """
    [5.C] Kiểm tra tương tác thuốc, dị ứng và trùng lặp hoạt chất.
    """
    alerts = []
    active_ingredients = []
    med_names = [m.get("standard_name") or m.get("name") for m in medications]

    # 1. Trùng hoạt chất
    for med in medications:
        act = med.get("active_ingredient", "")
        if act and act != "Chưa xác định":
            if act in active_ingredients:
                alerts.append(f"CẢNH BÁO TRÙNG HOẠT CHẤT: Phát hiện nhiều loại thuốc chứa cùng hoạt chất '{act}'. Nguy cơ quá liều!")
            else:
                active_ingredients.append(act)

    # 2. Dị ứng thuốc nếu bệnh nhân có tiền sử
    if user_allergies:
        for allergy in user_allergies:
            a_lower = allergy.lower().strip()
            for m in medications:
                m_comb = f"{m.get('name', '')} {m.get('active_ingredient', '')}".lower()
                if a_lower in m_comb:
                    alerts.append(f"CẢNH BÁO NGUY HIỂM: Bệnh nhân có tiền sử dị ứng với '{allergy}', trùng với thuốc '{m.get('name')}'!")

    # 3. Tra bảng tương tác thuốc
    for inter in DRUG_INTERACTIONS:
        pair = inter["pair"]
        found = [p for p in pair if any(p.lower() in m.lower() for m in med_names)]
        if len(found) >= 2:
            alerts.append(f"TƯƠNG TÁC THUỐC ({inter['level']}): {' + '.join(found)} - {inter['description']}")

    return {
        "has_alerts": len(alerts) > 0,
        "alerts": alerts
    }

def validate_lab_rules(metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    [5.B] So sánh cờ tự tính toán với cờ in trên phiếu để cảnh báo lệch và phát hiện thiếu dữ liệu.
    Phân biệt rõ: giá trị trích xuất, flag trên tài liệu, flag tính toán và trạng thái xác minh.
    """
    validated = []
    for item in metrics:
        m = dict(item)
        raw_result = str(m.get("result") or "").strip()
        raw_unit = str(m.get("unit") or "").strip()
        raw_ref = str(m.get("reference_range") or "").strip()
        raw_paper_flag = str(m.get("flag_on_paper") or "").strip()
        if not raw_paper_flag:
            raw_paper_flag = "UNKNOWN"
            m["flag_on_paper"] = "UNKNOWN"

        computed_flag = calculate_lab_flag(raw_result, raw_ref)
        paper_flag = raw_paper_flag.lower()
        paper_is_normal = paper_flag in ("normal", "binh thuong", "bình thường", "bt", "n")
        paper_is_high = paper_flag in ("high", "h", "cao") or "high" in paper_flag or "cao" in paper_flag
        paper_is_low = paper_flag in ("low", "l", "thap", "thấp") or "low" in paper_flag or "thap" in paper_flag or "thấp" in paper_flag
        paper_is_unknown = paper_flag in ("", "unknown", "?")

        is_flag_mismatch = False
        if computed_flag == "High" and (paper_is_normal or paper_is_low):
            is_flag_mismatch = True
        elif computed_flag == "Low" and (paper_is_normal or paper_is_high):
            is_flag_mismatch = True
        elif computed_flag == "Normal" and (paper_is_high or paper_is_low):
            is_flag_mismatch = True

        incomplete_fields = []
        if not raw_result:
            incomplete_fields.append("giá trị kết quả")
        if not raw_unit:
            incomplete_fields.append("đơn vị đo")
        if not raw_ref:
            incomplete_fields.append("khoảng tham chiếu")
        if computed_flag == "UNKNOWN":
            incomplete_fields.append("ngưỡng phân loại")

        m["computed_flag"] = computed_flag
        m["flag_mismatch"] = is_flag_mismatch
        if is_flag_mismatch:
            m["needs_review"] = True
            m["verification_status"] = "mismatch"
            m["validation_warning"] = f"Cờ tự tính ({computed_flag}) lệch với cờ ghi trên phiếu ({raw_paper_flag}). Cần kiểm tra kỹ."
        elif incomplete_fields or paper_is_unknown:
            m["needs_review"] = True
            m["verification_status"] = "unverified"
            reasons = ", ".join(incomplete_fields) if incomplete_fields else "thiếu cờ đối chiếu trên phiếu"
            m["validation_warning"] = f"Chưa đủ căn cứ phân loại ({reasons}). Vui lòng đối chiếu trực tiếp với phiếu gốc."
        else:
            m["verification_status"] = "verified"

        validated.append(m)
    return validated

