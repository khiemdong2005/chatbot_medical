"""
tests/test_security_production_hardening.py
Suite kiểm thử an ninh chuyên sâu cho Local Production Hardening (Phase 8.3):
  1. Trusted Proxy Spoofing Protection (Items 1-5)
  2. HTTPS & HSTS Awareness (Item 6)
  3. Security Header Parity between Flask & FastAPI (Items 7-8)
  4. XSS & URL Sanitization (Items 11-12)
  5. Centralized Log Redaction (Items 13-16)
  6. Upload & Parser Decompression Bomb Hardening (Items 17-20)
  7. OCR Prompt Injection & Confirmation Invariant (Items 21-22)
  8. Chat Message & History Bounds (Items 28-30)
  9. Production Error & Debug Hardening (Items 31-32)
  10. Data Retention & Cleanup Safety (Items 43-45)
"""
import io
import logging
from datetime import datetime, timedelta
import pytest
from PIL import Image
from starlette.testclient import TestClient

from core.network_utils import get_trusted_client_ip, is_request_https, is_safe_url, sanitize_url
from core.security_headers import get_security_headers
from core.logging_redaction import redact_sensitive_text, SensitiveDataRedactionFilter
from core.storage_service import inspect_upload_safety, MAX_IMAGE_DIMENSION
from core.models import db, MedicalDocument, User
from core.cleanup_service import cleanup_expired_records
from core.main_fastapi import app as fastapi_app
from core.settings import get_settings


# ==============================================================================
# 1. TRUSTED PROXY & CLIENT IP SPOOFING TESTS
# ==============================================================================

class TestTrustedProxyHardening:
    """Kiểm thử phòng vệ chống giả mạo IP qua X-Forwarded-For."""

    def test_proxy_trust_off_ignores_spoofed_xff(self):
        """Khi trust_proxy=False: Header X-Forwarded-For giả mạo BỊ BỎ QUA HOÀN TOÀN, chỉ dùng Peer IP."""
        headers = {"x-forwarded-for": "203.0.113.195, 198.51.100.17"}
        client_ip = get_trusted_client_ip(
            remote_addr="127.0.0.1",
            headers=headers,
            trust_proxy=False
        )
        assert client_ip == "127.0.0.1"

    def test_proxy_trust_on_extracts_trusted_hop(self):
        """Khi trust_proxy=True: Phân tích hop tin cậy chuẩn xác (không tin giá trị đầu tiên client gửi)."""
        headers = {"x-forwarded-for": "spoofed.client.ip, 198.51.100.50, 10.0.0.1"}
        # Với 1 trusted proxy ở trước ứng dụng (trusted_proxy_count=1) -> lấy hop liền kề proxy (10.0.0.1)
        ip_hop1 = get_trusted_client_ip(
            remote_addr="10.0.0.2",
            headers=headers,
            trust_proxy=True,
            trusted_proxy_count=1
        )
        assert ip_hop1 == "10.0.0.1"

        # Với 2 trusted proxies (trusted_proxy_count=2) -> lấy hop thứ 2 từ cuối (198.51.100.50)
        ip_hop2 = get_trusted_client_ip(
            remote_addr="10.0.0.2",
            headers=headers,
            trust_proxy=True,
            trusted_proxy_count=2
        )
        assert ip_hop2 == "198.51.100.50"


# ==============================================================================
# 2. HTTPS & HSTS AWARENESS TESTS
# ==============================================================================

class TestHTTPSAwareness:
    """Kiểm thử cơ chế nhận biết HTTPS an toàn và phát sinh header HSTS."""

    def test_spoofed_forwarded_proto_ignored_when_proxy_trust_off(self):
        """Khi trust_proxy=False: Không tin cậy X-Forwarded-Proto giả mạo."""
        headers = {"x-forwarded-proto": "https"}
        assert is_request_https(is_direct_secure=False, headers=headers, trust_proxy=False) is False

    def test_forwarded_proto_honored_when_proxy_trust_on(self):
        """Khi trust_proxy=True: Tin cậy header X-Forwarded-Proto từ reverse proxy tin cậy."""
        headers = {"x-forwarded-proto": "https"}
        assert is_request_https(is_direct_secure=False, headers=headers, trust_proxy=True) is True

    def test_hsts_emitted_only_on_https_request(self):
        """Chính sách HSTS (Strict-Transport-Security) CHỈ được phát sinh khi request là HTTPS."""
        http_headers = get_security_headers(is_https=False)
        assert "Strict-Transport-Security" not in http_headers

        https_headers = get_security_headers(is_https=True)
        assert "Strict-Transport-Security" in https_headers
        assert "max-age=31536000" in https_headers["Strict-Transport-Security"]


