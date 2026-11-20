import re
import difflib
import unicodedata
from typing import Dict, Any, List, Tuple


def _fold_ascii(text: str) -> str:
    if not text:
        return ""
    s = str(text).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"\bu6ng\b|\bi-jong\b", "uong", s)
    s = re.sub(r"\bt6i\b", "toi", s)
    s = re.sub(r"\btru&c\b", "truoc", s)
    s = re.sub(r"\bian\b", "lan", s)
    return re.sub(r"\s+", " ", s).strip()


# Danh mục thuốc cơ bản Việt Nam / Hoạt chất thông dụng
VN_DRUG_DATABASE = [
    {"name": "Paracetamol", "aliases": ["hapacol", "panadol", "efferalgan", "acetaminophen", "tylenol"], "active_ingredient": "Paracetamol", "category": "Hạ sốt, giảm đau", "purpose": "Hạ sốt, giảm đau nhức"},
    {"name": "Ibuprofen", "aliases": ["gofen", "advil", "alaxan"], "active_ingredient": "Ibuprofen", "category": "Kháng viêm NSAID", "purpose": "Kháng viêm, giảm đau cơ khớp"},
    {"name": "Celecoxib", "aliases": ["celebrex"], "active_ingredient": "Celecoxib", "category": "Kháng viêm NSAID chọn lọc COX-2", "purpose": "Giảm đau, kháng viêm cơ xương khớp"},
    {"name": "Meloxicam", "aliases": ["mobic"], "active_ingredient": "Meloxicam", "category": "Kháng viêm NSAID", "purpose": "Kháng viêm, giảm đau xương khớp"},
    {"name": "Amoxicillin", "aliases": ["augmentin", "clamentin", "amox", "klamentin"], "active_ingredient": "Amoxicillin", "category": "Kháng sinh Penicillin", "purpose": "Kháng sinh trị nhiễm trùng"},
    {"name": "Cefixime", "aliases": ["cefixim", "fixime"], "active_ingredient": "Cefixime", "category": "Kháng sinh Cephalosporin thế hệ 3", "purpose": "Kháng sinh trị nhiễm khuẩn hô hấp/tiết niệu"},
    {"name": "Cefuroxime", "aliases": ["zinnat", "cefuroxim"], "active_ingredient": "Cefuroxime", "category": "Kháng sinh Cephalosporin thế hệ 2", "purpose": "Kháng sinh trị nhiễm khuẩn hô hấp"},
    {"name": "Azithromycin", "aliases": ["zithromax", "azimax"], "active_ingredient": "Azithromycin", "category": "Kháng sinh Macrolide", "purpose": "Kháng sinh trị nhiễm trùng đường thở"},
    {"name": "Omeprazole", "aliases": ["losec", "omeprazol"], "active_ingredient": "Omeprazole", "category": "Ức chế bơm Proton", "purpose": "Giảm tiết axit dạ dày / Chống loét"},
    {"name": "Esomeprazole", "aliases": ["nexium", "esomeprazol", "yesom"], "active_ingredient": "Esomeprazole", "category": "Ức chế bơm Proton", "purpose": "Giảm tiết axit dạ dày / Trào ngược dạ dày"},
    {"name": "Pantoprazole", "aliases": ["pantoloc", "pantoprazol"], "active_ingredient": "Pantoprazole", "category": "Ức chế bơm Proton", "purpose": "Giảm tiết axit dạ dày / Trào ngược"},
    {"name": "Rabeprazole", "aliases": ["pariet", "rabeprazol"], "active_ingredient": "Rabeprazole", "category": "Ức chế bơm Proton", "purpose": "Giảm tiết axit dạ dày"},
    {"name": "Domperidone", "aliases": ["motilium", "domperidon"], "active_ingredient": "Domperidone", "category": "Chống nôn & Trợ vận động tiêu hóa", "purpose": "Giảm đầy bụng, buồn nôn, khó tiêu"},
    {"name": "Diosmectite", "aliases": ["smecta"], "active_ingredient": "Diosmectite", "category": "Bảo vệ niêm mạc tiêu hóa", "purpose": "Cầm tiêu chảy, bảo vệ niêm mạc ruột"},
    {"name": "Oresol", "aliases": ["oresol", "ors", "hydrite"], "active_ingredient": "Điện giải Oresol", "category": "Bù nước & Điện giải", "purpose": "Bù nước và điện giải"},
    {"name": "Cetirizine", "aliases": ["zyrtec", "cetirizin"], "active_ingredient": "Cetirizine HCl", "category": "Kháng dị ứng Histamin H1", "purpose": "Giảm ngứa, sổ mũi, viêm mũi dị ứng"},
    {"name": "Loratadine", "aliases": ["claritin", "loratadin"], "active_ingredient": "Loratadine", "category": "Kháng dị ứng Histamin H1", "purpose": "Chống dị ứng, mề đay, viêm mũi"},
    {"name": "Fexofenadine", "aliases": ["telfast", "fexofenadin"], "active_ingredient": "Fexofenadine HCl", "category": "Kháng dị ứng Histamin H1", "purpose": "Giảm hắt hơi, sổ mũi, dị ứng"},
    {"name": "Acetylcysteine", "aliases": ["acemuc", "mitux", "acetylcystein"], "active_ingredient": "N-Acetylcysteine", "category": "Tiêu nhầy đường hô hấp", "purpose": "Làm loãng đờm, giảm ho có đờm"},
    {"name": "Ambroxol", "aliases": ["mucosolvan"], "active_ingredient": "Ambroxol HCl", "category": "Long đờm hô hấp", "purpose": "Làm loãng dịch nhầy đường thở"},
    {"name": "Methylprednisolone", "aliases": ["medrol", "methylprednisolon"], "active_ingredient": "Methylprednisolone", "category": "Corticosteroid kháng viêm", "purpose": "Kháng viêm mạnh, chống dị ứng theo chỉ định"},
    {"name": "Losartan", "aliases": ["cozaar"], "active_ingredient": "Losartan Potassium", "category": "Hạ huyết áp (ARB)", "purpose": "Kiểm soát huyết áp, bảo vệ tim thận"},
    {"name": "Clopidogrel", "aliases": ["plavix"], "active_ingredient": "Clopidogrel", "category": "Chống kết tập tiểu cầu", "purpose": "Dự phòng huyết khối tim mạch"},
    {"name": "Vitamin C", "aliases": ["ascorbic acid", "ceelin", "upsa c"], "active_ingredient": "Acid Ascorbic", "category": "Vitamin & Đề kháng", "purpose": "Tăng cường sức đề kháng"},
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
    {"name": "Natri Clorid 0.9%", "aliases": ["nacl", "nuoc muoi sinh ly", "natri clorid"], "active_ingredient": "NaCl 0.9%", "category": "Dung dịch đẳng trương", "purpose": "Vệ sinh sát khuẩn đường thở"},
    {"name": "Scotolac (Shunorac)", "aliases": ["scotolac", "shunorac", "scotols", "scotolns", "etodolac"], "active_ingredient": "Etodolac 200mg", "category": "Kháng viêm NSAID", "purpose": "Kháng viêm, giảm đau cơ khớp & đau thần kinh tọa"},
    {"name": "Độc hoạt TKS viên (Lọ/100v)", "aliases": ["độc hoạt tks", "doc hoat tks", "độc hoạt", "doc hoat", "dxk hoat", "dk hoat"], "active_ingredient": "Độc hoạt tang ký sinh", "category": "Y học cổ truyền / Xương khớp", "purpose": "Bổ can thận, trừ phong thấp, giảm đau nhức lưng và chi"},
    {"name": "Đại tần giao (H/100v)", "aliases": ["đại tần giao", "dai tan giao", "đại tần", "dai lin gio", "dai lin"], "active_ingredient": "Đại tần giao thang", "category": "Y học cổ truyền / Xương khớp", "purpose": "Khu phong thanh nhiệt, thông kinh hoạt lạc, dưỡng huyết nhuận táo"},
    {"name": "Rheumatin (Ch/40v)", "aliases": ["rheumatin", "rhcumatin"], "active_ingredient": "Cao xương khớp thảo dược", "category": "Y học cổ truyền / Xương khớp", "purpose": "Bổ khí huyết, mạnh gân cốt, giảm đau thần kinh tọa"},
    {"name": "Ginkobil (H/100v)", "aliases": ["ginkobil", "ginkgo", "ginkgo biloba", "bạch quả"], "active_ingredient": "Ginkgo Biloba", "category": "Tuần hoàn não & thần kinh", "purpose": "Tăng cường lưu thông máu, hỗ trợ dẫn truyền thần kinh ngoại biên"},
    {"name": "JEX (H/30v)", "aliases": ["jex", "jex max", "jex thế hệ mới"], "active_ingredient": "Peptan & Collagen Type II", "category": "Bảo vệ sụn khớp", "purpose": "Tái tạo sụn khớp, giảm đau thoái hóa cột sống & đĩa đệm"},
    {"name": "Cồn xoa bóp Viện", "aliases": ["cồn xoa bóp", "con xoa bop", "can xon bop", "xoa bóp"], "active_ingredient": "Cồn thảo dược xoa bóp", "category": "Dùng ngoài da", "purpose": "Xoa bóp giảm đau cơ khớp, lưu thông kinh lạc tại chỗ"}
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
    comb = _fold_ascii(f"{frequency_str} {usage_str}")
    schedule = {
        "morning": {"time": "07:00", "active": False, "note": ""},
        "noon": {"time": "12:00", "active": False, "note": ""},
        "evening": {"time": "18:30", "active": False, "note": ""},
        "bedtime": {"time": "21:30", "active": False, "note": ""},
        "external": {"time": "Khi cần", "active": False, "note": ""},
    }

    # Bóc tách trước ăn / sau ăn / cách dùng đặc biệt
    is_topical = any(k in comb for k in ("boi", "thoa", "xoa", "dung ngoai", "ngoai da", "apply", "topical"))
    timing_note = "Sau khi ăn 30 phút"
    if "truoc an" in comb or "before meal" in comb:
        timing_note = "Trước khi ăn 30 phút"
    elif "ngam" in comb or "sublingual" in comb:
        timing_note = "Ngậm dưới lưỡi"
    elif "suc hong" in comb or "gargle" in comb:
        timing_note = "Súc họng"
    elif is_topical:
        timing_note = "Dùng ngoài da"

    # Ưu tiên các buổi được ghi tường minh (Sáng / Trưa / Chiều-Tối / Trước ngủ)
    has_morning = bool(re.search(r"\b(sang|morning|breakfast)\b", comb))
    has_noon = bool(re.search(r"\b(trua|noon|lunch)\b", comb))
    has_evening = bool(re.search(r"\b(chieu|toi|evening|dinner)\b", comb))
    has_bedtime = bool(re.search(r"\b(truoc\s*(?:khi\s*)?ngu|bedtime)\b", comb))

    if has_morning or has_noon or has_evening or has_bedtime:
        if has_morning:
            schedule["morning"]["active"] = True
            schedule["morning"]["note"] = timing_note
        if has_noon:
            schedule["noon"]["active"] = True
            schedule["noon"]["note"] = timing_note
        if has_evening:
            schedule["evening"]["active"] = True
            schedule["evening"]["note"] = timing_note
        if has_bedtime:
            schedule["bedtime"]["active"] = True
            schedule["bedtime"]["note"] = timing_note
        return schedule

    # Rule phân bổ theo tổng số lần / ngày (xét từ 4 -> 1)
    if any(k in comb for k in ("4 lan", "4 times", "four times", "qid", "cach 6h")):
        for slot in ("morning", "noon", "evening", "bedtime"):
            schedule[slot]["active"] = True
            schedule[slot]["note"] = timing_note
    elif any(k in comb for k in ("3 lan", "3 times", "three times", "tid", "cach 8h")):
        for slot in ("morning", "noon", "evening"):
            schedule[slot]["active"] = True
            schedule[slot]["note"] = timing_note
    elif any(k in comb for k in ("2 lan", "2 times", "twice", "bid", "cach 12h")):
        for slot in ("morning", "evening"):
            schedule[slot]["active"] = True
            schedule[slot]["note"] = timing_note
    elif is_topical:
        schedule["external"]["active"] = True
        schedule["external"]["note"] = usage_str.strip() or "Dùng ngoài da khi cần"
    else:
        schedule["morning"]["active"] = True
        schedule["morning"]["note"] = timing_note

    return schedule

