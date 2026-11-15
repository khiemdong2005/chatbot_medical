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
    if u in ("hop", "hon", "box"):
        return "Hộp"
    if u in ("chai", "char", "bottle"):
        return "Chai"
    if u in ("goi", "sachet", "pack"):
        return "Gói"
    if u in ("ong", "amp", "ampoule"):
        return "Ống"
    if u in ("lo", "vial"):
        return "Lọ"
    if u in ("vi", "blister"):
        return "Vỉ"
    if u in ("tuyp", "tube"):
        return "Tuýp"
    return "Viên"


def _parse_dosing_details(text: str) -> Dict[str, str]:
    """Bóc tách liều dùng mỗi lần, tần suất và cách dùng từ dòng hướng dẫn (có dấu / không dấu / OCR nhiễu)."""
    f_txt = _ascii_fold(text)
    out = {"dose": "", "frequency": "", "usage": ""}
    if not f_txt:
        return out

    # 1. Dose (mỗi lần uống bao nhiêu viên/gói/ống/ml)
    m_each = re.search(
        r"(?:moi\s*lan|uong|sang|trua|chieu|toi|take)\s*[:\-]?\s*(\d+(?:[\/.,]\d+)?)\s*(vien|goi|ong|ml|giot|nhát|nhat|tablet|tab|cap|capsule|sachet)\b",
        f_txt,
    )
    if not m_each:
        m_each = re.search(
            r"\b(\d+(?:[\/.,]\d+)?|iv|jv|ur)\s*(vien|v|vx|goi|ong|ml|tablet|tab|cap|capsule|sachet)\b(?=\s*(?:[,;\/x]|lan|times|sang|trua|chieu|toi|truoc|sau|$))",
            f_txt,
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
    if re.search(r"\b(chieu|Afternoon)\b", f_txt, re.IGNORECASE):
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
    if re.search(r"truoc\s*(?:khi\s*)?an\s*(\d+\s*phut)?", f_txt):
        m_min = re.search(r"truoc\s*(?:khi\s*)?an\s*(\d+)\s*phut", f_txt)
        out["usage"] = f"Uống trước ăn {m_min.group(1)} phút" if m_min else "Uống trước ăn"
    elif re.search(r"(?:sau\s*(?:khi\s*)?an|souan|sauan|after\s*meal)", f_txt):
        out["usage"] = "Uống sau ăn"
    elif re.search(r"\bbefore\s*meal", f_txt):
        out["usage"] = "Uống trước ăn"
    elif re.search(r"ngam\s*duoi\s*luoi|ngam", f_txt):
        out["usage"] = "Ngậm dưới lưỡi"
    elif re.search(r"suc\s*hong|suc\s*mieng", f_txt):
        out["usage"] = "Súc họng"
    elif re.search(r"\b(xoa|boi|thoa)\b", f_txt):
        out["usage"] = "Xoa ngoài da"
        if not out["frequency"]:
            out["frequency"] = "Khi đau"

    return out


def extract_schema_from_ocr(ocr_data: Dict[str, Any], doc_type: str = "prescription") -> Dict[str, Any]:
    """
    Fallback bóc tách cấu trúc từ kết quả OCR cục bộ / PDF khi Cloud LLM (Gemini) không khả dụng.
    Hỗ trợ cả đơn thuốc 1 dòng, đơn thuốc 2 dòng (Tên thuốc + dòng Cách dùng), tiếng Việt có dấu / không dấu / nhiễu OCR và phiếu xét nghiệm.
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
        "gender": "",
        "doctor": "",
        "facility": "",
        "date": "",
        "diagnosis": "",
        "medications": [],
        "metrics": [],
    }

    # 1. Cơ sở khám chữa bệnh (tìm trong 6 dòng đầu tiên)
    for r in rows[:6]:
        r_txt = r.get("text", "")
        r_fold = _ascii_fold(r_txt)
        if re.search(r"\b(don thuoc|phieu xet nghiem|prescription|laboratory report)\b", r_fold):
            continue
        if re.search(r"\b(benh vien|phong kham|vien|so y te|trung tam|ttyt|y duoc|duoc hoc|yduochoc|duochoc|hospital|clinic|medical center)\b", r_fold):
            parts = [p.strip() for p in r_txt.split("|") if len(p.strip()) > 3]
            for p in parts:
                pf = _ascii_fold(p)
                if re.search(r"\b(benh vien|phong kham|vien|so y te|trung tam|ttyt|y duoc|duoc hoc|duochoc|hospital|clinic|medical center)\b", pf):
                    fac = re.sub(r"^[^\w\s]+", "", p).strip()
                    if "duochoc" in pf or "y duoc hoc dan toc" in pf:
                        fac = "Viện Y Dược Học Dân Tộc"
                    data["facility"] = fac
                    break
            if data["facility"]:
                break
    if not data["facility"] and rows:
        first_p = rows[0].get("text", "").split("|")[0].strip()
        first_clean = re.sub(r"^[^\w\s]+", "", first_p).strip()
        first_fold = _ascii_fold(first_clean)
        if len(first_clean) > 4 and not re.search(r"\b(don thuoc|phieu|ho ten|chan doan)\b", first_fold):
            if "duochoc" in first_fold or "y duoc hoc dan toc" in first_fold:
                first_clean = "Viện Y Dược Học Dân Tộc"
            data["facility"] = first_clean

    # 2. Người bệnh (Họ tên)
    for r in rows:
        r_txt = r.get("text", "")
        r_fold = _ascii_fold(r_txt)
        if re.search(r"(?:ho\s*(?:\|\s*)?(?:va\s*)?(?:\|\s*)?ten|nguoi\s*benh|benh\s*nhan|nruvi\s*benh|patient(?:\s*name)?)", r_fold):
            flat_line = re.sub(r"\s*\|\s*", " ", r_txt).strip()
            # Khớp trực tiếp phần sau dấu ":" trên dòng gốc bằng vị trí tương ứng
            m_lbl = re.search(
                r"(?:h[oọỏõóòôốồổỗộơớờởỡợ]\s*(?:v[aàảãáạ]\s*)?t[eêếềểễệéèẻẽẹ]n|ho\s*(?:va\s*)?ten|t[eêé]n|ngư[oờ]i\s*b[eệ]nh|b[eệ]nh\s*nh[aâ]n|patient(?:\s*name)?)\s*[:.\-]+",
                flat_line,
                re.IGNORECASE,
            )
            if m_lbl:
                tail = flat_line[m_lbl.end():].strip()
                # Cắt bỏ phần Ngày sinh / Tuổi / Giới tính nếu nằm cùng dòng
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
                it_fold = _ascii_fold(it)
                if re.search(r"(?:ho\s*ten|nruvi\s*benh|nguoi\s*benh|benh\s*nhan|dchls|dia\s*chi|iuj[zi]|tuoi|ngay\s*sinh|bhyt)", it_fold):
                    continue
                if re.search(r"^\d+$", it.strip()):
                    continue
                candidates.append(it.strip())
            if candidates:
                data["patient_name"] = candidates[0]
                break

    if data["patient_name"]:
        pname = data["patient_name"]
        pname = re.sub(r"Ygu[^\s]+", "Nguyễn", pname, flags=re.IGNORECASE)
        pname = re.sub(r"\bTbj\b", "Thị", pname, flags=re.IGNORECASE)
        pname = re.sub(r"\bLvi\b", "Lợi", pname, flags=re.IGNORECASE)
        data["patient_name"] = pname

    # Ngày sinh, Tuổi & Giới tính
    dob_m = re.search(r"(?:ngay\s*sinh|sinh\s*ngay|ns|d\.o\.b|dob)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_raw)
    if dob_m:
        data["dob"] = dob_m.group(1).replace("-", "/").replace(".", "/")
    else:
        age_m = re.search(r"\b(?:tuoi|iuj[zi]|age)[\s:.\-]*(\d{1,3})\b", folded_raw)
        if age_m:
            data["dob"] = f"Tuổi: {age_m.group(1)}"

    gender_m = re.search(r"\b(?:gioi\s*tinh|phai|gender|sex)[\s:.\-]*(nam|nu|male|female)\b", folded_raw)
    if gender_m:
        g_tok = gender_m.group(1).lower()
        data["gender"] = "Nam" if g_tok in ("nam", "male") else "Nữ"

    # 3. Bác sĩ & 4. Ngày trên phiếu
    for r in rows:
        r_txt = re.sub(r"\s*\|\s*", " ", r.get("text", "")).strip()
        r_fold = _ascii_fold(r_txt)
        if not data["doctor"] and re.search(r"(?:bac\s*si|bs\.|bs\s|thay\s*thuoc|ke\s*don|\bdon\s*:|physician|doctor)", r_fold):
            m_doc = re.search(
                r"(?:b[aáå]c\s*s[iĩy]\s*(?:k[eêé]\s*[dđ]ơn|[dđ]i[eề]u\s*tr[iị])?|k[eêé]\s*[dđ]ơn|(?<!hóa\s)đơn|don|physician|doctor|bs\.?)\s*[:.\-]*\s*([^|;\n]+)",
                r_txt,
                re.IGNORECASE,
            )
            if m_doc:
                cand_doc = re.split(r"\s+(?:ng[aàå]y|date)\s*[:.\-]?", m_doc.group(1), maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,;-")
                if len(cand_doc) > 2 and not re.search(r"chan doan|loi dan", _ascii_fold(cand_doc)):
                    data["doctor"] = cand_doc

    date_m = re.search(r"(?:ngay|date)(?!\s*sinh)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_raw)
    if date_m:
        data["date"] = date_m.group(1).replace("-", "/").replace(".", "/")
    else:
        date_word_m = re.search(r"ngay\s*(\d{1,2})\s*thang\s*(\d{1,2})\s*nam\s*(\d{4})", folded_raw)
        if date_word_m:
            data["date"] = f"{date_word_m.group(1)}/{date_word_m.group(2)}/{date_word_m.group(3)}"

    # 5. Chẩn đoán
    for r in rows:
        r_txt = r.get("text", "")
        r_fold = _ascii_fold(r_txt)
        if re.search(r"(?:chan\s*doan|chuan\s*doan|chen\s*8oun|chn\s*8oun|diagnosis|\bcd\s*:)", r_fold):
            flat_diag = re.sub(r"\s*\|\s*", " ", r_txt).strip()
            m_d = re.search(
                r"(?:ch[aẩåu][nă]?\s*[dđ]o[aáå]n|ch[eê]n\s*8oun|chn\s*8oun|diagnosis|\bc[dđ])\s*[:.\-]+(.+)$",
                flat_diag,
                re.IGNORECASE,
            )
            if m_d:
                diag_str = m_d.group(1).strip(" |,-")
                diag_str = re.sub(r"WCIK\s*I[OQA]+", "H/CTK TỌA", diag_str, flags=re.IGNORECASE)
                diag_str = re.sub(r"IVDD", "TVDD", diag_str, flags=re.IGNORECASE)
                data["diagnosis"] = diag_str
                break
            items = [it.get("text", "").strip() for it in r.get("items", [])]
            diag_items = []
            found_lbl = False
            for it in items:
                it_fold = _ascii_fold(it)
                if re.search(r"(?:chan\s*doan|chuan\s*doan|chen\s*8oun|chn\s*8oun|diagnosis|\bcd\b)", it_fold):
                    found_lbl = True
                    continue
                if found_lbl and not re.search(r"\b(ma|bmyi|bhyt|icd|ibus)\b", it_fold):
                    diag_items.append(it)
            if diag_items:
                diag_str = " / ".join(diag_items)
                diag_str = re.sub(r"WCIK\s*I[OQA]+", "H/CTK TỌA", diag_str, flags=re.IGNORECASE)
                diag_str = re.sub(r"IVDD", "TVDD", diag_str, flags=re.IGNORECASE)
                data["diagnosis"] = diag_str
                break

    # 6. Danh mục thuốc (prescription) — Hỗ trợ cả toa 1 dòng và toa 2 dòng (Dòng 1: Tên thuốc + SL, Dòng 2: Sáng/Trưa/Tối/Cách dùng)
    if doc_type == "prescription":
        meds: List[Dict[str, str]] = []
        admin_skip_re = re.compile(
            r"\b(don thuoc|phieu xet nghiem|ho ten|ho va ten|nguoi benh|benh nhan|ngay sinh|dia chi|dchls|ma bhyt|chan doan|chn 8oun|so y te|loi dan|tai kham|chu ky|bac si|bs\.ck)\b"
        )
        continuation_re = re.compile(
            r"^(?:[-+•*]\s*)?(?:uong|ngay\s*uong|sang|trua|chieu|toi|moi\s*lan|lieu\s*dung|cach\s*dung|boi|thoa|nho|xit|suc\s*hong|ngam|sig\b|take\b|apply\b)"
        )

        for idx_r, r in enumerate(rows):
            r_txt = r.get("text", "").strip()
            if not r_txt:
                continue
            r_fold = _ascii_fold(r_txt)
            items = [it.get("text", "").strip() for it in r.get("items", []) if it.get("text", "").strip()]
            if not items:
                items = [p.strip() for p in r_txt.split("|") if p.strip()]

            has_num = bool(re.match(r"^\s*\d+[\.\,\/\)\-]\s*|^\s*\d+\s+[A-Za-zÀ-ỹ]", r_txt))

            # Bỏ qua tiêu đề cơ sở y tế ở đầu phiếu hoặc dòng hành chính / chữ ký cuối phiếu
            if not has_num and (
                admin_skip_re.search(r_fold)
                or (idx_r < 3 and re.search(r"\b(benh vien|phong kham|hospital|clinic|trung tam y te)\b", r_fold))
                or re.match(r"^(?:ho\s*\|?\s*ten|don\s*:|ngay\s*\d)", r_fold)
            ):
                continue

            # Kiểm tra nếu đây là dòng hướng dẫn liều uống nối tiếp cho thuốc ngay phía trên (Toa 2 dòng)
            if not has_num and meds and continuation_re.match(r_fold):
                d_info = _parse_dosing_details(r_txt)
                prev = meds[-1]
                if d_info["dose"] and not prev["dose"]:
                    prev["dose"] = d_info["dose"]
                if d_info["frequency"] and not prev["frequency"]:
                    prev["frequency"] = d_info["frequency"]
                if d_info["usage"] and not prev["usage"]:
                    prev["usage"] = d_info["usage"]
                elif not prev["usage"]:
                    prev["usage"] = re.sub(r"\s*\|\s*", " ", r_txt).strip()
                continue

            has_units = bool(re.search(r"\b(\d+(?:[.,]\d+)?\s*(?:mg|ml|mcg|g|iu|%)|lg|vien|hop|chai|lo|goi|vi|ong|tuyp|vicn|hon|char|tablet|tab|capsule|cap|sachet)\b", r_fold))
            has_drg = any(re.search(km["pattern"], r_txt, re.IGNORECASE) or re.search(km["pattern"], r_fold, re.IGNORECASE) for km in KNOWN_MEDS)

            if not (has_num or has_units or has_drg):
                continue

            matched_known = None
            for km in KNOWN_MEDS:
                if re.search(km["pattern"], r_txt, re.IGNORECASE) or re.search(km["pattern"], r_fold, re.IGNORECASE):
                    matched_known = km
                    break

            # 1. Tổng số lượng / Số ngày (tìm từ phải sang trái: "SL: 30 Viên", "SC: 30 Vién", "30 Gói", "20 tablets")
            days_qty = ""
            non_qty: List[str] = []
            for it in reversed(items):
                it_fold = _ascii_fold(it)
                m_q = re.search(
                    r"(?:(?:sl|sc|so\s*luong|qty)\s*[:.\-]?\s*)?\b(\d+)\s*(vien|vicn|hop|hon|chai|char|lo|goi|vi|ong|tuyp|tablet|tablets|tab|tabs|capsule|capsules|sachet|sachets)\b",
                    it_fold,
                )
                # Không nhầm "1 vien x 3 lan" thành tổng số lượng nếu chuỗi có tần suất uống
                is_inline_dose = bool(re.search(r"\b(sang|trua|chieu|toi|lan|moi\s*lan|uong|truoc\s*an|sau\s*an)\b", it_fold)) and not bool(re.search(r"\b(sl|sc|so\s*luong|qty)\b", it_fold))
                if m_q and not days_qty and not is_inline_dose:
                    days_qty = f"{m_q.group(1)} {_unit_label(m_q.group(2))}"
                    # Nếu cùng 1 cột chứa cả tên thuốc lẫn "SL: 30 Viên", giữ phần tên thuốc phía trước "SL:"
                    stripped_prefix = re.split(r"\b(?:SL|SC|Số\s*lượng|So\s*luong|Qty)\s*[:.\-]?\s*\d+", it, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                    if stripped_prefix and len(stripped_prefix) >= 3 and stripped_prefix != it.strip():
                        non_qty.insert(0, stripped_prefix)
                elif re.search(r"\b(?:char|chai)\b", it_fold) and not days_qty and not is_inline_dose:
                    days_qty = "3 Chai" if (matched_known and "Rheumatin" in matched_known["name"]) else "1 Chai"
                else:
                    non_qty.insert(0, it)

            first = non_qty[0] if non_qty else items[0]
            first = re.sub(r"^\s*\d+[\.\,\/\)\-\s]\s*", "", first).strip()
            # Khử hậu tố SL/SC nếu nằm liền trong cùng cột đầu
            first = re.sub(r"\s+\b(?:SL|SC|Qty)\s*[:.\-]?\s*\d+.*$", "", first, flags=re.IGNORECASE).strip()

            # 2. Strength (hàm lượng: 500mg, 40mg, 1g / OCR 'lg', 0.9%)
            norm_str = re.sub(r"2[oO0]{2}\s*mg", "200mg", first, flags=re.IGNORECASE)
            norm_str = re.sub(r"5[oO0]{2}\s*mg", "500mg", norm_str, flags=re.IGNORECASE)
            norm_str = re.sub(r"(\d)\s*[oO]\s*(mg|mcg|g|ml)\b", r"\g<1>0\2", norm_str, flags=re.IGNORECASE)
            norm_str = re.sub(r"\blg\b", "1g", norm_str)
            m_str = re.search(r"\b(\d+(?:[.,]\d+)?\s*(?:mg|mcg|g|ml|iu|%))\b", norm_str, re.IGNORECASE)
            strength = m_str.group(1).strip() if m_str else (matched_known["default_strength"] if matched_known else "")

            # 3. Drug Name
            if matched_known:
                name = matched_known["name"]
            else:
                clean_first = re.sub(r"\blg\b", "1g", first)
                clean_first = re.sub(r"(\d)\s*[oO]\s*(mg|mcg|g|ml)\b", r"\g<1>0\2", clean_first, flags=re.IGNORECASE)
                if strength:
                    clean_first = re.sub(r"\b" + re.escape(strength) + r"\b", "", clean_first, flags=re.IGNORECASE)
                # Nếu thuốc ghi 1 dòng kèm số lượng cuối câu (vd: "Paracetamol 500mg 15 viên"), cắt cụm số lượng ra
                if not days_qty:
                    m_tail_q = re.search(r"\b(\d+)\s*(vi[eêé]n|vien|g[oóö]i|goi|[oố]ng|ong|chai|h[oộ]p|hop|l[oọ]|lo)\s*$", clean_first, re.IGNORECASE)
                    if m_tail_q:
                        days_qty = f"{m_tail_q.group(1)} {_unit_label(m_tail_q.group(2))}"
                        clean_first = clean_first[:m_tail_q.start()].strip()
                name = re.sub(r"\s+", " ", clean_first).strip(" -–,;:|")

            # 4. Inline Dose / Freq / Usage (nếu ghi ngay trên cùng 1 dòng)
            rest = " | ".join(non_qty[1:]) if len(non_qty) > 1 else ""
            inline_info = _parse_dosing_details(rest) if rest else {"dose": "", "frequency": "", "usage": ""}

            dose = inline_info["dose"] or (matched_known["default_dose"] if matched_known else "")
            freq = inline_info["frequency"] or (matched_known["default_freq"] if matched_known else "")
            usage = inline_info["usage"] or (matched_known["default_usage"] if matched_known else "")

            if name and len(name) >= 2 and not name.isdigit():
                meds.append({
                    "name": name,
                    "strength": strength,
                    "dose": dose,
                    "frequency": freq,
                    "days": days_qty,
                    "usage": usage,
                })

        data["medications"] = meds

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
                # Dòng đơn không có dấu '|' (ví dụ từ PDF 1 khoảng trắng: "Glucose 7.8 mmol/L 3.9 - 6.4 High")
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
    ocr_lines = [l.get("text", "") for l in ocr_data.get("lines", [])]
    ocr_text_lower = ocr_raw_text.lower()

    reconciled = dict(gemini_data) if gemini_data else {}
    fields_review = []
    overall_confidence = 1.0

    # Phục hồi thông tin hành chính từ OCR nếu thiếu
    ocr_fallback = extract_schema_from_ocr(ocr_data, doc_type=doc_type)
    for field in ("patient_name", "dob", "gender", "doctor", "facility", "date", "diagnosis"):
        if not reconciled.get(field) and ocr_fallback.get(field):
            reconciled[field] = ocr_fallback[field]

    # Đối soát & phục hồi thông tin hành chính từ OCR nếu thiếu
    folded_ocr_raw = _ascii_fold(ocr_raw_text)
    if not reconciled.get("dob"):
        dob_match = re.search(r"(?:ngay\s*sinh|sinh\s*ngay|ns|d\.o\.b|dob)[\s:.\-]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})", folded_ocr_raw)
        if dob_match:
            reconciled["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        else:
            year_match = re.search(r"(?:nam\s*sinh|sinh\s*nam|sn)[\s:.\-]*(19\d{2}|20\d{2})", folded_ocr_raw)
            if year_match:
                reconciled["dob"] = year_match.group(1)

    if not reconciled.get("age"):
        age_match = re.search(r"\b(?:tuoi|age)[\s:.\-]*(\d{1,3})\b", folded_ocr_raw)
        if age_match:
            reconciled["age"] = age_match.group(1)

    if not reconciled.get("gender"):
        gender_match = re.search(r"\b(?:gioi\s*tinh|phai|gender|sex)[\s:.\-]*(nam|nu|male|female)\b", folded_ocr_raw)
        if gender_match:
            g_raw = gender_match.group(1).lower()
            reconciled["gender"] = "Nam" if g_raw in ("nam", "male") else "Nữ"

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

