"""
core/cleanup_service.py
Dịch vụ dọn dẹp và duy trì chính sách lưu trữ tài liệu tạm (Data Retention & Maintenance) (Phase 8.3).
Chỉ xóa các bản thảo OCR chưa xác nhận và tệp tải lên tạm thời đã hết hạn.
TUYỆT ĐỐI KHÔNG XÓA HỒ SƠ Y TẾ ĐÃ XÁC NHẬN CỦA BỆNH NHÂN.
"""
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from core.models import db, MedicalDocument
from core.storage_service import is_safe_path
from core.settings import get_settings

logger = logging.getLogger("CleanupService")


def cleanup_expired_records(
    db_session=None,
    upload_dir: str = "",
    ocr_retention_hours: int = 24,
    temp_retention_hours: int = 24
) -> Dict[str, Any]:
    """
    Thực hiện dọn dẹp theo chính sách lưu trữ:
      1. Tìm và xóa các bản ghi 'ocr_draft' có created_at < cutoff.
      2. Xóa các tệp tải lên tạm thời mồ côi đã hết hạn trong thư mục uploads.
      3. Bất biến quan trọng:
         - BẢN GHI ĐÃ XÁC NHẬN (doc_type != 'ocr_draft') KHÔNG BAO GIỜ BỊ XÓA.
         - ĐƯỜNG DẪN NGOÀI UPLOAD DIRECTORY KHÔNG BAO GIỜ BỊ CHẠM TỚI.
    """
    sess = db_session or db.session
    settings = get_settings()
    base_upload_path = Path(upload_dir or settings.paths.upload_dir).resolve()

    ocr_hours = max(1, ocr_retention_hours or settings.security.ocr_draft_retention_hours)
    cutoff_time = datetime.utcnow() - timedelta(hours=ocr_hours)

    results = {
        "expired_drafts_deleted": 0,
        "orphaned_files_deleted": 0,
        "confirmed_records_preserved": 0,
        "errors": []
    }

    try:
        # Đếm hồ sơ đã xác nhận để báo cáo bảo toàn
        confirmed_count = sess.query(MedicalDocument).filter(
            MedicalDocument.doc_type != "ocr_draft"
        ).count()
        results["confirmed_records_preserved"] = confirmed_count

        # 1. Tìm các bản thảo OCR hết hạn
        expired_drafts = sess.query(MedicalDocument).filter(
            MedicalDocument.doc_type == "ocr_draft",
            MedicalDocument.created_at < cutoff_time
        ).all()

        draft_files_to_clean = []
        for draft in expired_drafts:
            if draft.storage_filename:
                draft_files_to_clean.append(draft.storage_filename)
            sess.delete(draft)
            results["expired_drafts_deleted"] += 1

        sess.commit()

        # 2. Dọn dẹp tệp tin vật lý gắn liền với draft bị xóa (nếu an toàn và nằm trong uploads)
        for fname in draft_files_to_clean:
            target_path = base_upload_path / fname
            if is_safe_path(target_path, base_upload_path) and target_path.is_file():
                try:
                    os.remove(target_path)
                    results["orphaned_files_deleted"] += 1
                except Exception as e:
                    results["errors"].append(f"Không thể xóa file tạm {fname}: {e}")

    except Exception as e:
        sess.rollback()
        logger.error("Lỗi trong quá trình dọn dẹp dữ liệu tạm: %s", e)
        results["errors"].append(str(e))

    return results
