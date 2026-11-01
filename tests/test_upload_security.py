import io
import pytest
from pathlib import Path
from core.models import db, MedicalDocument
from core.storage_service import (
    process_secure_upload,
    decode_and_validate_base64_image,
    is_safe_path
)


def test_filename_traversal_is_blocked(temp_dirs):
    """Kiểm thử 3a: Chặn đứng tấn công Path Traversal qua tên file."""
    uploads_dir = temp_dirs["uploads"]
    
    # Giả lập file có tên chứa path traversal
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    file_obj = io.BytesIO(png_bytes)
    file_obj.filename = "../../../etc/passwd.png"

    success, meta, err = process_secure_upload(file_obj, str(uploads_dir))
    assert success is True
    # Tên lưu trữ trên đĩa phải là UUID ngẫu nhiên nằm trong uploads_dir, không thể nhảy ra ngoài
    saved_path = Path(meta["absolute_path"])
    assert saved_path.is_relative_to(uploads_dir)
    assert "passwd" not in saved_path.name
    assert is_safe_path(saved_path, uploads_dir) is True


def test_invalid_file_extension_rejected(temp_dirs):
    """Kiểm thử 3b: Từ chối các định dạng file không được phép (.exe, .php, .sh)."""
    uploads_dir = temp_dirs["uploads"]

    for dangerous_ext in ["malware.exe", "shell.php", "script.sh", "payload.py"]:
        file_obj = io.BytesIO(b"executable or script code")
        file_obj.filename = dangerous_ext
        success, meta, err = process_secure_upload(file_obj, str(uploads_dir))
        assert success is False
        assert "không được hỗ trợ" in err


def test_oversized_file_rejected(temp_dirs):
    """Kiểm thử 3c: Từ chối tệp quá dung lượng tối đa (10MB)."""
    uploads_dir = temp_dirs["uploads"]
    
    # 11MB file with PNG header
    oversized_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)
    file_obj = io.BytesIO(oversized_bytes)
    file_obj.filename = "huge_scan.png"

    success, meta, err = process_secure_upload(file_obj, str(uploads_dir))
    assert success is False
    assert "vượt quá giới hạn" in err


def test_duplicate_filenames_do_not_overwrite(temp_dirs):
    """Kiểm thử 3d: Hai tệp trùng tên gốc không được ghi đè lên nhau."""
    uploads_dir = temp_dirs["uploads"]

    png_bytes_1 = b"\x89PNG\r\n\x1a\n" + b"file_version_1"
    png_bytes_2 = b"\x89PNG\r\n\x1a\n" + b"file_version_2"

    file_1 = io.BytesIO(png_bytes_1)
    file_1.filename = "don_thuoc.png"
    success_1, meta_1, err_1 = process_secure_upload(file_1, str(uploads_dir))
    assert success_1 is True

    file_2 = io.BytesIO(png_bytes_2)
    file_2.filename = "don_thuoc.png"
    success_2, meta_2, err_2 = process_secure_upload(file_2, str(uploads_dir))
    assert success_2 is True

    # Phải sinh 2 tên lưu trữ khác nhau hoàn toàn
    assert meta_1["storage_filename"] != meta_2["storage_filename"]
    
    # Cả hai tệp đều tồn tại độc lập trên đĩa và giữ nguyên nội dung
    with open(meta_1["absolute_path"], "rb") as f1:
        assert b"file_version_1" in f1.read()
    with open(meta_2["absolute_path"], "rb") as f2:
        assert b"file_version_2" in f2.read()


def test_corrupt_or_oversized_base64_image():
    """Kiểm thử 3e: Xử lý chuỗi Base64 ảnh hỏng hoặc quá lớn an toàn."""
    # Base64 hỏng
    img_bytes, mime, err = decode_and_validate_base64_image("invalid_base64_!!!")
    assert err is not None

    # Base64 không phải là ảnh (chỉ là chuỗi text mã hóa)
    import base64
    text_b64 = base64.b64encode(b"This is just plain text, not an image").decode()
    img_bytes, mime, err = decode_and_validate_base64_image(f"data:image/png;base64,{text_b64}")
    assert err is not None
    assert "không hợp lệ" in err

