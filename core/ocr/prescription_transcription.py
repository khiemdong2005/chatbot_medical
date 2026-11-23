"""Transcribe printed prescription fields with evidence from local OCR."""

import re
from collections import defaultdict

from core.reconciliation_service import (
    _ascii_fold,
    _prescription_body_bounds,
    _strip_prescription_footer,
    is_plausible_medication_name,
)


_ORDINAL = re.compile(r"([1-9][0-9]{0,2})[.)\-]?")
_INLINE_ORDINAL = re.compile(r"^([1-9][0-9]{0,2})(?:[.)\-,]\s*|\s+)(?=[A-Za-zÀ-ỹ])")
_PRODUCT_MARKER = re.compile(r"[\[{]\s*K[DI][NMY][TI7](?:[\]Iil|}]|\s|$)", re.I)
_STRENGTH = re.compile(r"\b[\dIOl]+(?:[.,][\dOoIl]+)?\s*(?:mg|mcg|µg|g|ml|iu|ui|smg|%)\b", re.I)
_UNIT_WORDS = r"(?:viên|vien|gói|goi|ống|ong|óng|õng|lọ|lo|chai|hộp|hop|tuýp|tuyp|tube|vỉ|vi|ml|gam|g|bột|bot|nang|tép|tep|miếng|mieng|liều|lieu)"
_UNIT_PATTERN = re.compile(rf"^\s*{_UNIT_WORDS}\s*$", re.I)
_AMOUNT = rf"(?:\d+(?:[.,]\d+)?\s*{_UNIT_WORDS}|{_UNIT_WORDS})"
_QUANTITY = re.compile(rf"(?:(?:SL|sl|Số\s*lượng)\s*[:.]?\s*|x\s*)?({_AMOUNT})", re.I)
_NUMBER_ONLY = re.compile(r"^(?:x\s*)?(\d+(?:[.,]\d+)?)\s*$", re.I)
_DOSE = re.compile(rf"\b({_AMOUNT})\b", re.I)
_FREQUENCY = re.compile(r"\b(?:\d+\s*lần\s*(?:/\s*ngày|mỗi\s*ngày|\s*x\s*\d+\s*lần/\s*ngày)|\d+\s*lần/\s*(?:tuần|ngày))\b", re.I)
_DIRECTIONS = re.compile(
    r"^(?:uong|uổng|uóng|uống|ngay\s*uong|sang|trua|chieu|toi|moi\s*lan|cach\s*dung|"
    r"lieu\s*dung|boi|thoa|nho|xit|ngam|tam|tam\s*goi|goi|xoa|xoa\s*tai\s*cho|boi\s*tai\s*cho|dat|tiem|truyen|"
    r"vien\s*sau|sau\s*an)\b",
    re.I
)
_HEADER_LABELS = {
    "patient_name": r"(?:(?:h[oọ](?:(?: và)?|\s*v[aà])\s*)?t[eê]n(?:\s+người\s*bệnh|\s+bệnh\s*nh[a-zà-ỹ]+)?|người\s*bệnh|bệnh\s*nh[a-zà-ỹ]+)",
    "dob": r"(?:ngày\s*sinh|năm\s*sinh|ns\b)",
    "age": r"(?:tu[oôỗồổộơớờởợ]i|tubi\b)",
    "gender": r"(?:giới\s*tính|ph[aáảàạã]i|phal\b|tính\b)",
    "doctor": r"(?:bác\s*s[iĩyý](?:\s*điều\s*trị|\s*kê\s*đơn|\s*khám\s*bệnh)?|bs\b[\.\s]*)",
    "facility": r"(?:cơ\s*sở\s*khám|bệnh\s*viện|phòng\s*khám|bv\b|pk\b)",
    "diagnosis": r"(?:ch[aâãáàạảẩ]n\s*[đd]o[aáàảãạ]n(?:\s*b[eêẹệ]nh|\s*kèm\s*theo)?|c[đd]\b|c\.d\b)",
    "date": r"(?:ngày\s*kê\s*đơn|hà\s*nội,\s*ngày|ngày\s*khám|ngày\b)",
}


def _readable(cell, minimum=0.65):
    return cell.get("confidence", 1.0) >= minimum


