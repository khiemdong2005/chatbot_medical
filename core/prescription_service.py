import os
import sys
import json
import re
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output on console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

from core.ocr_extractor import extract_prescription_text


def normalize_and_analyze_with_gemini(ocr_data: Dict[str, Any], original_filename: str = "", file_path: str = "") -> Optional[Dict[str, Any]]:
    """
    TẦNG 2 TRONG KIẾN TRÚC HYBRID:
    Bộ não suy luận lâm sàng & chuẩn hóa thực thể y tế (Clinical NLP & NER) bằng Gemini:
      - Nhận ảnh gốc + văn bản OCR thô trích xuất từ OpenCV + EasyOCR
      - Đối chiếu đa phương thức (Multimodal Cross-validation) tránh sai sót nhận diện tên thuốc
      - Khắc phục các lỗi chính tả quang học (OCR Typos) về tên thuốc, hoạt chất, nồng độ
      - Bóc tách cấu trúc: Cơ sở khám bệnh, Bác sĩ, Bệnh nhân, Chẩn đoán, Ngày tháng
      - Lập thời gian biểu uống thuốc chuẩn dược động học (Sáng - Trưa - Tối - Trước ngủ - Dùng ngoài)
      - Phân tích tương tác thuốc đối kháng, tác dụng phụ và cảnh báo an toàn
    """
    raw_text = ocr_data.get("raw_text", "").strip()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
Bạn là Bác sĩ Trưởng khoa Lâm sàng kiêm Chuyên gia Dược học AI hàng đầu tại Việt Nam.
Dưới đây là tài liệu y tế (kèm ảnh chụp và văn bản quét được từ mô hình OCR cục bộ OpenCV + EasyOCR):

--- VĂN BẢN QUÉT ĐƯỢC TỪ MÁY OCR CỤC BỘ ---
{raw_text}
--- KẾT THÚC VĂN BẢN QUÉT ---

HƯỚNG DẪN ĐẶC BIỆT DÀNH CHO ĐƠN THUỐC LÂM SÀNG TẠI VIỆT NAM:
1. Đọc kỹ ảnh chụp để ĐỐI CHIẾU VỚI VĂN BẢN OCR, ĐẢM BẢO BÓC TÁCH ĐỦ VÀ CHÍNH XÁC 100% CÁC MỤC THUỐC (KHÔNG BỎ SÓT THUỐC NÀO):
   - Đơn thuốc tại Việt Nam thường kết hợp thuốc tân dược và thuốc Đông y / Y học cổ truyền.
   - Tuyệt đối không nhầm lẫn tên hoạt chất và không tự bịa tên thuốc.
2. THÔNG TIN BỆNH NHÂN & CHẨN ĐOÁN:
   - Họ tên bệnh nhân (kèm tuổi, giới tính nếu có).
   - Địa chỉ.
   - Chẩn đoán xác định.
   - Đợt dùng / Thời gian điều trị.
3. PHÂN BỔ THỜI GIAN BIỂU UỐNG THUỐC:
   - Sáng (06:30 - 08:00), Trưa (11:30 - 12:30), Tối (18:00 - 19:30), Trước ngủ (21:00 - 22:00).
   - Ghi rõ note: "Trước ăn (30 phút)", "Sau khi ăn", hoặc "Dùng ngoài da".
4. CẢNH BÁO LÂM SÀNG (warnings).

