import re
import difflib
from typing import Dict, Any, List, Tuple

# Danh mục thuốc cơ bản Việt Nam / Hoạt chất thông dụng
VN_DRUG_DATABASE = [
    {"name": "Paracetamol", "aliases": ["hapacol", "panadol", "efferalgan", "acetaminophen"], "active_ingredient": "Paracetamol", "category": "Hạ sốt, giảm đau", "purpose": "Hạ sốt, giảm đau nhức"},
    {"name": "Ibuprofen", "aliases": ["gofen", "advil", "alaxan"], "active_ingredient": "Ibuprofen", "category": "Kháng viêm NSAID", "purpose": "Kháng viêm, giảm đau cơ khớp"},
    {"name": "Amoxicillin", "aliases": ["augmentin", "clamentin", "amox"], "active_ingredient": "Amoxicillin", "category": "Kháng sinh Penicillin", "purpose": "Kháng sinh trị nhiễm trùng"},
    {"name": "Cefixime", "aliases": ["cefixim", "fixime"], "active_ingredient": "Cefixime", "category": "Kháng sinh Cephalosporin thế hệ 3", "purpose": "Kháng sinh trị nhiễm khuẩn hô hấp/tiết niệu"},
    {"name": "Azithromycin", "aliases": ["zithromax", "azimax"], "active_ingredient": "Azithromycin", "category": "Kháng sinh Macrolide", "purpose": "Kháng sinh trị nhiễm trùng đường thở"},
    {"name": "Omeprazole", "aliases": ["losec", "omeprazol"], "active_ingredient": "Omeprazole", "category": "Ức chế bơm Proton", "purpose": "Giảm tiết axit dạ dày / Chống loét"},
    {"name": "Esomeprazole", "aliases": ["nexium", "esomeprazol", "yesom"], "active_ingredient": "Esomeprazole", "category": "Ức chế bơm Proton", "purpose": "Giảm tiết axit dạ dày / Trào ngược dạ dày"},
    {"name": "Sucralfate", "aliases": ["sucrate", "sucrate gel", "sucralfat"], "active_ingredient": "Sucralfate", "category": "Bảo vệ niêm mạc dạ dày", "purpose": "Băng bao vết loét, bảo vệ niêm mạc dạ dày"},
    {"name": "Trimebutine", "aliases": ["arthur", "debridat", "trimebutin"], "active_ingredient": "Trimebutine Maleate", "category": "Điều hòa nhu động đường tiêu hóa", "purpose": "Chống co thắt dạ dày, giảm đầy bụng khó tiêu"},
    {"name": "Magnesi & Nhôm Hydroxide", "aliases": ["biocid", "biocid mh", "papaze", "maalox", "gastropulgite"], "active_ingredient": "Antacid (Nhôm Hydroxide + Magnesi)", "category": "Thuốc kháng Axit (Antacid)", "purpose": "Trung hòa dịch vị dạ dày, giảm đau rát thượng vị"},
    {"name": "L-Arginine", "aliases": ["diglumisan", "arginine"], "active_ingredient": "L-Arginine HCl", "category": "Bảo vệ & Tăng cường chức năng gan", "purpose": "Hỗ trợ thải độc, bảo vệ chức năng gan mật"},
    {"name": "Metformin", "aliases": ["glucophage", "panfor"], "active_ingredient": "Metformin HCl", "category": "Thuốc điều trị Đái tháo đường", "purpose": "Hạ đường huyết"},
    {"name": "Amlodipine", "aliases": ["norvasc", "amlodipin"], "active_ingredient": "Amlodipine", "category": "Hạ huyết áp", "purpose": "Hạ huyết áp / Chẹn kênh Canxi"},
    {"name": "Atorvastatin", "aliases": ["lipitor", "atorvastatin"], "active_ingredient": "Hạ mỡ máu nhóm Statin", "category": "Hạ mỡ máu", "purpose": "Hạ mỡ máu / Bảo vệ tim"},
    {"name": "Thiamine", "aliases": ["vitamin b1", "thiamin"], "active_ingredient": "Thiamine Mononitrate", "category": "Vitamin nhóm B", "purpose": "Bổ thần kinh ngoại biên"},
    {"name": "Desloratadine", "aliases": ["aerius", "desloratadin"], "active_ingredient": "Desloratadine", "category": "Kháng dị ứng Histamin H1", "purpose": "Chống dị ứng, giảm ngứa nghẹt mũi"},
    {"name": "Alpha Chymotrypsin", "aliases": ["chymoral", "alphachymotrypsin", "choay", "alphachoay"], "active_ingredient": "Chymotrypsin", "category": "Kháng viêm dạng men", "purpose": "Giảm phù nề, chống sung huyết"},
    {"name": "Natri Clorid 0.9%", "aliases": ["nacl", "nuoc muoi sinh ly", "natri clorid"], "active_ingredient": "NaCl 0.9%", "category": "Dung dịch đẳng trương", "purpose": "Vệ sinh sát khuẩn đường thở"}
]