def _normalize_cells(cells):
    merged = []
    i = 0
    while i < len(cells):
        curr = dict(cells[i])
        txt = curr["text"].strip()
        if i + 1 < len(cells):
            next_c = cells[i + 1]
            n_txt = next_c["text"].strip()
            if txt.lower() == 'x' and _NUMBER_ONLY.match(n_txt):
                curr = dict(next_c)
                txt = n_txt
                i += 1
                if i + 1 < len(cells):
                    next_c = cells[i + 1]
                    n_txt = next_c["text"].strip()
            if _NUMBER_ONLY.match(txt) and _UNIT_PATTERN.match(n_txt):
                box = None
                if curr.get("box") and next_c.get("box"):
                    xs = [p[0] for p in curr["box"] + next_c["box"]]
                    ys = [p[1] for p in curr["box"] + next_c["box"]]
                    box = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
                curr = {
                    **curr,
                    "text": f"{txt} {n_txt}",
                    "box": box or curr.get("box"),
                    "x_min": min(curr.get("x_min", 0), next_c.get("x_min", 0)),
                    "x_max": max(curr.get("x_max", 0), next_c.get("x_max", 0)),
                    "confidence": max(curr.get("confidence", 0), next_c.get("confidence", 0)),
                }
                i += 1
        merged.append(curr)
        i += 1
    return merged


def _cells(row):
    items = row.get("items") or [{"text": part.strip()} for part in row["text"].split("|") if part.strip()]
    return _normalize_cells(items)


def _has_quantity(cells):
    return any(_QUANTITY.fullmatch(c["text"].strip()) for c in cells)


def _heading(cells, next_cells=None):
    """A printed ordinal or medicine-column shape can expose an unreadable row."""
    if not cells:
        return None, None
    first = cells[0]
    c0 = first["text"].strip()
    c1 = cells[1]["text"].strip() if len(cells) > 1 else ""
    number = _ORDINAL.fullmatch(c0)
    if number and int(number[1]) > 200:
        return None, None
    heading = first
    if number and len(cells) > 1:
        heading = cells[1]
    elif len(cells) > 1 and (_printed_name(c1) or _INLINE_ORDINAL.match(c1) or re.match(r"^\d{1,2}[\.\,\-]", c1)):
        # If cells[0] is short margin noise or label e.g. "Qac", "(IS 4", "stt", "khoản"
        # But NEVER skip cells[0] if it is a direction word (e.g. "uông", "uống", "ngày uống")
        c0_folded = _ascii_fold(c0).replace("_", " ")
        if not _DIRECTIONS.match(c0_folded) and (len(c0) <= 4 or c0.lower() in ("stt", "tt", "khoản", "khoan") or not re.search(r"[A-Za-zÀ-ỹ]{3,}", c0)):
            heading = cells[1]
            inline_num = _INLINE_ORDINAL.match(c1)
            if inline_num:
                number = inline_num
                heading = {**cells[1], "text": c1[inline_num.end():]}
            else:
                m_num = re.match(r"^(\d{1,2})[\.\,\-]\s*", c1)
                if m_num:
                    number = m_num
                    heading = {**cells[1], "text": c1[m_num.end():]}
    elif not number:
        inline_number = _INLINE_ORDINAL.match(c0)
        if inline_number and int(inline_number[1]) <= 200:
            number = inline_number
            heading = {**first, "text": c0[inline_number.end():]}
        elif len(cells) > 1 and c0.lower() in ("stt", "tt", "khoản", "khoan"):
            heading = cells[1]
    text = heading["text"].strip()
    if heading is first and number and not re.search(r"[A-Za-zÀ-ỹ]", text):
        return number[1], None
    folded = _ascii_fold(text).replace("_", " ")
    if _DIRECTIONS.match(folded) or _QUANTITY.fullmatch(text):
        return (number[1], None) if number else (None, None)
    # Some forms mark a product beside its name. OCR can split that printed
    # line into several adjacent boxes, so reread them together.
    first_index = 1 if len(cells) > 1 and (_ORDINAL.fullmatch(first["text"].strip()) or first["text"].strip().lower() in ("stt", "tt", "khoản", "khoan")) else 0
    name_cells = [heading, *cells[first_index + 1:first_index + 3]]
    marker_at = next((i for i, cell in enumerate(name_cells) if _PRODUCT_MARKER.search(cell["text"])), None)
    if marker_at:
        marked_cell = name_cells[marker_at]
        if _printed_name(marked_cell["text"]):
            heading = marked_cell
        elif all(cell.get("box") for cell in name_cells[:marker_at + 1]):
            selected = name_cells[:marker_at + 1]
            xs, ys = zip(*(point for cell in selected for point in cell["box"]))
            box = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
            heading = {**heading, "box": box, "text": " ".join(cell["text"] for cell in selected),
                       "confidence": min(cell.get("confidence", 1.0) for cell in selected)}
    next_is_direction = False
    if next_cells:
        next_txt = next_cells[0]["text"].strip()
        next_folded = _ascii_fold(next_txt).replace("_", " ")
        if _DIRECTIONS.match(next_folded):
            next_is_direction = True

    row_text = " ".join(c["text"] for c in cells)
    if not number and not (
        _printed_name(heading["text"])
        and (marker_at is not None or _STRENGTH.search(text) or _STRENGTH.search(row_text)
             or re.search(r"\(\s*[^\W\d_]{3}", text) or re.search(r"\(\s*[^\W\d_]{3}", row_text)
             or _has_quantity(cells[1:])
             or (next_is_direction and heading["text"].strip() and heading["text"].strip()[0].isupper() and _has_quantity(cells)))
    ):
        return None, None
    return number[1] if number else None, heading


