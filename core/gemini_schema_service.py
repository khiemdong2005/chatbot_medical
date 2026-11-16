import os
import json
import re
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

def extract_with_gemini_schema(image_path: str, doc_type: str = "prescription", api_key: str = "") -> Optional[Dict[str, Any]]:
    """
    [2.B] Gemini đọc thẳng ảnh đơn thuốc -> JSON theo response schema chuẩn y khoa lâm sàng:
      - Đơn thuốc: patient_name, dob, age, gender, diagnosis, facility, doctor, date, medications
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

        prompt = """
Bạn là Hệ thống AI Chuyên gia Đọc & Bóc tách Đơn Thuốc Y Tế Lâm Sàng. Hãy đọc toàn bộ thông tin trên đơn thuốc trong hình ảnh đính kèm và trích xuất dữ liệu chính xác 100%.

YÊU CẦU SCHEMA JSON TRẢ VỀ:
{
  "doc_type": "prescription",
  "patient_name": "Họ và tên bệnh nhân (viết chữ in hoa theo đơn hoặc để trống)",
  "dob": "Ngày tháng năm sinh ghi trên đơn (ví dụ: 20/11/2010 hoặc 1982 nếu chỉ có năm sinh, hoặc để trống)",
  "age": "Tuổi bệnh nhân nếu ghi rõ trên đơn (ví dụ: 45 hoặc để trống nếu đơn chỉ ghi ngày sinh)",
  "gender": "Giới tính (Nam hoặc Nữ nếu có trên đơn, hoặc để trống)",
  "diagnosis": "Chẩn đoán bệnh (ghi đầy đủ tên bệnh và mã ICD nếu có trên đơn)",
  "facility": "Tên bệnh viện hoặc phòng khám",
  "doctor": "Tên bác sĩ kê đơn",
  "date": "Ngày kê đơn",
  "medications": [
    {
      "name": "Tên biệt dược hoặc hoạt chất thuốc",
      "strength": "Hàm lượng (ví dụ: 500mg, 40mg, 1g, 200mg)",
      "purpose": "Công dụng chính ngắn gọn (ví dụ: Giảm tiết acid dạ dày, Trị trào ngược dạ dày, Bảo vệ niêm mạc, Giảm co thắt, Bổ gan)",
      "dose": "Liều dùng mỗi lần (ví dụ: 1 viên, 1 gói, 1 ống)",
      "frequency": "Tần suất uống trong ngày (ví dụ: 2 lần / ngày (Sáng 1 - Chiều 1))",
      "days": "Số ngày uống hoặc tổng số lượng (ví dụ: 60 viên (Đủ 30 ngày))",
      "usage": "Lưu ý và hướng dẫn cách dùng chi tiết (ví dụ: Uống trước bữa ăn 30 phút. Không bẻ, không nhai viên thuốc giải phóng chậm)"
    }
  ]
}

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

