import os
import json
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("GeminiSchemaService")

def extract_with_gemini_schema(image_path: str, doc_type: str = "prescription", api_key: str = "") -> Optional[Dict[str, Any]]:
    """
    [2.B] Gemini đọc thẳng ảnh đơn thuốc -> JSON theo response schema chuẩn y khoa lâm sàng qua Unified LLM Provider:
      - Đơn thuốc: patient_name, dob, age, gender, diagnosis, facility, doctor, date, medications
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

        mime_type = "image/jpeg"
        ext = os.path.splitext(image_path)[1].lower()
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".pdf":
            mime_type = "application/pdf"

        prompt = """
Bạn là Hệ thống AI Chuyên gia Đọc & Bóc tách Đơn Thuốc Y Tế Lâm Sàng. Chỉ ghi nội dung đọc được trên ảnh; không suy đoán chẩn đoán, tên thuốc, liều dùng hay thông tin hành chính. Nếu một trường không đọc rõ, hãy để chuỗi rỗng; nếu một dòng thuốc không đủ căn cứ để xác định tên, đừng tạo dòng đó.

Với đơn thuốc: đọc ảnh theo chiều đúng trước khi tách bảng. Mỗi hàng thuốc thực sự trong phần thân phiếu là một mục medications, có hoặc không có số thứ tự; giữ đúng thứ tự trên ảnh. Phải phân biệt nhãn cột STT/Tên thuốc/Hàm lượng/Số lượng với dữ liệu của hàng. Không tạo mục riêng từ tên hoạt chất trong ngoặc, dòng cách dùng, tiêu đề, ngày tháng, mã chẩn đoán, mã hồ sơ, số lượng đứng riêng, chữ ký hoặc lời dặn. Số lượng ở cột bên phải phải được ghép với đúng dòng thuốc cùng hàng; nếu không đọc chắc, để trống. Chỉ thêm thuốc khi đọc được tên ở hàng thuốc trên ảnh, không suy từ chẩn đoán hay kiến thức y khoa. Trường patient_name chỉ là tên nằm sau nhãn "Họ tên" hoặc "Tên bệnh nhân", bỏ nhãn khỏi giá trị. Trường doctor phải là tên bác sĩ ở phần ký tên; cụm "Bác sĩ điều trị" đứng một mình là nhãn, không phải tên. Trường facility chỉ chứa tên cơ sở y tế đọc rõ ở đầu phiếu.

YÊU CẦU SCHEMA JSON TRẢ VỀ:
{
  "doc_type": "prescription",
  "patient_name": "Họ và tên bệnh nhân (viết chữ in hoa theo đơn hoặc để trống)",
  "dob": "Ngày tháng năm sinh ghi trên đơn (ví dụ: 20/11/2010 hoặc 1982 nếu chỉ có năm sinh, hoặc để trống)",
  "age": "Tuổi bệnh nhân nếu ghi rõ trên đơn (ví dụ: 40 hoặc để trống)",
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
      "days": "Số ngày uống hoặc tổng số lượng cấp phát (ví dụ: 20 viên, 10 ngày)",
      "usage": "Chỉ ghi cách dùng thực sự in trên phiếu hoặc hướng dẫn chi tiết, hoặc để trống"
    }
  ]
}

BẮT BUỘC TRẢ VỀ DUY NHẤT 1 ĐỐI TƯỢNG JSON HỢP LỆ (KHÔNG DÙNG ```json, KHÔNG BÌNH LUẬN THÊM).
"""
        # Ưu tiên model OCR được cấu hình; chỉ giữ một model dự phòng còn hỗ trợ.
        preferred_model = llm_provider.get_default_model("prescription_ocr")
        candidate_models = list(dict.fromkeys([preferred_model, "gemini-flash-latest"]))
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