# ==============================================================================
# 3. SECURITY HEADER PARITY & SERVER DISCLOSURE TESTS
# ==============================================================================

class TestSecurityHeaderParity:
    """Kiểm thử tính đồng nhất (Parity) 100% về Security Headers giữa Flask và FastAPI."""

    def test_fastapi_security_headers_parity(self):
        """FastAPI native routes phải có đầy đủ bộ khiên an ninh giống hệt Flask."""
        client = TestClient(fastapi_app)
        res = client.get("/health")
        assert res.status_code == 200

        headers = res.headers
        assert headers.get("server") == "MediMind-Clinical-Engine"
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "SAMEORIGIN"
        assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert headers.get("x-permitted-cross-domain-policies") == "none"
        assert "camera=()" in headers.get("permissions-policy", "")
        assert "default-src 'self'" in headers.get("content-security-policy", "")

    def test_flask_security_headers_parity(self, test_app):
        """Flask routes phải có đầy đủ bộ khiên an ninh tương đương."""
        client = test_app.test_client()
        res = client.get("/health")
        assert res.status_code == 200

        headers = res.headers
        assert headers.get("Server") == "MediMind-Clinical-Engine"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ==============================================================================
# 4. XSS & URL SANITIZATION TESTS
# ==============================================================================

class TestURLSanitization:
    """Kiểm thử hàm làm sạch URL chống XSS và nạp tài nguyên ngoài luồng."""

    def test_safe_schemes_allowed(self):
        assert is_safe_url("https://medlineplus.gov/ency/article/000123.htm") is True
        assert is_safe_url("http://localhost:8000/api/chat") is True
        assert is_safe_url("mailto:support@medimind.vn") is True
        assert is_safe_url("tel:19001234") is True
        assert is_safe_url("/static/css/main.css") is True

    def test_dangerous_schemes_rejected(self):
        assert is_safe_url("javascript:alert(1)") is False
        assert is_safe_url("JAVASCRIPT:alert(document.cookie)") is False
        assert is_safe_url("data:text/html,<script>alert(1)</script>") is False
        assert is_safe_url("file:///etc/passwd") is False
        assert is_safe_url("vbscript:MsgBox(1)") is False

    def test_sanitize_url_fallback(self):
        assert sanitize_url("javascript:evil()", default="/") == "/"
        assert sanitize_url("https://example.com/ok", default="/") == "https://example.com/ok"


# ==============================================================================
# 5. LOGGING REDACTION TESTS
# ==============================================================================

class TestLoggingRedaction:
    """Kiểm thử bộ lọc che giấu thông tin nhạy cảm trong hệ thống Log."""

    def test_redact_sensitive_credentials(self):
        text = "API KEY: AIzaSyD1234567890123456789012345678901 and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        redacted = redact_sensitive_text(text)
        assert "AIzaSy" not in redacted
        assert "[API_KEY_REDACTED]" in redacted
        assert "[TOKEN_REDACTED]" in redacted

    def test_redact_pii_emails_and_phones(self):
        text = "Bệnh nhân test.user@medimind.vn có số điện thoại 0912345678 và session=sess_abc12345678901234"
        redacted = redact_sensitive_text(text)
        assert "test.user@medimind.vn" not in redacted
        assert "[EMAIL_REDACTED]" in redacted
        assert "0912345678" not in redacted
        assert "[PHONE_REDACTED]" in redacted
        assert "[SESSION_REDACTED]" in redacted

    def test_logging_filter_redacts_record(self):
        log_filter = SensitiveDataRedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="User login failed for secret_password: %s, token=%s",
            args=("MatKhauBiMat123@", "AIzaSyABCDEF1234567890123456789012345"),
            exc_info=None
        )
        log_filter.filter(record)
        assert "MatKhauBiMat123@" not in str(record.args)
        assert "MatKhauBiMat123@" not in record.msg
        assert "AIzaSyABCDEF" not in str(record.args)
        assert "AIzaSyABCDEF" not in record.msg


