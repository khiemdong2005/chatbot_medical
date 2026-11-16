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
Bạn là hệ thống trích xuất thông tin từ ảnh tài liệu y tế. Chỉ ghi nội dung đọc được trên ảnh; không suy đoán chẩn đoán, tên thuốc, liều dùng hay thông tin hành chính. Nếu một trường không đọc rõ, hãy để chuỗi rỗng; nếu một dòng thuốc không đủ căn cứ để xác định tên, đừng tạo dòng đó.

LOẠI TÀI LIỆU DỰ ĐOÁN HOẶC YÊU CẦU: {doc_type}

Với đơn thuốc: đọc ảnh theo chiều đúng trước khi tách bảng. Mỗi hàng thuốc thực sự trong phần thân phiếu là một mục medications, có hoặc không có số thứ tự; giữ đúng thứ tự trên ảnh. Phải phân biệt nhãn cột STT/Tên thuốc/Hàm lượng/Số lượng với dữ liệu của hàng. Không tạo mục riêng từ tên hoạt chất trong ngoặc, dòng cách dùng, tiêu đề, ngày tháng, mã chẩn đoán, mã hồ sơ, số lượng đứng riêng, chữ ký hoặc lời dặn. Số lượng ở cột bên phải phải được ghép với đúng dòng thuốc cùng hàng; nếu không đọc chắc, để trống. Chỉ thêm thuốc khi đọc được tên ở hàng thuốc trên ảnh, không suy từ chẩn đoán hay kiến thức y khoa. Trường patient_name chỉ là tên nằm sau nhãn "Họ tên" hoặc "Tên bệnh nhân", bỏ nhãn khỏi giá trị. Trường doctor phải là tên bác sĩ ở phần ký tên; cụm "Bác sĩ điều trị" đứng một mình là nhãn, không phải tên. Trường facility chỉ chứa tên cơ sở y tế đọc rõ ở đầu phiếu, không lấy chuỗi OCR vô nghĩa hoặc tên thuốc. Phân biệt "liều mỗi lần" với tổng số lượng cấp phát. Không tự điền liều, tần suất hay cách dùng mặc định.

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
      "dose": "Liều dùng mỗi lần (ví dụ: 1 viên, 2 gói)",
      "frequency": "Tần suất (ví dụ: 2 lần / ngày (Sáng 1 - Chiều 1))",
      "days": "Số ngày hoặc tổng số lượng cấp phát ghi trên đúng dòng thuốc; giữ nguyên đơn vị, không quy đổi hay suy tính",
      "usage": "Chỉ ghi cách dùng thực sự in trên phiếu, hoặc để trống"
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
        # Ưu tiên model OCR được cấu hình; chỉ giữ một model dự phòng còn hỗ trợ.
        # Các model 1.5/2.0 cũ khiến mỗi lần scan lỗi phải chờ thêm nhiều request.
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

