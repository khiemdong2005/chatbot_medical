import os
import re
from abc import ABC, abstractmethod
from typing import Dict, Type

class DocumentExtractor(ABC):
    """
    Interface trừu tượng (Abstract Base Class) cho tất cả các bộ trích xuất văn bản tài liệu.
    Tuân thủ nguyên tắc Open/Closed Principle (OCP) và Single Responsibility (SRP).
    """

    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """
        Trích xuất toàn bộ nội dung văn bản thô từ tệp tài liệu.

        :param file_path: Đường dẫn tuyệt đối hoặc tương đối tới tệp.
        :return: Chuỗi văn bản thô trích xuất được.
        :raises FileNotFoundError: Khi tệp không tồn tại.
        :raises RuntimeError: Khi quá trình giải mã tệp thất bại.
        """
        pass


class DocxExtractor(DocumentExtractor):
    """
    Bộ trích xuất văn bản từ tệp Microsoft Word (.docx).
    Bóc tách cả các đoạn văn bản (paragraphs) và dữ liệu trong các bảng biểu (tables).
    """

    def extract_text(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Tệp không tồn tại: {file_path}")

        try:
            import docx
        except ImportError:
            raise ImportError(
                "Thư viện 'python-docx' chưa được cài đặt. Vui lòng chạy: pip install python-docx"
            )

        try:
            doc = docx.Document(file_path)
            extracted_lines = []

            # 1. Trích xuất văn bản từ các đoạn (paragraphs)
            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if text:
                    extracted_lines.append(text)

            # 2. Trích xuất văn bản từ các bảng (tables - đơn thuốc rất hay dùng bảng)
            for table in doc.tables:
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_data:
                        extracted_lines.append(" | ".join(row_data))

            return "\n".join(extracted_lines)
        except Exception as e:
            raise RuntimeError(f"Lỗi khi trích xuất tệp DOCX '{file_path}': {str(e)}") from e


class PdfExtractor(DocumentExtractor):
    """
    Bộ trích xuất văn bản từ tệp PDF sạch (vector/text PDF, có thể copy text).
    Ưu tiên sử dụng PyMuPDF (fitz) vì tốc độ C-native vượt trội, fallback sang pdfplumber.
    """

    def extract_text(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Tệp không tồn tại: {file_path}")

        # Thử nghiệm PyMuPDF (fitz) trước
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            pages_text = []
            for page_index in range(len(doc)):
                page = doc[page_index]
                text = page.get_text("text")
                if text.strip():
                    pages_text.append(text.strip())
            doc.close()
            return "\n".join(pages_text)
        except ImportError:
            pass

        # Fallback sang pdfplumber nếu PyMuPDF không có sẵn
        try:
            import pdfplumber
            pages_text = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text and text.strip():
                        pages_text.append(text.strip())
            return "\n".join(pages_text)
        except ImportError:
            raise ImportError(
                "Cần cài đặt ít nhất một thư viện PDF: 'pymupdf' hoặc 'pdfplumber'. "
                "Khuyến nghị chạy: pip install pymupdf"
            )
        except Exception as e:
            raise RuntimeError(f"Lỗi khi trích xuất tệp PDF '{file_path}': {str(e)}") from e


class ImageExtractor(DocumentExtractor):
    """
    [LƯU Ý CHO TƯƠNG LAI - GIAI ĐOẠN 2]
    Bộ trích xuất văn bản từ ảnh chụp / scan đơn thuốc (JPG, PNG, TIFF) sử dụng OCR / VLM.
    Dự kiến tích hợp: Tesseract OCR, PaddleOCR hoặc Multimodal Vision AI (GPT-4o Vision / Gemini Flash).
    """

    def extract_text(self, file_path: str) -> str:
        raise NotImplementedError(
            f"Tính năng đọc đơn thuốc từ ảnh chụp cho tệp '{file_path}' thuộc Giai đoạn 2 "
            "(đang được phát triển với OCR / Vision AI)."
        )


# ==============================================================================
# FACTORY / REGISTRY ROUTER
# ==============================================================================

EXTRACTOR_REGISTRY: Dict[str, Type[DocumentExtractor]] = {
    ".docx": DocxExtractor,
    ".pdf": PdfExtractor,
    # Giai đoạn 2: Kích hoạt khi hoàn thiện OCR
    ".png": ImageExtractor,
    ".jpg": ImageExtractor,
    ".jpeg": ImageExtractor,
}

def get_extractor(file_path: str) -> DocumentExtractor:
    """
    Factory function tự động phát hiện định dạng tệp và khởi tạo Extractor phù hợp.

    :param file_path: Đường dẫn tới tệp tài liệu.
    :return: Thể hiện cụ thể của DocumentExtractor.
    :raises ValueError: Nếu định dạng tệp không được hỗ trợ hoặc thiếu phần mở rộng.
    """
    if not file_path:
        raise ValueError("Đường dẫn tệp không được để trống.")

    _, ext = os.path.splitext(file_path)
    normalized_ext = ext.lower().strip()

    if not normalized_ext:
        raise ValueError(f"Không xác định được định dạng (thiếu phần mở rộng): '{file_path}'")

    extractor_cls = EXTRACTOR_REGISTRY.get(normalized_ext)
    if not extractor_cls:
        supported = ", ".join(EXTRACTOR_REGISTRY.keys())
        raise ValueError(
            f"Định dạng tệp '{normalized_ext}' không được hỗ trợ. "
            f"Các định dạng được hỗ trợ hiện tại: {supported}"
        )

    return extractor_cls()