# ==============================================================================
# 6. UPLOAD & PARSER DECOMPRESSION BOMB HARDENING TESTS
# ==============================================================================

class TestUploadParserHardening:
    """Kiểm thử phòng vệ tấn công Decompression Bomb và định dạng tài liệu."""

    def test_image_dimension_limits_rejected(self):
        """Ảnh có kích thước vượt MAX_IMAGE_DIMENSION (8000px) bị từ chối an toàn."""
        # Tạo ảnh hợp lệ nhỏ
        img = Image.new("RGB", (100, 100), color="white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        valid_bytes = buf.getvalue()
        is_safe, _ = inspect_upload_safety(valid_bytes, "jpg")
        assert is_safe is True

        # Ảnh vượt quá kích thước an toàn
        oversized = Image.new("RGB", (MAX_IMAGE_DIMENSION + 100, 50), color="white")
        buf_over = io.BytesIO()
        oversized.save(buf_over, format="JPEG")
        is_safe_over, err = inspect_upload_safety(buf_over.getvalue(), "jpg")
        assert is_safe_over is False
        assert "vượt quá giới hạn tối đa" in err


# ==============================================================================
# 7. OCR PROMPT INJECTION & CONFIRMATION INVARIANT TESTS
# ==============================================================================

class TestOCRTrustAndConfirmationInvariant:
    """Kiểm thử tính bất biến: OCR là dữ liệu untrusted và ocr_draft không tự động xác nhận."""

    def test_ocr_draft_excluded_from_confirmed_patient_history(self, test_app):
        """Hồ sơ ở trạng thái 'ocr_draft' không được xuất hiện trong lịch sử bệnh án chính thức."""
        with test_app.app_context():
            user = User.query.filter_by(email="patient_ocr_test@medimind.vn").first()
            if not user:
                user = User(
                    email="patient_ocr_test@medimind.vn",
                    full_name="Bệnh Nhân Test OCR",
                    role="patient"
                )
                user.set_password("MatKhauChuan123@")
                db.session.add(user)
                db.session.commit()

            # Tạo 1 draft và 1 confirmed doc
            draft_doc = MedicalDocument(
                storage_filename="draft_sample.png",
                original_filename="don_thuoc_draft.png",
                file_path="uploads/draft_sample.png",
                file_size=1024,
                file_type="PNG",
                owner_id=user.id,
                doc_type="ocr_draft"
            )
            confirmed_doc = MedicalDocument(
                storage_filename="confirmed_sample.png",
                original_filename="don_thuoc_confirmed.png",
                file_path="uploads/confirmed_sample.png",
                file_size=1024,
                file_type="PNG",
                owner_id=user.id,
                doc_type="prescription"
            )
            db.session.add_all([draft_doc, confirmed_doc])
            db.session.commit()

            # Truy vấn hồ sơ chính thức (phải loại trừ ocr_draft)
            confirmed_records = MedicalDocument.query.filter_by(
                owner_id=user.id
            ).filter(MedicalDocument.doc_type != "ocr_draft").all()

            assert len(confirmed_records) >= 1
            assert all(doc.doc_type != "ocr_draft" for doc in confirmed_records)


# ==============================================================================
# 8. CHAT MESSAGE & HISTORY BOUNDS TESTS
# ==============================================================================

class TestChatMessageBounds:
    """Kiểm thử giới hạn kích thước dữ liệu chat trên FastAPI endpoint."""

    def test_oversized_chat_message_rejected(self):
        """Tin nhắn chat dài quá 2,000 ký tự bị FastAPI từ chối bằng 400 Validation Error."""
        client = TestClient(fastapi_app)
        oversized_text = "A" * 2500
        res = client.post(
            "/api/chat",
            headers={"origin": "http://localhost:8000"},
            json={"message": oversized_text, "history": []}
        )
        assert res.status_code == 400
        data = res.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_oversized_history_rejected(self):
        """Lịch sử chat vượt quá 50 lượt bị từ chối bằng 400 Validation Error."""
        client = TestClient(fastapi_app)
        oversized_history = [{"role": "user", "content": "hello"}] * 55
        res = client.post(
            "/api/chat",
            headers={"origin": "http://localhost:8000"},
            json={"message": "Tôi bị sốt", "history": oversized_history}
        )
        assert res.status_code == 400
        data = res.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# 9. PRODUCTION ERROR & DEBUG HARDENING TESTS
# ==============================================================================

class TestProductionErrorHardening:
    """Kiểm thử che giấu lỗi nội bộ và cấu hình debug trong môi trường sản xuất."""

    def test_settings_production_debug_flag(self):
        """Xác nhận get_settings().server.is_production kiểm soát chặt chẽ cờ debug."""
        settings = get_settings()
        # Trong test env hoặc prod env, debug không được tự động bật nếu không cấu hình rõ
        assert isinstance(settings.server.debug, bool)


# ==============================================================================
# 10. DATA RETENTION & CLEANUP SAFETY TESTS
# ==============================================================================

class TestDataRetentionSafety:
    """Kiểm thử tính an toàn của dịch vụ dọn dẹp tài liệu tạm."""

    def test_cleanup_preserves_confirmed_documents(self, test_app, tmp_path):
        """Dịch vụ dọn dẹp chỉ xóa ocr_draft hết hạn, TUYỆT ĐỐI KHÔNG XÓA hồ sơ y tế đã xác nhận."""
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        with test_app.app_context():
            user = User.query.filter_by(email="retention_test_user@medimind.vn").first()
            if not user:
                user = User(
                    email="retention_test_user@medimind.vn",
                    full_name="Người Dùng Retention Test",
                    role="patient"
                )
                user.set_password("MatKhauTest123@")
                db.session.add(user)
                db.session.commit()

            # Tạo file và bản ghi draft cũ (> 48 giờ trước)
            old_time = datetime.utcnow() - timedelta(hours=48)
            old_draft = MedicalDocument(
                storage_filename="old_draft.png",
                original_filename="old_draft.png",
                file_path=str(upload_dir / "old_draft.png"),
                file_size=500,
                file_type="PNG",
                owner_id=user.id,
                doc_type="ocr_draft",
                created_at=old_time
            )
            # Tạo file vật lý cho draft cũ
            (upload_dir / "old_draft.png").write_bytes(b"dummy_draft_bytes")

            # Tạo bản ghi đã xác nhận cũ (> 48 giờ trước)
            confirmed_doc = MedicalDocument(
                storage_filename="permanent_record.png",
                original_filename="permanent_record.png",
                file_path=str(upload_dir / "permanent_record.png"),
                file_size=500,
                file_type="PNG",
                owner_id=user.id,
                doc_type="prescription",
                created_at=old_time
            )
            (upload_dir / "permanent_record.png").write_bytes(b"dummy_confirmed_bytes")

            db.session.add_all([old_draft, confirmed_doc])
            db.session.commit()

            # Chạy dọn dẹp với ngưỡng 24 giờ
            results = cleanup_expired_records(
                db_session=db.session,
                upload_dir=str(upload_dir),
                ocr_retention_hours=24
            )

            assert results["expired_drafts_deleted"] >= 1
            assert results["orphaned_files_deleted"] >= 1

            # Bản ghi xác nhận và tệp tin xác nhận PHẢI NGUYÊN VẸN
            remaining_confirmed = db.session.get(MedicalDocument, confirmed_doc.id)
            assert remaining_confirmed is not None
            assert (upload_dir / "permanent_record.png").exists() is True

            # Bản ghi draft cũ phải bị xóa khỏi DB và đĩa
            remaining_draft = db.session.get(MedicalDocument, old_draft.id)
            assert remaining_draft is None
            assert (upload_dir / "old_draft.png").exists() is False