# Từ điển chuẩn hóa tên chỉ số xét nghiệm sang LOINC / chuẩn quốc tế
LAB_ALIAS_MAP = {
    "glucose": {"standard_code": "2345-7", "standard_name": "Glucose (Đường huyết đói)", "std_unit": "mmol/L"},
    "đường huyết": {"standard_code": "2345-7", "standard_name": "Glucose (Đường huyết đói)", "std_unit": "mmol/L"},
    "cholesterol": {"standard_code": "2093-3", "standard_name": "Cholesterol toàn phần", "std_unit": "mmol/L"},
    "mỡ máu": {"standard_code": "2093-3", "standard_name": "Cholesterol toàn phần", "std_unit": "mmol/L"},
    "triglyceride": {"standard_code": "2571-8", "standard_name": "Triglycerides", "std_unit": "mmol/L"},
    "ast": {"standard_code": "1920-8", "standard_name": "AST (SGOT - Men gan)", "std_unit": "U/L"},
    "sgot": {"standard_code": "1920-8", "standard_name": "AST (SGOT - Men gan)", "std_unit": "U/L"},
    "alt": {"standard_code": "1742-6", "standard_name": "ALT (SGPT - Men gan)", "std_unit": "U/L"},
    "sgpt": {"standard_code": "1742-6", "standard_name": "ALT (SGPT - Men gan)", "std_unit": "U/L"},
    "creatinine": {"standard_code": "2160-0", "standard_name": "Creatinine (Chức năng thận)", "std_unit": "µmol/L"},
    "ure": {"standard_code": "3094-0", "standard_name": "Urea / BUN", "std_unit": "mmol/L"},
    "urea": {"standard_code": "3094-0", "standard_name": "Urea / BUN", "std_unit": "mmol/L"},
    "acid uric": {"standard_code": "2019-8", "standard_name": "Axit Uric (Gút)", "std_unit": "µmol/L"},
    "wbc": {"standard_code": "6690-2", "standard_name": "WBC (Số lượng Bạch cầu)", "std_unit": "G/L"},
    "bạch cầu": {"standard_code": "6690-2", "standard_name": "WBC (Số lượng Bạch cầu)", "std_unit": "G/L"},
    "rbc": {"standard_code": "789-8", "standard_name": "RBC (Số lượng Hồng cầu)", "std_unit": "T/L"},
    "hồng cầu": {"standard_code": "789-8", "standard_name": "RBC (Số lượng Hồng cầu)", "std_unit": "T/L"},
    "hgb": {"standard_code": "718-7", "standard_name": "Hemoglobin (Huyết sắc tố)", "std_unit": "g/L"},
    "plt": {"standard_code": "777-3", "standard_name": "PLT (Tiểu cầu)", "std_unit": "G/L"},
    "tiểu cầu": {"standard_code": "777-3", "standard_name": "PLT (Tiểu cầu)", "std_unit": "G/L"}
}

