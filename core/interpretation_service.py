import os
import json
import re
from typing import Dict, Any
from google import genai

def generate_clinical_interpretation(validated_data: Dict[str, Any], api_key: str = "") -> Dict[str, Any]:
    """
    [6] Diễn giải (Gemini, CHỈ NHẬN JSON ĐÃ VALIDATE):
      - Giải thích đơn giản cho người dùng, tuyệt đối không tự thêm số liệu mới.
      - Gắn disclaimer rõ ràng.
      - Field needs_review=True hiển thị "vui lòng kiểm tra lại với đơn gốc".
    """
    if not api_key:
        api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

    doc_type = validated_data.get("doc_type", "prescription")
    clean_payload = {
        "doc_type": doc_type,
        "facility": validated_data.get("facility", ""),
        "diagnosis": validated_data.get("diagnosis", ""),
        "items": validated_data.get("medications") if doc_type == "prescription" else validated_data.get("metrics"),
        "alerts": validated_data.get("clinical_alerts", []),
        "review_needed_items": [
            x.get("name") or x.get("test_name")
            for x in (validated_data.get("medications") or validated_data.get("metrics") or [])
            if x.get("needs_review")
        ]
    }

    prompt = f"""
Bạn là Trợ lý Y tế MediMind. Hãy đọc bản dữ liệu JSON đã được hệ thống kiểm duyệt kỹ thuật dưới đây và viết phần diễn giải thân thiện, dễ hiểu cho người bệnh:

{json.dumps(clean_payload, ensure_ascii=False, indent=2)}

NGUYÊN TẮC NGHIÊM NGẶT:
1. KHÔNG tự bịa hoặc thêm bất kỳ con số, liều dùng hay chỉ số nào ngoài dữ liệu đã cung cấp.
2. Với các mục có cờ cảnh báo hoặc nằm trong 'review_needed_items', PHẢI ghi rõ: "[CẦN ĐỐI CHIẾU] Vui lòng kiểm tra lại số liệu trực tiếp với đơn/phiếu gốc trước khi dùng".
3. Diễn giải mục đích các nhóm thuốc hoặc ý nghĩa của chỉ số bất thường một cách dễ hiểu và khoa học.
4. BẮT BUỘC có lời khuyên chăm sóc sức khỏe phù hợp và TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM Y TẾ.

Trả về kết quả dưới dạng Markdown có cấu trúc (gồm các tiêu đề: ### 1. Tóm tắt nhanh, ### 2. Hướng dẫn sử dụng & Lưu ý quan trọng, ### 3. Khuyến nghị lối sống).
"""

    if not api_key:
        return {
            "interpretation_md": "### Tóm tắt tài liệu y tế\nKết quả đã được trích xuất an toàn. Vui lòng đối chiếu với bản gốc.",
            "disclaimer": "Lưu ý: MediMind AI là hệ thống sàng lọc tham khảo, không thay thế chẩn đoán của bác sĩ."
        }

    try:
        client = genai.Client(api_key=api_key)
        candidate_models = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-flash-latest"]
        for model in candidate_models:
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                if res and res.text:
                    return {
                        "interpretation_md": res.text.strip(),
                        "disclaimer": "CẢNH BÁO: Thông tin trên mang tính chất hỗ trợ tra cứu và theo dõi tuân thủ điều trị. Bệnh nhân không tự ý thay đổi liều hoặc ngừng thuốc khi chưa có chỉ định của Bác sĩ."
                    }
            except Exception:
                continue
    except Exception as e:
        print(f"[INTERPRETATION ERROR] {e}")

    return {
        "interpretation_md": "### Tóm tắt kết quả\nQuá trình trích xuất và chuẩn hóa hoàn tất. Vui lòng kiểm tra kỹ các thông tin trước khi xác nhận.",
        "disclaimer": "Lưu ý: Không thay thế thăm khám chuyên khoa trực tiếp."
    }

