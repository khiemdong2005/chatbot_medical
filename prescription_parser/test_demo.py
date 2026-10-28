import os
import sys
import json

# Đảm bảo import được module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from prescription_parser.extractors import get_extractor, DocxExtractor, PdfExtractor, ImageExtractor
from prescription_parser.pipeline import clean_text, extract_prescription_data, _parse_llm_json_response
from prescription_parser.main import process_prescription

def run_all_tests():
    print("=" * 65)
    print("🧪 BẮT ĐẦU CHẠY KIỂM THỬ MODULE ĐỌC ĐƠN THUỐC (PRESCRIPTION PARSER)")
    print("=" * 65)

    # --------------------------------------------------------------------------
    # TEST 1: Kiểm thử Factory / Router get_extractor
    # --------------------------------------------------------------------------
    print("\n[TEST 1] Kiểm tra Factory Router (get_extractor):")
    docx_ext = get_extractor("don_thuoc_mau.docx")
    assert isinstance(docx_ext, DocxExtractor), "Lỗi: Không trả về DocxExtractor!"
    print("  ✓ docx -> DocxExtractor: ĐẠT")

    pdf_ext = get_extractor("don_thuoc_benh_vien.pdf")
    assert isinstance(pdf_ext, PdfExtractor), "Lỗi: Không trả về PdfExtractor!"
    print("  ✓ pdf -> PdfExtractor: ĐẠT")

    img_ext = get_extractor("don_thuoc_chup.png")
    assert isinstance(img_ext, ImageExtractor), "Lỗi: Không trả về ImageExtractor!"
    try:
        img_ext.extract_text("don_thuoc_chup.png")
    except NotImplementedError as e:
        print(f"  ✓ png -> ImageExtractor (Hook Giai đoạn 2): ĐẠT ({e})")

    try:
        get_extractor("virus.exe")
        assert False, "Lỗi: Đuôi file lạ không ném ra ValueError!"
    except ValueError:
        print("  ✓ file lạ (.exe) -> Chặn lỗi an toàn (ValueError): ĐẠT")

    # --------------------------------------------------------------------------
    # TEST 2: Kiểm thử hàm làm sạch Text (clean_text)
    # --------------------------------------------------------------------------
    print("\n[TEST 2] Kiểm tra Text Cleaning Pipeline (clean_text):")
    dirty_text = """
    BỆNH VIỆN BẠCH MAI                  Trang 1 / 2
    ================================================
    Họ và tên: Trần Thị B                Tuổi: 42
    
    
    
    Ngày in: 26/10/2026 09:30:00
    1. Augmentin 625mg          Uống 2 viên / ngày
    2. Paracetamol 500mg       Uống khi sốt > 38.5 độ
    ------------------------------------------------
    Page 2 of 2
    """
    cleaned = clean_text(dirty_text)
    assert "Trang 1 / 2" not in cleaned, "Lỗi: Chưa xóa Header Trang 1/2!"
    assert "Page 2 of 2" not in cleaned, "Lỗi: Chưa xóa Footer Page 2 of 2!"
    assert "Ngày in" not in cleaned, "Lỗi: Chưa xóa Ngày in!"
    assert "=====" not in cleaned, "Lỗi: Chưa xóa dải gạch phân cách!"
    print("  ✓ Đã loại bỏ hoàn toàn Header, Footer, Timestamp rác và gạch phân cách.")
    print("  ✓ Văn bản sau làm sạch:\n" + "-" * 40)
    print(cleaned)
    print("-" * 40)

    # --------------------------------------------------------------------------
    # TEST 3: Kiểm thử Phòng thủ JSON Parser (_parse_llm_json_response)
    # --------------------------------------------------------------------------
    print("\n[TEST 3] Kiểm tra Bộ phân tích cú pháp JSON phòng thủ (Defensive Parser):")
    # Tình huống LLM bọc trong Markdown code block
    llm_markdown_output = """```json
    {
      "patient_info": {"name": "Lê Công Luyến", "age": "21"},
      "medications": [
        {"name": "Augmentin", "dosage": "625mg", "frequency": "2 lần / ngày", "instruction": "Uống sau ăn no"}
      ]
    }
    ```"""
    parsed = _parse_llm_json_response(llm_markdown_output)
    assert parsed["patient_info"]["name"] == "Lê Công Luyến"
    print("  ✓ Xử lý mượt mà chuỗi Markdown code block (```json ... ```): ĐẠT")

    # Tình huống LLM trả lời kèm câu chào rườm rà phía trước và sau
    llm_chatty_output = """Dưới đây là thông tin đơn thuốc của bạn:
    {"patient_info": {"name": "Nguyễn Văn An", "age": "34"}, "medications": []}
    Hy vọng giúp ích cho bạn!"""
    parsed_chatty = _parse_llm_json_response(llm_chatty_output)
    assert parsed_chatty["patient_info"]["name"] == "Nguyễn Văn An"
    print("  ✓ Tự động lọc bỏ lời thoại rườm rà của LLM qua Regex: ĐẠT")

    # --------------------------------------------------------------------------
    # TEST 4: Kiểm thử End-to-End Trích xuất Dữ liệu Đơn thuốc
    # --------------------------------------------------------------------------
    print("\n[TEST 4] Kiểm thử End-to-End trích xuất đơn thuốc:")
    result = extract_prescription_data(cleaned)
    print("  ✓ Kết quả JSON thu được:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    assert "patient_info" in result
    assert "medications" in result
    print("  ✓ Schema JSON đảm bảo đầy đủ 'patient_info' và 'medications': ĐẠT")

    print("\n" + "=" * 65)
    print("🎉 TẤT CẢ 4/4 BỘ TEST CASE ĐÃ HOÀN TOÀN VƯỢT QUA (100% PASS)!")
    print("=" * 65)

if __name__ == "__main__":
    run_all_tests()
