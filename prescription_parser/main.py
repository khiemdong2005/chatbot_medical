import os
import sys
import json
import logging
from typing import Dict, Any, Optional

from prescription_parser.extractors import get_extractor, DocumentExtractor
from prescription_parser.pipeline import clean_text, extract_prescription_data

# Thiết lập hệ thống ghi log chuẩn
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PrescriptionParser")


def process_prescription(file_path: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Hàm điều phối trung tâm (Entry Point) của toàn bộ hệ thống đọc đơn thuốc:
    1. Chọn Extractor tương ứng theo định dạng tệp.
    2. Trích xuất nội dung văn bản thô từ tài liệu.
    3. Làm sạch văn bản (loại bỏ ký tự rác, chuẩn hóa dòng).
    4. Gọi LLM để phân tích và bóc tách thực thể y tế thành JSON.
    5. Xử lý triệt để các ngoại lệ phát sinh để đảm bảo hệ thống không bị crash.

    :param file_path: Đường dẫn tệp đơn thuốc (.pdf hoặc .docx).
    :param api_key: OpenAI API Key (tùy chọn).
    :return: Dictionary chứa dữ liệu đơn thuốc có cấu trúc chuẩn.
    :raises FileNotFoundError: Khi không tìm thấy tệp.
    :raises ValueError: Khi định dạng tệp không được hỗ trợ hoặc nội dung trống.
    :raises RuntimeError: Khi có lỗi trong quá trình bóc tách hoặc gọi LLM.
    """
    logger.info(f"Bắt đầu xử lý đơn thuốc từ tệp: '{file_path}'")

    # 1. Kiểm tra sự tồn tại của tệp
    if not os.path.exists(file_path):
        err_msg = f"Tệp không tồn tại: {file_path}"
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    # 2. Điều hướng Extractor phù hợp qua Factory
    try:
        extractor: DocumentExtractor = get_extractor(file_path)
        logger.info(f"Đã kích hoạt Extractor: {extractor.__class__.__name__}")
    except ValueError as ve:
        logger.error(f"Lỗi xác thực định dạng tệp: {ve}")
        raise

    # 3. Trích xuất văn bản thô
    try:
        raw_text = extractor.extract_text(file_path)
        logger.info(f"Trích xuất thô thành công ({len(raw_text)} ký tự).")
    except Exception as ee:
        logger.error(f"Thất bại trong quá trình bóc tách văn bản: {ee}")
        raise RuntimeError(f"Lỗi bóc tách tài liệu: {str(ee)}") from ee

    if not raw_text.strip():
        logger.warning("Văn bản trích xuất được rỗng hoặc không có nội dung chữ.")
        return {
            "status": "warning",
            "message": "Không tìm thấy nội dung văn bản trong tài liệu.",
            "patient_info": {"name": "", "age": ""},
            "medications": []
        }

    # 4. Làm sạch văn bản (Text Pipeline)
    cleaned_text = clean_text(raw_text)
    logger.info(f"Làm sạch văn bản hoàn tất (còn {len(cleaned_text)} ký tự chuẩn hóa).")

    # 5. Gọi LLM trích xuất dữ liệu có cấu trúc
    try:
        prescription_data = extract_prescription_data(cleaned_text, api_key=api_key)
        logger.info("Trích xuất thực thể y tế qua LLM thành công.")
        return prescription_data
    except Exception as le:
        logger.error(f"Thất bại tại tầng LLM / Parse JSON: {le}")
        raise RuntimeError(f"Lỗi xử lý LLM: {str(le)}") from le


# ==============================================================================
# CLI EXECUTION ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nCách sử dụng: python -m prescription_parser.main <duong_dan_tep_don_thuoc>")
        print("Ví dụ: python -m prescription_parser.main sample_prescription.pdf\n")
        sys.exit(1)

    target_file = sys.argv[1]
    try:
        result = process_prescription(target_file)
        print("\n" + "=" * 50)
        print("KẾT QUẢ TRÍCH XUẤT ĐƠN THUỐC (JSON OUTPUT):")
        print("=" * 50)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"\n[LỖI]: {e}\n", file=sys.stderr)
        sys.exit(1)
