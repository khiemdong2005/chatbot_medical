import os
import json
import re
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

def extract_with_gemini_schema(image_path: str, doc_type: str = "auto", api_key: str = "") -> Optional[Dict[str, Any]]:
    """
    [2.B] Gemini đọc thẳng ảnh -> JSON theo response schema chuẩn y khoa:
      - Đơn thuốc: patient_name, diagnosis, medications [name, strength, dose, frequency, days, usage]
      - Xét nghiệm: metrics [test_name, result, unit, reference_range, flag_on_paper (H/L/Normal)]
    """
    if not api_key:
        api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return None

    try:
        client = genai.Client(api_key=api_key)

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
  "dob": "Ngày sinh hoặc tuổi",
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
        candidate_models = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-flash-latest"]
        for model in candidate_models:
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                        prompt
                    ]
                )
                if res and res.text:
                    cleaned = res.text.strip()
                    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
                    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
                    if match:
                        cleaned = match.group(1).strip()
                    return json.loads(cleaned)
            except Exception as me:
                print(f"[GEMINI SCHEMA MODEL FAIL {model}] {me}")
                continue

    except Exception as e:
        print(f"[GEMINI SCHEMA EXTRACTION ERROR] {e}")

    return None