BẮT BUỘC TRẢ VỀ DUY NHẤT MỘT ĐỐI TƯỢNG JSON HỢP LỆ (TUYỆT ĐỐI KHÔNG DÙNG ```json, KHÔNG GIẢI THÍCH):
{{
  "status": "success",
  "type": "prescription",
  "doc_title": "Đơn thuốc Điều trị ...",
  "facility": "Tên cơ sở y tế",
  "department": "Khoa phòng",
  "doctor": "Bác sĩ kê đơn",
  "patient_name": "Họ và tên bệnh nhân (tuổi, giới tính)",
  "address": "Địa chỉ",
  "diagnosis": "Chẩn đoán y khoa chi tiết",
  "date": "Ngày khám",
  "duration": "Thời gian điều trị",
  "timeline": {{
    "morning": [],
    "noon": [],
    "evening": [],
    "bedtime": [],
    "external": []
  }},
  "medications": [],
  "warnings": []
}}
"""

        # Prepare multimodal content if file_path exists
        contents_payload = []
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                img_bytes = f.read()
            ext = os.path.splitext(file_path)[1].lower()
            mime_type = "image/png" if ext == ".png" else "application/pdf" if ext == ".pdf" else "image/jpeg"
            contents_payload.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        contents_payload.append(prompt)

        candidate_models = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-latest"]
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )

        raw_json_str = None
        for model_name in candidate_models:
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                    config=config
                )
                if res and res.text:
                    raw_json_str = res.text.strip()
                    break
            except Exception:
                continue

        if not raw_json_str:
            return None

        cleaned = raw_json_str
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

        data = json.loads(cleaned)
        if isinstance(data, dict):
            data.setdefault("status", "success")
            data.setdefault("type", "prescription")
            data["scanned_by"] = "Kiến trúc Hybrid AI: Tiền xử lý OpenCV ➔ EasyOCR Tiếng Việt Cục bộ ➔ Gemini Multimodal Clinical NLP"
            data["pipeline_mode"] = "Hybrid Pipeline (Local Edge Computer Vision + Cloud Multimodal Verification)"
            data["uploaded_filename"] = original_filename or "Tai_lieu_y_te.jpg"
            data["ocr_stats"] = {
                "engine": "EasyOCR (Tiếng Việt + Tiếng Anh Local Engine)",
                "total_lines_detected": ocr_data.get("total_lines", 0),
                "avg_confidence_score": ocr_data.get("avg_confidence", 0.0),
                "ocr_duration_sec": ocr_data.get("ocr_duration_sec", 0.0),
                "deskew_angle": ocr_data.get("prep_info", {}).get("skew_angle", 0.0),
                "clahe_applied": ocr_data.get("prep_info", {}).get("clahe_applied", True)
            }
            data["raw_ocr_preview"] = [line["text"] for line in ocr_data.get("lines", [])[:15]]
            return data

    except Exception as e:
        print(f"[HYBRID CLINICAL NLP ERROR] Lỗi phân tích văn bản OCR: {e}")
        return None

    return None


def scan_prescription_with_gemini_vision(file_path: str, original_filename: str = "") -> Optional[Dict[str, Any]]:
    """
    DỰ PHÒNG CẤP 2 (Fallback Vision Multimodal):
    Dùng trực tiếp Gemini Vision khi ảnh scan quá mờ, chữ viết tay khó hoặc file PDF nhiều trang.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        ext = os.path.splitext(file_path)[1].lower()
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".pdf":
            mime_type = "application/pdf"

        prompt = """
        Bạn là Bác sĩ Trưởng khoa Lâm sàng kiêm Chuyên gia Dược học AI.
        Hãy quan sát tài liệu y tế này (bao gồm chữ in và chữ viết tay):
        1. Xác định type: "prescription" hay "lab_test".
        2. Nếu là prescription: trích xuất facility, department, doctor, patient_name, diagnosis, date, duration, timeline 4 cữ, medications và warnings.
        3. Nếu là lab_test: trích xuất metrics (name, value, unit, reference, status: High/Normal/Low, advice) và ai_summary.
        Trả về DUY NHẤT một JSON hợp lệ.
        """

        candidate_models = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-latest"]
        for model_name in candidate_models:
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt
                    ]
                )
                if res and res.text:
                    cleaned = res.text.strip()
                    if cleaned.startswith("```"):
                        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
                    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
                    if match:
                        cleaned = match.group(1).strip()
                    data = json.loads(cleaned)
                    if isinstance(data, dict):
                        data["scanned_by"] = "Google Gemini Vision Multimodal Fallback"
                        data["pipeline_mode"] = "End-to-End Vision Fallback"
                        data["uploaded_filename"] = original_filename or os.path.basename(file_path)
                        return data
            except Exception:
                continue

    except Exception as e:
        print(f"[VISION FALLBACK ERROR] {e}")

    return None


def analyze_uploaded_document(file_path: str, original_filename: str = "") -> Dict[str, Any]:
    """
    BỘ ĐIỀU PHỐI KIẾN TRÚC HYBRID:
      1. Tiền xử lý OpenCV + Bóc tách EasyOCR cục bộ.
      2. Chuyển văn bản sang Gemini để chuẩn hóa dược học.
      3. Dự phòng Gemini Vision nếu OCR không đọc được text.
      4. BẢO MẬT & TRUNG THỰC: Khi cả OCR và Gemini thất bại, KHÔNG tự bịa dữ liệu mẫu hoặc trả preset.
         Trả về trạng thái failed/needs_review kèm mã lỗi rõ ràng để người bệnh chụp lại.
    """
    filename_clean = original_filename or os.path.basename(file_path)

    if not os.path.exists(file_path):
        return {
            "status": "failed",
            "needs_review": True,
            "error_code": "FILE_NOT_FOUND",
            "message": "Không tìm thấy tệp tài liệu cần phân tích. Vui lòng thử tải lên lại.",
            "uploaded_filename": filename_clean
        }

    print(f"\n🚀 [HYBRID PIPELINE START] Tiếp nhận tệp: {filename_clean}")

    # BƯỚC 1: BÓC TÁCH BẰNG MÔ HÌNH OCR CỤC BỘ
    print("📸 [BƯỚC 1/2] Đang tiền xử lý ảnh OpenCV và chạy EasyOCR Tiếng Việt...")
    ocr_result = extract_prescription_text(file_path)
    total_lines = ocr_result.get("total_lines", 0)
    avg_conf = ocr_result.get("avg_confidence", 0.0)
    print(f"✅ [BƯỚC 1/2] Phát hiện {total_lines} dòng văn bản (Độ tin cậy TB: {avg_conf:.2f})")

    # BƯỚC 2: CHUẨN HÓA VĂN BẢN BẰNG GEMINI NLP NẾU CÓ DỮ LIỆU OCR
    if ocr_result.get("success") and total_lines >= 3:
        print("🧠 [BƯỚC 2/2] Chuyển dữ liệu OCR sang Gemini Clinical NLP...")
        hybrid_res = normalize_and_analyze_with_gemini(ocr_result, filename_clean, file_path)
        if hybrid_res:
            print("🎉 [HYBRID PIPELINE SUCCESS] Chuẩn hóa dược học thành công!")
            return hybrid_res

    # BƯỚC 3: DỰ PHÒNG GEMINI VISION NẾU ẢNH MỜ HOẶC PDF
    print("⚠️ [FALLBACK 1] Thử nghiệm Vision Multimodal dự phòng...")
    vision_res = scan_prescription_with_gemini_vision(file_path, filename_clean)
    if vision_res:
        return vision_res

    # BƯỚC 4: BÁO LỖI MINH BẠCH - TUYỆT ĐỐI KHÔNG BỊA KẾT QUẢ HAY TRẢ PRESET MẪU
    print("🛑 [PIPELINE FAILED] Không thể nhận diện nội dung. Trả trạng thái failed để người dùng chụp lại.")
    return {
        "status": "failed",
        "needs_review": True,
        "error_code": "OCR_OR_AI_ANALYSIS_FAILED",
        "message": "Không thể nhận diện nội dung đơn thuốc hoặc xét nghiệm từ tệp này. "
                   "Vui lòng chụp lại ảnh rõ nét, đủ sáng, căn chỉnh góc thẳng hoặc tải bản scan có độ phân giải cao hơn.",
        "uploaded_filename": filename_clean,
        "ocr_stats": {
            "engine": "EasyOCR (Tiếng Việt + Tiếng Anh Local Engine)",
            "total_lines_detected": total_lines,
            "avg_confidence_score": avg_conf,
            "ocr_duration_sec": ocr_result.get("ocr_duration_sec", 0.0)
        },
        "raw_ocr_preview": [line["text"] for line in ocr_result.get("lines", [])[:15]] if total_lines > 0 else []
    }


def get_preset_data(preset_key: str) -> Dict[str, Any]:
    """
    Trả về kịch bản mẫu thử nghiệm (Presets) CHỈ KHI ĐƯỢC YÊU CẦU RÕ RÀNG.
    Luôn đánh dấu is_demo: True để người dùng và giao diện nhận biết dữ liệu mô phỏng.
    """
    today = datetime.now().strftime("%d/%m/%Y")

    if preset_key in ["binh_dan", "tran_trung", "da_day_binh_dan"]:
        return {
            "status": "demo",
            "is_demo": True,
            "type": "prescription",
            "doc_title": "Đơn thuốc Điều trị Viêm Dạ Dày Cấp - Bệnh Viện Bình Dân (Dữ liệu Demo)",
            "facility": "SỞ Y TẾ TP. HỒ CHÍ MINH - BỆNH VIỆN BÌNH DÂN (DEMO)",
            "department": "Phòng khám Dịch Vụ 109 - (KTC)",
            "doctor": "BS. Nguyễn Văn Hùng",
            "patient_name": "TRẦN TRUNG (49 tuổi - Nam)",
            "address": "Xã Bảo Bình, Huyện Cẩm Mỹ, Tỉnh Đồng Nai",
            "diagnosis": "Viêm dạ dày cấp khác (Mã ICD: K29.1)",
            "date": "25/09/2014",
            "duration": "21 ngày (Đợt điều trị tấn công - 6 loại thuốc)",
            "timeline": {
                "morning": [
                    {"name": "YESOM 40 40mg", "dosage": "1 viên", "time": "06:30", "note": "Trước ăn sáng 30 phút", "tag": "Giảm tiết acid PPI", "color": "purple"},
                    {"name": "SUCRATE GEL 1g", "dosage": "1 gói", "time": "06:45", "note": "Trước ăn sáng 15-30 phút", "tag": "Băng se ổ loét", "color": "blue"},
                    {"name": "ARTHUR 200mg", "dosage": "1 viên", "time": "07:45", "note": "Sau ăn sáng 15 phút", "tag": "Điều hòa nhu động ruột", "color": "emerald"},
                    {"name": "PAPAZE", "dosage": "1 viên", "time": "07:45", "note": "Sau ăn sáng 15 phút", "tag": "Men tiêu hóa & Kháng acid", "color": "amber"},
                    {"name": "BIOCID MH 3.5+2g", "dosage": "1/3 chai (~33ml)", "time": "08:30", "note": "Sau ăn sáng 1 giờ", "tag": "Kháng acid dạng sữa", "color": "rose"},
                    {"name": "DIGLUMISAN 1000mg", "dosage": "1 ống", "time": "08:30", "note": "Uống sau ăn sáng", "tag": "Bảo vệ tế bào gan", "color": "indigo"}
                ],
                "noon": [
                    {"name": "SUCRATE GEL 1g", "dosage": "1 gói", "time": "11:30", "note": "Trước ăn trưa 15-30 phút", "tag": "Băng se ổ loét", "color": "blue"},
                    {"name": "ARTHUR 200mg", "dosage": "1 viên", "time": "12:30", "note": "Sau ăn trưa 15 phút", "tag": "Điều hòa nhu động", "color": "emerald"},
                    {"name": "PAPAZE", "dosage": "1 viên", "time": "12:30", "note": "Sau ăn trưa 15 phút", "tag": "Men tiêu hóa", "color": "amber"},
                    {"name": "BIOCID MH 3.5+2g", "dosage": "1/3 chai", "time": "13:30", "note": "Sau ăn trưa 1 giờ", "tag": "Kháng acid dạng sữa", "color": "rose"},
                    {"name": "DIGLUMISAN 1000mg", "dosage": "1 ống", "time": "13:30", "note": "Uống sau ăn trưa", "tag": "Bảo vệ gan", "color": "indigo"}
                ],
                "evening": [
                    {"name": "SUCRATE GEL 1g", "dosage": "1 gói", "time": "18:00", "note": "Trước ăn tối 15-30 phút", "tag": "Băng se ổ loét", "color": "blue"},
                    {"name": "ARTHUR 200mg", "dosage": "1 viên", "time": "19:00", "note": "Sau ăn tối 15 phút", "tag": "Điều hòa nhu động", "color": "emerald"},
                    {"name": "PAPAZE", "dosage": "1 viên", "time": "19:00", "note": "Sau ăn tối 15 phút", "tag": "Men tiêu hóa", "color": "amber"},
                    {"name": "BIOCID MH 3.5+2g", "dosage": "1/3 chai", "time": "20:00", "note": "Sau ăn tối 1 giờ", "tag": "Kháng acid dạng sữa", "color": "rose"},
                    {"name": "DIGLUMISAN 1000mg", "dosage": "1 ống", "time": "20:00", "note": "Uống sau ăn tối", "tag": "Bảo vệ gan", "color": "indigo"}
                ],
                "bedtime": [
                    {"name": "Lời dặn bác sĩ", "dosage": "Tái khám theo hẹn", "time": "21:30", "note": "Khám lại mang theo đơn thuốc này.", "tag": "Lịch hẹn tái khám", "color": "purple"}
                ]
            },
            "medications": [
                {
                    "name": "YESOM 40 (Esomeprazol 40mg) - 63 Viên",
                    "ingredient": "Esomeprazole 40mg",
                    "category": "Thuốc ức chế bơm proton thế hệ mới (PPI)",
                    "purpose": "Ức chế dạ dày tiết acid clohydric, giảm đau rát vùng thượng vị.",
                    "usage": "Uống nguyên viên vào buổi sáng trước khi ăn 30 phút."
                },
                {
                    "name": "SUCRATE GEL (Sucralfate 1g) - 63 Gói",
                    "ingredient": "Sucralfate 1g dạng gel",
                    "category": "Thuốc bảo vệ ổ loét dạ dày",
                    "purpose": "Tạo màng bảo vệ che phủ vết viêm trợt niêm mạc dạ dày.",
                    "usage": "Ngày uống 3 lần, mỗi lần 1 gói trước bữa ăn."
                }
            ],
            "warnings": [
                "[DỮ LIỆU MẪU DEMO]: Đây là đơn thuốc mẫu minh họa cho chức năng nhận diện đơn thuốc.",
                "Cần tuân thủ chỉ dẫn của bác sĩ điều trị và không tự ý điều chỉnh thuốc."
            ]
        }

    elif preset_key in ["throat", "tai_mui_hong", "ho_hap", "viem_hong"]:
        return {
            "status": "demo",
            "is_demo": True,
            "type": "prescription",
            "doc_title": "Đơn thuốc Điều trị Viêm Họng Cấp & Viêm Đường Hô Hấp Trên (Dữ liệu Demo)",
            "facility": "SỞ Y TẾ TP. HỒ CHÍ MINH - BỆNH VIỆN TAI MŨI HỌNG (DEMO)",
            "department": "Khoa Khám Bệnh Ngoại Trú (KTC)",
            "doctor": "BS. CKII Trần Minh Tâm",
            "patient_name": "NGUYỄN VĂN AN (32 tuổi - Nam)",
            "address": "Phường Võ Thị Sáu, Quận 3, TP. Hồ Chí Minh",
            "diagnosis": "Viêm họng cấp / Viêm amidan cấp mủ (Mã ICD: J02.9)",
            "date": today,
            "duration": "5 ngày (Đợt điều trị ngoại trú)",
            "timeline": {
                "morning": [
                    {"name": "Paracetamol 500mg", "dosage": "1 viên", "time": "08:00", "note": "Sau ăn sáng, dùng khi sốt > 38.5°C hoặc đau rát họng", "tag": "Hạ sốt & Giảm đau", "color": "blue"},
                    {"name": "Alpha Chymotrypsin 4.2mg", "dosage": "2 viên", "time": "08:00", "note": "Ngậm dưới lưỡi tan từ từ", "tag": "Kháng viêm & Tiêu phù nề", "color": "amber"},
                    {"name": "Dung dịch súc họng NaCl 0.9%", "dosage": "15ml", "time": "08:30", "note": "Súc họng kỹ sau khi đánh răng", "tag": "Sát khuẩn tại chỗ", "color": "emerald"}
                ],
                "noon": [
                    {"name": "Alpha Chymotrypsin 4.2mg", "dosage": "2 viên", "time": "13:00", "note": "Ngậm dưới lưỡi sau ăn trưa", "tag": "Kháng viêm", "color": "amber"},
                    {"name": "Dung dịch súc họng NaCl 0.9%", "dosage": "15ml", "time": "13:30", "note": "Súc họng sau bữa trưa", "tag": "Sát khuẩn", "color": "emerald"}
                ],
                "evening": [
                    {"name": "Paracetamol 500mg", "dosage": "1 viên", "time": "19:00", "note": "Sau ăn tối nếu còn đau rát họng hoặc sốt", "tag": "Hạ sốt giảm đau", "color": "blue"},
                    {"name": "Desloratadine 5mg", "dosage": "1 viên", "time": "20:00", "note": "Sau ăn tối, giảm kích ứng ho & nghẹt mũi", "tag": "Kháng Histamin H1", "color": "purple"},
                    {"name": "Dung dịch súc họng NaCl 0.9%", "dosage": "15ml", "time": "21:30", "note": "Súc họng trước khi ngủ", "tag": "Sát khuẩn tại chỗ", "color": "emerald"}
                ],
                "bedtime": [
                    {"name": "Lời dặn & Hẹn tái khám", "dosage": "Tái khám sau 5 ngày", "time": "22:00", "note": "Khám lại ngay nếu sốt cao liên tục không hạ hoặc khó nuốt, khó thở.", "tag": "Theo dõi lâm sàng", "color": "purple"}
                ]
            },
            "medications": [
                {
                    "name": "Paracetamol 500mg - 10 Viên",
                    "ingredient": "Paracetamol 500mg",
                    "category": "Thuốc giảm đau hạ sốt giảm đau ngoại vi",
                    "purpose": "Hạ nhiệt độ khi sốt trên 38.5°C, giảm đau rát họng khi nuốt thức ăn.",
                    "usage": "Uống 1 viên khi sốt hoặc đau rát, mỗi lần cách nhau tối thiểu 4-6 giờ."
                },
                {
                    "name": "Alpha Chymotrypsin 4.2mg (Chymoral) - 20 Viên",
                    "ingredient": "Chymotrypsin 4200 IU",
                    "category": "Enzym kháng viêm dạng ngậm",
                    "purpose": "Giảm phù nề, tiêu dịch viêm sung huyết niêm mạc hầu họng và amidan.",
                    "usage": "Ngậm dưới lưỡi 2 viên/lần, ngày 2 lần sáng và trưa."
                },
                {
                    "name": "Desloratadine 5mg (Aerius) - 5 Viên",
                    "ingredient": "Desloratadine 5mg",
                    "category": "Kháng Histamin H1 thế hệ 2",
                    "purpose": "Giảm phản xạ kích ứng đường thở, chống xuất tiết niêm mạc mũi họng.",
                    "usage": "Uống 1 viên vào buổi tối sau ăn."
                },
                {
                    "name": "Dung dịch Natri Clorid 0.9% - 1 Chai 500ml",
                    "ingredient": "NaCl 0.9% đẳng trương",
                    "category": "Dung dịch sát khuẩn vệ sinh niêm mạc",
                    "purpose": "Rửa trôi vi khuẩn bám dính, làm dịu niêm mạc họng.",
                    "usage": "Súc họng sâu 3-4 lần/ngày sau các bữa ăn và trước khi ngủ."
                }
            ],
            "warnings": [
                "[DỮ LIỆU MẪU DEMO]: Đây là đơn thuốc mẫu minh họa điều trị triệu chứng viêm đường hô hấp trên.",
                "Uống nhiều nước ấm, súc họng thường xuyên và giữ ấm vùng cổ.",
                "Nếu xuất hiện sốt cao liên tục > 39°C không hạ sau 48h hoặc khó thở, cần đến cơ sở y tế khám ngay."
            ]
        }

    elif preset_key == "lab_blood":
        return {
            "status": "demo",
            "is_demo": True,
            "type": "lab_test",
            "doc_title": "Phiếu Kết quả Xét nghiệm Sinh hóa & Huyết học (Dữ liệu Demo)",
            "facility": "Trung tâm Xét nghiệm Y khoa MediLab (DEMO)",
            "department": "Khoa Hóa sinh - Miễn dịch",
            "doctor": "BS. CKI Lê Thị Mai",
            "patient_name": "Nguyễn Thành Khiêm (Mẫu)",
            "diagnosis": "Kiểm tra sức khỏe định kỳ & Đánh giá hội chứng chuyển hóa",
            "date": today,
            "duration": "Có giá trị đối chiếu trong 3 tháng",
            "metrics": [
                {
                    "name": "Glucose (Đường huyết lúc đói)",
                    "value": "7.8",
                    "unit": "mmol/L",
                    "reference": "3.9 - 6.4",
                    "status": "High",
                    "status_label": "Vượt ngưỡng an toàn",
                    "advice": "Chỉ số đường huyết vượt ngưỡng, cần hạn chế tinh bột trắng và kiểm tra định kỳ."
                },
                {
                    "name": "Cholesterol Toàn phần",
                    "value": "5.9",
                    "unit": "mmol/L",
                    "reference": "< 5.2",
                    "status": "High",
                    "status_label": "Hơi cao",
                    "advice": "Mỡ máu toàn phần vượt ngưỡng, nên tập luyện thể dục thường xuyên."
                },
                {
                    "name": "AST / SGOT (Men gan)",
                    "value": "26",
                    "unit": "U/L",
                    "reference": "< 40",
                    "status": "Normal",
                    "status_label": "Bình thường",
                    "advice": "Men gan trong giới hạn bình thường."
                },
                {
                    "name": "Creatinine (Chức năng thận)",
                    "value": "72",
                    "unit": "µmol/L",
                    "reference": "53 - 106",
                    "status": "Normal",
                    "status_label": "Bình thường",
                    "advice": "Chức năng lọc cầu thận bình thường."
                }
            ],
            "ai_summary": "[DỮ LIỆU MẪU DEMO]: Kết quả xét nghiệm mẫu minh họa chỉ số đường huyết và mỡ máu hơi cao.",
            "lifestyle_recommendations": [
                "Tăng cường rau xanh và thực phẩm giàu chất xơ hòa tan.",
                "Tập thể dục ít nhất 30 phút mỗi ngày."
            ]
        }

    return {
        "status": "error",
        "is_demo": True,
        "message": f"Kịch bản mẫu '{preset_key}' không tồn tại. Vui lòng chọn 'binh_dan' hoặc 'lab_blood'."
    }
