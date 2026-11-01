import os
import uuid
import base64
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf", "docx", "doc"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_BASE64_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

# Magic bytes signatures for file format verification
FILE_SIGNATURES = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"]
}


def is_safe_path(target_path: Path, base_dir: Path) -> bool:
    """
    Kiểm tra phòng thủ chống Path Traversal:
    Đảm bảo đường dẫn đích hoàn toàn nằm trong thư mục gốc được phép.
    """
    try:
        resolved_target = Path(target_path).resolve()
        resolved_base = Path(base_dir).resolve()
        return resolved_target.is_relative_to(resolved_base)
    except Exception:
        return False


def validate_file_content(file_bytes: bytes, declared_ext: str) -> bool:
    """
    Kiểm tra magic bytes để ngăn chặn kỹ thuật giả mạo đuôi file (File extension spoofing).
    """
    ext = declared_ext.lower()
    if ext not in FILE_SIGNATURES:
        return False

    signatures = FILE_SIGNATURES[ext]
    return any(file_bytes.startswith(sig) for sig in signatures)


def process_secure_upload(file_obj, upload_folder: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Xử lý tệp tải lên với tiêu chuẩn bảo mật y tế:
      1. Kiểm tra tên tệp & loại bỏ ký tự nguy hiểm
      2. Kiểm tra phần mở rộng nằm trong danh sách cho phép
      3. Kiểm tra kích thước tệp (tối đa 10MB)
      4. Kiểm tra magic bytes thực tế
      5. Tạo tên tệp ngẫu nhiên (UUID) để tránh ghi đè và ẩn danh hóa
      6. Lưu tệp an toàn và chống path traversal
    
    Returns:
      (success: bool, metadata: dict, error_message: str | None)
    """
    if not file_obj or not file_obj.filename:
        return False, {}, "Chưa chọn tệp hoặc tệp không hợp lệ."

    original_name = os.path.basename(file_obj.filename).strip()
    safe_client_name = secure_filename(original_name)
    if not safe_client_name:
        safe_client_name = f"upload_{uuid.uuid4().hex[:8]}.png"

    if "." not in safe_client_name:
        return False, {}, "Tệp không có phần mở rộng hợp lệ."

    ext = safe_client_name.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, {}, f"Định dạng '.{ext}' không được hỗ trợ. Vui lòng chọn JPG, PNG, PDF hoặc DOCX."

    # Đọc nội dung để kiểm tra kích thước và chữ ký nhị phân
    file_bytes = file_obj.read()
    if len(file_bytes) == 0:
        return False, {}, "Tệp tải lên rỗng (0 bytes)."

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, {}, f"Dung lượng tệp ({len(file_bytes) / (1024*1024):.1f} MB) vượt quá giới hạn cho phép (10 MB)."

    if not validate_file_content(file_bytes, ext):
        return False, {}, f"Nội dung tệp không khớp với định dạng .{ext} được khai báo."

    # Sinh tên lưu trữ ngẫu nhiên (UUID) để tránh trùng tên và chống tấn công đoán tên tệp
    random_filename = f"{uuid.uuid4().hex}.{ext}"
    base_folder_path = Path(upload_folder).resolve()
    base_folder_path.mkdir(parents=True, exist_ok=True)

    dest_path = base_folder_path / random_filename
    if not is_safe_path(dest_path, base_folder_path):
        return False, {}, "Phát hiện đường dẫn không an toàn (Path Traversal)."

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    metadata = {
        "storage_filename": random_filename,
        "original_filename": original_name,
        "file_path": str(dest_path.relative_to(base_folder_path)),
        "absolute_path": str(dest_path),
        "file_size": len(file_bytes),
        "file_type": ext.upper(),
        "mime_type": f"image/{ext}" if ext in ["jpg", "jpeg", "png"] else f"application/{ext}"
    }

    return True, metadata, None


def decode_and_validate_base64_image(image_str: str) -> Tuple[Optional[bytes], str, Optional[str]]:
    """
    Giải mã chuỗi Base64 ảnh và kiểm tra độ an toàn:
      1. Kiểm tra kích thước chuỗi
      2. Tách MIME header
      3. Giải mã và kiểm tra dung lượng bytes thực tế
      4. Kiểm tra magic bytes ảnh (PNG/JPEG/WEBP/GIF)
    
    Returns:
      (image_bytes, mime_type, error_message)
    """
    if not image_str:
        return None, "image/jpeg", None

    # Giới hạn độ dài chuỗi base64 thô
    if len(image_str) > (MAX_BASE64_IMAGE_BYTES * 4 // 3 + 1024):
        return None, "image/jpeg", "Dung lượng ảnh vượt quá giới hạn cho phép (5 MB)."

    mime_type = "image/jpeg"
    b64_data = image_str

    if "," in image_str:
        header, b64_data = image_str.split(",", 1)
        if "image/png" in header:
            mime_type = "image/png"
        elif "image/webp" in header:
            mime_type = "image/webp"
        elif "image/gif" in header:
            mime_type = "image/gif"
        elif "image/jpeg" in header or "image/jpg" in header:
            mime_type = "image/jpeg"

    try:
        img_bytes = base64.b64decode(b64_data, validate=True)
    except Exception as e:
        return None, mime_type, f"Định dạng Base64 không hợp lệ: {e}"

    if len(img_bytes) > MAX_BASE64_IMAGE_BYTES:
        return None, mime_type, "Dung lượng ảnh vượt quá giới hạn 5 MB."

    # Kiểm tra signature nhị phân
    is_valid_image = (
        img_bytes.startswith(b"\xff\xd8\xff") or  # JPEG
        img_bytes.startswith(b"\x89PNG\r\n\x1a\n") or  # PNG
        img_bytes.startswith(b"RIFF") or  # WEBP
        img_bytes.startswith(b"GIF87a") or img_bytes.startswith(b"GIF89a")  # GIF
    )
    if not is_valid_image:
        return None, mime_type, "Dữ liệu ảnh không hợp lệ hoặc bị hỏng."

    return img_bytes, mime_type, None