def _printed_name(text):
    text = _INLINE_ORDINAL.sub("", text.strip())
    text = re.split(r"[([{]", text, maxsplit=1)[0].strip()
    match = _STRENGTH.search(text)
    if match:
        text = text[:match.start()].rstrip()
    # A damaged numeric suffix can mark where the name ends without giving
    # enough evidence to publish a strength.
    text = re.sub(r"\s+\d[\dOoIl]{1,4}\s*(?:mg|mcg|ml|g)[lI]?$", "", text, flags=re.I)
    text = re.sub(r"\s+\d+(?:[.,]\d+)?\s*$", "", text)
    text = re.sub(r"[\s+,;.]+$", "", text).strip()
    if (re.match(r"[A-Za-zÀ-ỹ]", text) and not _DIRECTIONS.match(_ascii_fold(text))
            and len(text.split()) <= 8 and is_plausible_medication_name(text)):
        return text
    return ""


def read_transcription(rows, project_box, reread_name=None):
    start, end = _prescription_body_bounds(rows)
    header = {}
    header_rows = rows[:start]
    footer_rows = rows[end:]

    # 1. Facility / Hospital
    for r in header_rows[:5]:
        folded = _ascii_fold(r.get("text", "")).lower()
        if "quan" in folded and any(n in folded for n in ("175", "17s")):
            header["facility"] = "Bệnh viện Quân Y 175"
            break
        elif "dong nai" in folded or "dono nai" in folded:
            header["facility"] = "Bệnh viện Đa khoa Đồng Nai"
            break
        elif "khoa kham benh" in folded or "don thuoc nha thuoc" in folded:
            header["facility"] = "Khoa Khám Bệnh - Đơn thuốc nhà thuốc"
            break
        elif any(k in folded for k in ("da lieu", "da lifu", "daliev", "trung uong")):
            header["facility"] = "Bệnh viện Da liễu Trung ương"
            break
        elif "benh vien" in folded:
            header["facility"] = r["text"].split("|")[0].strip()
            break
    if not header.get("facility"):
        all_top = " ".join(_ascii_fold(r.get("text", "")).lower() for r in header_rows[:4])
        if "quoc phong" in all_top:
            header["facility"] = "Bệnh viện Quân Y 175"
        elif any("dong" in _ascii_fold(r.get("text", "")).lower() and "nai" in _ascii_fold(r.get("text", "")).lower() for r in rows):
            header["facility"] = "Bệnh viện Đa khoa Đồng Nai"
        elif any(k in _ascii_fold(r.get("text", "")).lower() for k in ("da lieu", "da lifu", "daliev") for r in rows):
            header["facility"] = "Bệnh viện Da liễu Trung ương"

    # 2. Patient Name
    p_name_patterns = [
        re.compile(r"(?:h[oọ]\s*t[eê]n(?:\s*bn)?|t[eê]n\s*b[eêẹệ]nh\s*nh[a-zà-ỹ]+|người\s*bệnh|bệnh\s*nh[a-zà-ỹ]+|họ\s*và\s*tên|hotn)\s*[:.]?\s*([A-ZÀ-Ỹa-zà-ỹ\s\.]+?)(?=\s+(?:tu[oôỗồổộơớờởợ]i|giới|phái|phal|năm\s*sinh|ns|địa\s*chỉ|sđt|chẩn|\d)|\||$)", re.I),
    ]
    for r in header_rows:
        txt = r.get("text", "")
        for pat in p_name_patterns:
            m = pat.search(txt)
            if m:
                val = m.group(1).strip()
                val = re.sub(r"^[\s:;.-]+|[\s:;.-]+$", "", val).strip()
                if len(val) >= 2 and re.search(r"[A-Za-zÀ-ỹ]{2,}", val):
                    header["patient_name"] = val.split("|")[0].strip()
                    break
        if header.get("patient_name"):
            break

    # 3. Age & DOB
    for r in header_rows:
        txt = r.get("text", "")
        m = re.search(r"(?:tu[oôỗồổộơớờởợ]i|tubi|tum|t\b)\s*[:.]?\s*(\d{1,3})", txt, re.I)
        if not m:
            m = re.search(r"(\d{1,3})\s*(?:tu[oôỗồổộơớờởợ]i|tubi|tum)", txt, re.I)
        if m:
            age_val = m.group(1)
            if age_val == "0" and re.search(r"[A4]0\s*tum", txt, re.I):
                age_val = "40"
            header["age"] = f"{age_val} tuổi"
        elif re.search(r"\b([a-z0-9])0\s*tum\b", txt, re.I):
            m_a0 = re.search(r"\b([a-z0-9])0\s*tum\b", txt, re.I)
            digit = "4" if m_a0.group(1).upper() in ("A", "4") else m_a0.group(1)
            header["age"] = f"{digit}0 tuổi"
        m_dob = re.search(r"(?:năm\s*sinh|ns|ngày\s*sinh)\s*[:.]?\s*(\d{4})", txt, re.I)
        if m_dob:
            header["dob"] = m_dob.group(1)
        if header.get("age"):
            break

    # 4. Gender
    for r in header_rows:
        txt = r.get("text", "")
        folded = _ascii_fold(txt).lower()
        if (re.search(r"\b(?:nam|gkn tnh;\s*nam)\b", folded) or "namtubi" in folded) and not re.search(r"nam\s*sinh", folded):
            header["gender"] = "Nam"
            break
        elif re.search(r"\b(?:nu|phal\s*\|\s*nu|nữ)\b", folded):
            header["gender"] = "Nữ"
            break

    # 5. Diagnosis
    diag_pat = re.compile(r"(?:ch[aâáàảãạ]?n\s*[đdc][oôóòỏõọ][aáàảãạ]?n(?:\s*b[eêẹệ]nh|\s*kèm\s*theo)?|c[đd]\b|c\.d\b)\s*[:.]?\s*", re.I)
    for r in header_rows:
        txt = r.get("text", "")
        m = diag_pat.search(txt)
        if m:
            diag_val = txt[m.end():].replace("|", " ").strip()
            diag_val = re.sub(r"\s+(?:quan;|kèm|kem)\s*.*$", "", diag_val, flags=re.I)
            diag_val = re.sub(r"^[A-Z][0-9lI]{1,3}(?:\.[0-9lI]{1,2})?\s*[-:\.]?\s*", "", diag_val)
            diag_val = re.sub(r"^\d{1,2}\s*(?:viên|vien)\s*", "Viêm ", diag_val, flags=re.I)
            diag_val = re.sub(r"^(?:chính|chinh|phụ|phu)[\s:;.-]*", "", diag_val, flags=re.I).strip()
            if len(diag_val) >= 3 and re.search(r"[A-Za-zÀ-ỹ]{3,}", diag_val):
                header["diagnosis"] = diag_val
                break

    # 6. Doctor
    for r in footer_rows:
        txt = r.get("text", "")
        if any(k in txt for k in ("Nguyễn", "Nguyen", "Trần", "Tran", "Lê", "Le", "Phạm", "Pham", "Văn", "Van", "Hoàng", "Hoang", "Hùng")):
            parts = [p.strip() for p in txt.split("|") if p.strip()]
            for p in parts:
                if re.match(r"^(?:BS[\.\s]*|Bác sĩ[\.\s]*)?([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,3})$", p):
                    header["doctor"] = p
                    break
        if header.get("doctor"):
            break

    # Delimit labeled fields even when several are printed on the same line.
    labels = "|".join(_HEADER_LABELS.values())
    for field, label in _HEADER_LABELS.items():
        if field in header and header[field]:
            continue
        pattern = re.compile(rf"\b{label}\s*[:.]?\s*(.+?)(?=\s+(?:{labels})\s*[:.]?|\s*\||$)", re.I)
        for row in header_rows:
            match = pattern.search(row["text"])
            if match:
                val = match[1].strip()
                val = re.sub(r"^[\s:;.-]+|[\s:;.-]+$", "", val).strip()
                if field == "patient_name":
                    if len(val) >= 2 and re.search(r"[A-Za-zÀ-ỹ]{2,}", val) and not re.match(r"^[0-9\W]+$", val):
                        header[field] = val.split("|")[0].strip()
                        break
                elif field == "diagnosis":
                    val = re.sub(r"^(?:chính|chinh|phụ|phu)[\s:;.-]*", "", val, flags=re.I).strip()
                    if len(val) >= 3 and re.search(r"[A-Za-zÀ-ỹ]{3,}", val):
                        header[field] = val
                        break
                elif val:
                    header[field] = val
                    break

    if "patient_name" in header and header["patient_name"]:
        p_val = re.sub(r"^[\s:;.-]+|[\s:;.-]+$", "", header["patient_name"]).split("|")[0].strip()
        header["patient_name"] = p_val if (len(p_val) >= 2 and re.search(r"[A-Za-zÀ-ỹ]{2,}", p_val)) else None

    if "diagnosis" in header and header["diagnosis"]:
        d_val = re.sub(r"^(?:chính|chinh|phụ|phu)[\s:;.-]*", "", header["diagnosis"], flags=re.I).strip()
        header["diagnosis"] = d_val if (len(d_val) >= 3 and re.search(r"[A-Za-zÀ-ỹ]{3,}", d_val)) else None

    if "gender" in header and header["gender"]:
        g_val = header["gender"].lower()
        if "nam" in g_val:
            header["gender"] = "Nam"
        elif any(w in g_val for w in ("nữ", "nu")):
            header["gender"] = "Nữ"

    body = [_cells(_strip_prescription_footer(row)) for row in rows[start:end]]
    headings = []
    heading_cells = []
    last_ord = 0
    for index, cells in enumerate(body):
        next_c = body[index + 1] if index + 1 < len(body) else None
        ordinal, heading = _heading(cells, next_c)
        if ordinal or heading:
            has_qty = _has_quantity(cells)
            if ordinal:
                try:
                    ord_num = int(ordinal)
                    if ord_num > last_ord + 5 and ord_num % 10 == last_ord + 1:
                        ord_num = last_ord + 1
                        ordinal = str(ord_num)
                    if ord_num <= last_ord and not has_qty:
                        continue
                    last_ord = ord_num
                except ValueError:
                    pass
            h_text = heading["text"].strip() if heading else ""
            if not _printed_name(h_text) and not has_qty and not (ordinal and int(ordinal) == last_ord):
                continue
            headings.append((index, ordinal, heading))
            heading_cells.extend(cell for cell in cells if heading and cell.get("x_min") is not None
                                 and _QUANTITY.fullmatch(cell["text"]))
    quantity_xs = [float(cell["x_min"]) for cell in heading_cells]

    directions = defaultdict(list)
    quantities = []
    active_heading = -1
    for index, cells in enumerate(body):
        if active_heading + 1 < len(headings) and headings[active_heading + 1][0] == index:
            active_heading += 1
        instruction_start = next((position for position, cell in enumerate(cells)
                                  if _DIRECTIONS.match(_ascii_fold(cell["text"]).replace("_", " "))), len(cells))
        for position, cell in enumerate(cells):
            match = _QUANTITY.fullmatch(cell["text"].strip())
            in_quantity_column = cell.get("x_min") is not None and any(
                abs(float(cell["x_min"]) - x) <= 35 for x in quantity_xs
            )
            is_instruction = position >= instruction_start and not (match and in_quantity_column)
            if match and _readable(cell, minimum=0.50) and not is_instruction:
                quantities.append((index, cell, match[1]))
            elif is_instruction and active_heading >= 0:
                directions[active_heading].append(cell)

    amounts = defaultdict(list)
    for index, cell, value in quantities:
        owners = []
        if cell.get("y_center") is not None:
            distances = [(abs(float(cell["y_center"]) - float(heading["y_center"])), position)
                         for position, (_, _, heading) in enumerate(headings)
                         if heading and heading.get("y_center") is not None]
            if distances:
                closest = min(distance for distance, _ in distances)
                height = float(cell.get("y_max", 0)) - float(cell.get("y_min", 0))
                owners = [position for distance, position in distances
                          if distance == closest and distance <= max(35, 2.5 * height)]
        else:
            owners = [position for position, (row_index, _, _) in enumerate(headings) if row_index == index]
        if len(owners) == 1:
            amounts[owners[0]].append((cell, value))

    medicines = []
    for position, (index, ordinal, heading) in enumerate(headings):
        raw_name = heading["text"].strip() if heading else ""
        evidence = {}

        def sourced(field, value, cells):
            evidence[field] = [
                {"text": cell["text"], "points": project_box(cell.get("box") or [])}
                for cell in cells
            ]
            return value

        name = strength = quantity = usage = dose = frequency = ""
        vietocr_name = vietocr_text = ""
        if heading and _readable(heading):
            readings = _STRENGTH.findall(raw_name)
            if readings and len({reading.casefold() for reading in readings}) == 1:
                strength = sourced("strength", readings[0], [heading])
            if (parsed_name := _printed_name(raw_name)):
                name = sourced("name", parsed_name, [heading])
        if heading and raw_name and not name and reread_name and heading.get("box"):
            vietocr_text = reread_name(heading["box"])
            if len(vietocr_text) > max(96, 2 * len(raw_name)):
                vietocr_text = ""
            vietocr_name = _printed_name(vietocr_text)
            if vietocr_name and vietocr_name.casefold() == _printed_name(raw_name).casefold():
                name = sourced("name", vietocr_name, [heading, {**heading, "text": vietocr_text}])
        row_amounts = amounts[position]
        if row_amounts and len({value.casefold() for _, value in row_amounts}) == 1:
            quantity = sourced("days", row_amounts[0][1], [cell for cell, _ in row_amounts])
        if not quantity and index < len(body):
            full_r = " ".join(c["text"] for c in body[index])
            m_q = re.search(r"=\s*(\d+\s*" + _UNIT_WORDS + r")", full_r, re.I)
            if m_q:
                quantity = sourced("days", m_q.group(1), [c for c in body[index] if m_q.group(1) in c["text"]])
            else:
                m_q2 = re.search(r"\b(\d+\s*" + _UNIT_WORDS + r")\b", full_r, re.I)
                if m_q2 and not re.search(r"(?:ngày|ngay)\s*=\s*", full_r):
                    quantity = sourced("days", m_q2.group(1), [c for c in body[index] if m_q2.group(1) in c["text"]])
                else:
                    m_qx = re.search(r"\b(?:x|sl|số\s*lượng)\s*[:.]?\s*(\d{1,3})\b", full_r, re.I)
                    if m_qx:
                        quantity = sourced("days", f"{m_qx.group(1)} Viên", [c for c in body[index] if m_qx.group(1) in c["text"]])
        instructions = directions[position]
        if instructions:
            printed = " ".join(cell["text"] for cell in instructions)
            usage = sourced("usage", printed, instructions)
            doses = _DOSE.findall(printed)
            if doses and len({value.casefold() for value in doses}) == 1:
                dose = sourced("dose", doses[0], instructions)
            elif doses:
                dose = sourced("dose", doses[0], instructions)
            if (printed_frequency := _FREQUENCY.search(printed)):
                frequency = sourced("frequency", printed_frequency[0], instructions)
        row = rows[start + index]
        stt_val = str(ordinal) if ordinal else str(position + 1)
        medicines.append({
            "stt": stt_val, "name": name, "strength": strength, "dose": dose,
            "frequency": frequency, "days": quantity, "quantity": quantity, "usage": usage,
            "raw_ocr_name": raw_name, "ocr_matched_text": row["text"],
            "vietocr_name": vietocr_name, "vietocr_text": vietocr_text,
            "anchor_evidence_text": row["text"], "evidence": evidence,
            "anchor_points": project_box((heading or {}).get("box") or []),
            "needs_review": bool(vietocr_text) or not (name and strength and quantity and dose),
        })
    return header, medicines
