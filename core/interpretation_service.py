import os
import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger("InterpretationService")

def generate_clinical_interpretation(validated_data: Dict[str, Any], api_key: str = "") -> Dict[str, Any]:
    """
    Diễn giải qua Groq Unified LLM Provider (chỉ nhận JSON đã validate):
      - Giải thích đơn giản cho người dùng, tuyệt đối không tự thêm số liệu mới.
      - Gắn disclaimer rõ ràng.
      - Field needs_review=True hiển thị "vui lòng kiểm tra lại với đơn gốc".
    """
    from core.llm_provider import llm_provider

    if not api_key:
        api_key = llm_provider.resolve_api_key(profile="interpretation")

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
        candidate_models = [llm_provider.get_default_model("interpretation")]
        res_text = llm_provider.generate_text(
            prompt=prompt,
            candidate_models=candidate_models,
            api_key=api_key,
            operation="interpretation"
        )
        if res_text and res_text.strip():
            return {
                "interpretation_md": res_text.strip(),
                "disclaimer": "CẢNH BÁO: Thông tin trên mang tính chất hỗ trợ tra cứu và theo dõi tuân thủ điều trị. Bệnh nhân không tự ý thay đổi liều hoặc ngừng thuốc khi chưa có chỉ định của Bác sĩ."
            }
    except Exception as e:
        logger.warning("Clinical interpretation call failed (%s).", type(e).__name__)

    return {
        "interpretation_md": "### Tóm tắt kết quả\nQuá trình trích xuất và chuẩn hóa hoàn tất. Vui lòng kiểm tra kỹ các thông tin trước khi xác nhận.",
        "disclaimer": "Lưu ý: Không thay thế thăm khám chuyên khoa trực tiếp."
    }

