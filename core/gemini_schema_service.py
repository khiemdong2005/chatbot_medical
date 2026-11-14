import os
import json
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("GeminiSchemaService")

def extract_with_gemini_schema(image_path: str, doc_type: str = "auto", api_key: str = "") -> Optional[Dict[str, Any]]:
    """
    [2.B] Gemini đọc thẳng ảnh -> JSON theo response schema chuẩn y khoa qua Unified LLM Provider:
      - Đơn thuốc: patient_name, diagnosis, medications [name, strength, dose, frequency, days, usage]
      - Xét nghiệm: metrics [test_name, result, unit, reference_range, flag_on_paper (H/L/Normal)]
    """
    from core.llm_provider import llm_provider

    if not api_key:
        api_key = llm_provider.resolve_api_key(profile="ocr")
    if not llm_provider.is_configured(profile="ocr", explicit_key=api_key):
        return None

    try:
        from google.genai import types

        with open(image_path, "rb") as f:
            file_bytes = f.read()

        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".pdf":
            mime_type = "application/pdf"

        prompt = f"""
Bạn là Hệ thống AI Chẩn đoán Y tế Lâm sàng. Hãy đọc tài liệu y khoa trong ảnh đính kèm và trích xuất dữ liệu chính xác 100%.

LOẠI TÀI LIỆU DỰ ĐOÁN HOẶC YÊU CẦU: {doc_type}

YÊU CẦU SCHEMA TRẢ VỀ:
1. Nếu là ĐƠN THUỐC (prescription):
{{
  "doc_type": "prescription",
  "patient_name": "Tên bệnh nhân hoặc để trống",
  "dob": "Ngày tháng năm sinh (ví dụ: 12/08/1982 hoặc 1982 nếu chỉ có năm sinh, hoặc để trống)",
  "age": "Tuổi bệnh nhân nếu ghi trên đơn (ví dụ: 45 hoặc để trống)",
  "gender": "Giới tính (Nam hoặc Nữ nếu có trên đơn, hoặc để trống)",
  "diagnosis": "Chẩn đoán bệnh",
  "facility": "Tên bệnh viện / phòng khám",
  "doctor": "Tên bác sĩ kê đơn",
  "date": "Ngày kê đơn",
  "medications": [
    {{
      "name": "Tên thuốc",
      "strength": "Hàm lượng (ví dụ: 500mg, 10mg)",
      "purpose": "Công dụng chính ngắn gọn (ví dụ: Hạ đường huyết, Hạ mỡ máu / Bảo vệ tim, Bổ thần kinh ngoại biên, Giảm tiết axit dạ dày, Trị co thắt dạ dày)",
      "dose": "Liều dùng mỗi lần (ví dụ: 1 viên, 2 gói)",
      "frequency": "Tần suất (ví dụ: 2 lần / ngày (Sáng 1 - Chiều 1))",
      "days": "Số ngày uống hoặc tổng số lượng (ví dụ: 60 viên (Đủ 30 ngày))",
      "usage": "Lưu ý cách dùng chi tiết (ví dụ: Uống nguyên viên ngay sau bữa ăn chính. Không bẻ, không nhai viên thuốc kéo dài)"
    }}
  ]
}}

2. Nếu là PHIẾU XÉT NGHIỆM (lab_test):
{{
  "doc_type": "lab_test",
  "patient_name": "Tên bệnh nhân hoặc để trống",
  "facility": "Tên bệnh viện / phòng khám",
  "date": "Ngày xét nghiệm",
  "metrics": [
    {{
      "test_name": "Tên chỉ số xét nghiệm (ví dụ: Glucose đói, Men gan ALT, Ure)",
      "result": "Giá trị số kết quả (ví dụ: 7.8, 42.5)",
      "unit": "Đơn vị đo (ví dụ: mmol/L, U/L, g/L)",
      "reference_range": "Khoảng tham chiếu chuẩn ghi trên phiếu (ví dụ: 3.9 - 6.4, < 40)",
      "flag_on_paper": "Cờ in trên phiếu nếu có: High / Low / Normal / Bình thường / Không có"
    }}
  ]
}}

BẮT BUỘC TRẢ VỀ DUY NHẤT 1 ĐỐI TƯỢNG JSON HỢP LỆ (KHÔNG DÙNG ```json, KHÔNG BÌNH LUẬN THÊM).
"""
        candidate_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite", "gemini-flash-latest"]
        contents = [
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            prompt
        ]
        return llm_provider.generate_json(
            contents=contents,
            candidate_models=candidate_models,
            api_key=api_key,
            operation="prescription_ocr"
        )

    except Exception as e:
        logger.warning("Gemini schema extraction failed (%s).", type(e).__name__)

    return None