def normalize_drug_entity(raw_name: str) -> Dict[str, Any]:
    """Fuzzy matching tên thuốc với danh mục thuốc VN."""
    raw_lower = raw_name.lower().strip()
    best_match = None
    best_score = 0.0

    for drug in VN_DRUG_DATABASE:
        score = difflib.SequenceMatcher(None, raw_lower, drug["name"].lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = drug

        for alias in drug.get("aliases", []):
            ascore = difflib.SequenceMatcher(None, raw_lower, alias.lower()).ratio()
            if alias.lower() in raw_lower:
                ascore = max(ascore, 0.85)
            if ascore > best_score:
                best_score = ascore
                best_match = drug

    if best_match and best_score >= 0.65:
        return {
            "is_matched": True,
            "standard_name": best_match["name"],
            "active_ingredient": best_match["active_ingredient"],
            "category": best_match["category"],
            "purpose": best_match.get("purpose", best_match["category"]),
            "match_confidence": round(best_score, 2),
            "status": "grounded"
        }
    return {
        "is_matched": False,
        "standard_name": raw_name,
        "active_ingredient": "Chưa xác định",
        "category": "Thuốc đặc trị",
        "purpose": "Hỗ trợ điều trị triệu chứng theo đơn",
        "match_confidence": round(best_score, 2),
        "status": "uncertain"
    }

def map_lab_test(raw_name: str) -> Dict[str, Any]:
    """Map alias tên xét nghiệm sang mã chuẩn LOINC và tên thống nhất."""
    raw_lower = raw_name.lower().strip()
    for alias, info in LAB_ALIAS_MAP.items():
        if alias in raw_lower or difflib.SequenceMatcher(None, alias, raw_lower).ratio() > 0.7:
            return {
                "mapped": True,
                "loinc_code": info["standard_code"],
                "standard_name": info["standard_name"],
                "preferred_unit": info["std_unit"]
            }
    return {
        "mapped": False,
        "loinc_code": "UNKNOWN",
        "standard_name": raw_name,
        "preferred_unit": ""
    }

def normalize_lab_unit_and_value(value_str: str, current_unit: str, target_std_unit: str) -> Tuple[float, str]:
    """Chuẩn hóa chuyển đổi đơn vị sinh hóa cơ bản."""
    try:
        val = float(str(value_str).replace(",", ".").strip())
    except Exception:
        return 0.0, current_unit

    c_unit = current_unit.lower().strip()
    t_unit = target_std_unit.lower().strip()

    # Ví dụ: Glucose mg/dL -> mmol/L (chia 18)
    if "mg/dl" in c_unit and "mmol/l" in t_unit:
        return round(val / 18.0, 2), target_std_unit
    if "mmol/l" in c_unit and "mg/dl" in t_unit:
        return round(val * 18.0, 1), target_std_unit

    # g/dL -> g/L (nhân 10)
    if "g/dl" in c_unit and "g/l" in t_unit:
        return round(val * 10.0, 1), target_std_unit

    return val, current_unit

def parse_frequency_to_schedule(frequency_str: str, usage_str: str = "") -> Dict[str, Any]:
    """
    [4.D] Chuyển đổi tần suất sang lịch uống bằng RULE thuần túy (Không dùng LLM).
    Quy ước khung giờ dược động học:
      - Sáng: 07:00
      - Trưa: 12:00
      - Tối: 18:30
      - Trước ngủ: 21:30
    """
    comb = f"{frequency_str} {usage_str}".lower()
    schedule = {
        "morning": {"time": "07:00", "active": False, "note": ""},
        "noon": {"time": "12:00", "active": False, "note": ""},
        "evening": {"time": "18:30", "active": False, "note": ""},
        "bedtime": {"time": "21:30", "active": False, "note": ""}
    }

    # Bóc tách trước ăn / sau ăn
    timing_note = "Sau khi ăn 30 phút"
    if "trước ăn" in comb or "truoc an" in comb:
        timing_note = "Trước khi ăn 30 phút"
    elif "ngậm" in comb:
        timing_note = "Ngậm dưới lưỡi"
    elif "bôi" in comb or "dung ngoai" in comb:
        timing_note = "Dùng ngoài da"

    # Rule phân bổ theo số lần
    if any(k in comb for k in ["1 lần", "1 lan", "buổi sáng", "sang"]):
        if "tối" in comb or "toi" in comb or "trước ngủ" in comb:
            schedule["evening"]["active"] = True
            schedule["evening"]["note"] = timing_note
        else:
            schedule["morning"]["active"] = True
            schedule["morning"]["note"] = timing_note

    elif any(k in comb for k in ["2 lần", "2 lan", "sáng, tối", "sang toi", "cách 12h"]):
        schedule["morning"]["active"] = True
        schedule["morning"]["note"] = timing_note
        schedule["evening"]["active"] = True
        schedule["evening"]["note"] = timing_note

    elif any(k in comb for k in ["3 lần", "3 lan", "sáng, trưa, tối", "sang trua toi", "cách 8h"]):
        schedule["morning"]["active"] = True
        schedule["morning"]["note"] = timing_note
        schedule["noon"]["active"] = True
        schedule["noon"]["note"] = timing_note
        schedule["evening"]["active"] = True
        schedule["evening"]["note"] = timing_note

    elif any(k in comb for k in ["4 lần", "4 lan", "cách 6h"]):
        schedule["morning"]["active"] = True
        schedule["morning"]["note"] = timing_note
        schedule["noon"]["active"] = True
        schedule["noon"]["note"] = timing_note
        schedule["evening"]["active"] = True
        schedule["evening"]["note"] = timing_note
        schedule["bedtime"]["active"] = True
        schedule["bedtime"]["note"] = timing_note
    else:
        # Mặc định an toàn: Sáng
        schedule["morning"]["active"] = True
        schedule["morning"]["note"] = timing_note

    return schedule

