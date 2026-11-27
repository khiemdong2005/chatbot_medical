"""
tests/test_forgot_password_otp.py
Kiểm thử đầy đủ tính năng Quên mật khẩu & Đặt lại mật khẩu qua OTP:
- 1B: Kiểm tra tồn tại tài khoản (404 khi không tồn tại) ở /api/auth/otp/send.
- 2B: Mật khẩu mới >= 8 ký tự, có chữ hoa + chữ thường + số, cấm đặt trùng mật khẩu cũ.
- 3A: Sau khi đặt lại mật khẩu thành công, xóa session cũ (requires_login=True), không auto-login, đăng nhập lại bằng mật khẩu mới.
- 4:  OTP TTL = 120s, nhập sai tối đa 5 lần hủy mã, tiêu đề email đúng ngữ cảnh "Đặt lại mật khẩu",
      chặn Dev Simulator khi ENV=production (fail-closed) cho cả Email & SMS.
"""

from pathlib import Path
import time

import pytest

from app import create_app
from core.auth.email_service import EmailService
from core.auth.otp_service import OtpManager, otp_manager
from core.auth.sms_service import SmsService
from core.shared.models import User, db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def reset_client(monkeypatch):
    """Flask test client với SQLite in-memory, cô lập hoàn toàn OTP store & không gửi mạng thật."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    sent_emails = []
    sent_sms = []

    def fake_send_email(to_email, subject, html_body, text_body=None):
        sent_emails.append(
            {
                "to": to_email,
                "subject": subject,
                "html": html_body,
                "text": text_body or "",
            }
        )
        return True

    def fake_send_sms(to_phone, otp_code, brand_name="MediMind AI", ttl_seconds=120):
        sent_sms.append({"to": to_phone, "code": otp_code, "ttl": ttl_seconds})
        return True

    monkeypatch.setattr("core.auth.email_service.email_service.send_email", fake_send_email)
    monkeypatch.setattr("core.auth.sms_service.sms_service.send_otp_sms", fake_send_sms)

    with otp_manager._lock:
        otp_manager._store.clear()
        otp_manager._verified_store.clear()

    with app.app_context():
        user = User(
            email="patient.reset@example.com",
            full_name="Nguyễn Văn Minh",
            role="patient",
            phone_number="0912345678",
        )
        user.set_password("OldPass123")
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    yield app, client, sent_emails, sent_sms

    with otp_manager._lock:
        otp_manager._store.clear()
        otp_manager._verified_store.clear()


def test_otp_default_policy_is_120s_and_5_attempts():
    """Xác minh cấu hình mặc định: TTL 120 giây (2 phút) và tối đa 5 lần nhập sai."""
    assert otp_manager.ttl == 120
    assert otp_manager.max_attempts == 5

    mgr = OtpManager()
    assert mgr.ttl == 120
    assert mgr.max_attempts == 5


def test_forgot_password_send_otp_rejects_unknown_account_1b(reset_client):
    """1B: Gửi OTP reset_pwd cho tài khoản không tồn tại trả 404 và không gửi thư."""
    _, client, sent_emails, sent_sms = reset_client

    res = client.post(
        "/api/auth/otp/send",
        json={"identifier": "khongtontai@example.com", "channel": "email", "purpose": "reset_pwd"},
    )
    assert res.status_code == 404
    data = res.get_json()
    assert data["success"] is False
    assert len(sent_emails) == 0

    res_sms = client.post(
        "/api/auth/otp/send",
        json={"identifier": "0988776655", "channel": "sms", "purpose": "reset_pwd"},
    )
    assert res_sms.status_code == 404
    assert len(sent_sms) == 0


def test_forgot_password_end_to_end_email_and_session_invalidation_3a(reset_client):
    """Luồng chuẩn Email OTP reset_pwd: tiêu đề email đúng ngữ cảnh, TTL 120s, đổi mật khẩu DB, xóa session cũ (3A)."""
    _, client, sent_emails, _ = reset_client

    # Đăng nhập trước để xác minh session cũ bị xóa sau khi đặt lại mật khẩu
    login_old = client.post(
        "/api/auth/login",
        json={"identifier": "patient.reset@example.com", "password": "OldPass123"},
    )
    assert login_old.status_code == 200
    assert client.get("/api/auth/me").get_json()["authenticated"] is True

    # Bước 1: Yêu cầu OTP đặt lại mật khẩu (kèm Origin hợp lệ vì client đang có session cookie)
    csrf_headers = {"Origin": "http://localhost"}
    res_send = client.post(
        "/api/auth/otp/send",
        json={"identifier": "patient.reset@example.com", "channel": "email", "purpose": "reset_pwd"},
        headers=csrf_headers,
    )
    assert res_send.status_code == 200
    send_data = res_send.get_json()
    assert send_data["success"] is True
    assert send_data["expires_in"] == 120
    assert len(sent_emails) == 1
    assert "Đặt lại mật khẩu" in sent_emails[0]["subject"]
    assert "120 giây" in sent_emails[0]["html"]
    assert "Nguyễn Văn Minh" in sent_emails[0]["html"]

    otp_code = otp_manager.get_active_code("patient.reset@example.com", "email")
    assert otp_code and len(otp_code) == 6

    # Bước 2: Xác minh OTP và đặt mật khẩu mới mạnh
    res_verify = client.post(
        "/api/auth/otp/verify",
        json={
            "identifier": "patient.reset@example.com",
            "channel": "email",
            "code": otp_code,
            "purpose": "reset_pwd",
            "user_data": {"new_password": "NewStrong2026"},
        },
        headers=csrf_headers,
    )
    assert res_verify.status_code == 200
    verify_data = res_verify.get_json()
    assert verify_data["success"] is True
    assert verify_data["purpose"] == "reset_pwd"
    assert verify_data["requires_login"] is True
    assert "user" not in verify_data

    # 3A: Phiên cũ đã bị xóa sạch, yêu cầu đăng nhập lại
    assert client.get("/api/auth/me").get_json()["authenticated"] is False

    # Mật khẩu cũ không còn đăng nhập được
    fail_old = client.post(
        "/api/auth/login",
        json={"identifier": "patient.reset@example.com", "password": "OldPass123"},
    )
    assert fail_old.status_code == 401

    # Mật khẩu mới đăng nhập thành công
    ok_new = client.post(
        "/api/auth/login",
        json={"identifier": "patient.reset@example.com", "password": "NewStrong2026"},
    )
    assert ok_new.status_code == 200
    assert ok_new.get_json()["success"] is True


def test_forgot_password_strong_policy_and_no_reuse_2b(reset_client):
    """2B: Từ chối mật khẩu yếu (không đốt OTP) và từ chối mật khẩu trùng mật khẩu cũ."""
    _, client, _, _ = reset_client

    res_send = client.post(
        "/api/auth/otp/send",
        json={"identifier": "patient.reset@example.com", "channel": "email", "purpose": "reset_pwd"},
    )
    assert res_send.status_code == 200
    otp_code = otp_manager.get_active_code("patient.reset@example.com", "email")

    # Các mật khẩu không đạt chuẩn 2B
    for weak in ("Short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"):
        res_weak = client.post(
            "/api/auth/otp/verify",
            json={
                "identifier": "patient.reset@example.com",
                "channel": "email",
                "code": otp_code,
                "purpose": "reset_pwd",
                "user_data": {"new_password": weak},
            },
        )
        assert res_weak.status_code == 400
        assert res_weak.get_json()["success"] is False

    # OTP vẫn còn sống vì validate format diễn ra trước khi tiêu thụ OTP
    assert otp_manager.get_active_code("patient.reset@example.com", "email") == otp_code

    # Từ chối đặt trùng mật khẩu hiện tại (OldPass123)
    res_reuse = client.post(
        "/api/auth/otp/verify",
        json={
            "identifier": "patient.reset@example.com",
            "channel": "email",
            "code": otp_code,
            "purpose": "reset_pwd",
            "user_data": {"new_password": "OldPass123"},
        },
    )
    assert res_reuse.status_code == 400
    assert "trùng" in res_reuse.get_json()["error"].lower()


def test_otp_lockout_after_5_wrong_attempts_and_120s_expiry(monkeypatch):
    """Kiểm tra khóa mã sau đúng 5 lần nhập sai và hết hạn sau 120 giây."""
    mgr = OtpManager(ttl_seconds=120, cooldown_seconds=60, max_attempts=5)
    monkeypatch.setattr("core.auth.otp_service.email_service.send_verification_otp", lambda *a, **kw: True)

    ok, _, _ = mgr.request_otp("user@example.com", channel="email", purpose="reset_pwd")
    assert ok is True
    real_code = mgr.get_active_code("user@example.com", "email")
    wrong_code = "000000" if real_code != "000000" else "999999"

    for attempt in range(1, 5):
        v_ok, msg = mgr.verify_otp("user@example.com", "email", wrong_code, purpose="reset_pwd")
        assert v_ok is False
        assert f"còn {5 - attempt} lần" in msg

    # Lần sai thứ 5 phải hủy mã ngay lập tức
    v_ok5, msg5 = mgr.verify_otp("user@example.com", "email", wrong_code, purpose="reset_pwd")
    assert v_ok5 is False
    assert "5 lần" in msg5
    assert mgr.get_active_code("user@example.com", "email") is None

    # Kiểm tra hết hạn sau 120s
    ok2, _, _ = mgr.request_otp("exp@example.com", channel="email", purpose="reset_pwd")
    assert ok2 is True
    code2 = mgr.get_active_code("exp@example.com", "email")
    key2 = "email:exp@example.com"
    mgr._store[key2]["expires_at"] = time.time() - 1
    v_exp, msg_exp = mgr.verify_otp("exp@example.com", "email", code2, purpose="reset_pwd")
    assert v_exp is False
    assert "hết hạn" in msg_exp.lower()


def test_dev_simulator_blocked_in_production_for_email_and_sms(monkeypatch, capsys):
    """Chặn Dev Simulator khi ENV=production (fail-closed, không in OTP ra terminal); local dev vẫn hoạt động."""
    for var in ("SMTP_SERVER", "SMTP_USERNAME", "SMTP_PASSWORD", "SPEEDSMS_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    # 1. Production mode -> Fail-closed, không in OTP ra stdout
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("FLASK_ENV", "production")
    es = EmailService()
    ss = SmsService()

    assert es.send_verification_otp("prod@example.com", "654321", purpose="reset_pwd") is False
    assert ss.send_otp_sms("0912345678", "654321") is False
    out_prod = capsys.readouterr().out
    assert "654321" not in out_prod

    # 2. Local development mode -> Cho phép Dev Simulator in OTP ra terminal
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("FLASK_ENV", "development")
    assert es.send_verification_otp("dev@example.com", "123456", purpose="reset_pwd") is True
    assert ss.send_otp_sms("0912345678", "123456") is True
    out_dev = capsys.readouterr().out
    assert "123456" in out_dev


def test_frontend_forgot_password_policy_and_login_redirect_contract():
    """Đảm bảo HTML & JS đồng bộ chính sách 2B (>= 8 ký tự, hoa/thường/số) và 3A (quay lại form đăng nhập)."""
    html_text = (ROOT / "frontend" / "templates" / "index.html").read_text(encoding="utf-8")
    js_text = (ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert 'id="forgot-new-password" required minlength="8"' in html_text
    assert "function t(viText, enText)" in js_text
    assert "newPassword.length < 8" in js_text
    assert "password.length < 8" in js_text
    assert "pendingOtpFlow.purpose === 'reset_pwd'" in js_text
    assert "toggleAuthMode('login')" in js_text


def test_registration_rejects_weak_passwords_123456_and_123456789(reset_client):
    """Đăng ký tài khoản bắt buộc mật khẩu mạnh >= 8 ký tự gồm chữ hoa, chữ thường và số."""
    _, client, _, _ = reset_client
    for weak in ("123456", "123456789", "abcdefgh"):
        res = client.post(
            "/api/auth/register",
            json={"identifier": f"weak_{weak}@example.com", "full_name": "Weak Test", "password": weak},
        )
        assert res.status_code == 400
        assert res.get_json()["success"] is False
        assert "8 ký tự" in res.get_json()["error"] or "chữ hoa" in res.get_json()["error"]


def test_otp_registration_redirects_to_login_without_auto_session(reset_client):
    """Sau khi đăng ký bằng OTP thành công, không tự đăng nhập mà yêu cầu quay lại bước Đăng nhập."""
    _, client, sent_emails, _ = reset_client

    res_send = client.post(
        "/api/auth/otp/send",
        json={
            "identifier": "new.patient@example.com",
            "channel": "email",
            "purpose": "register",
            "full_name": "Phạm Minh Khoa",
        },
    )
    assert res_send.status_code == 200
    assert len(sent_emails) == 1

    otp_code = otp_manager.get_active_code("new.patient@example.com", "email")
    assert otp_code and len(otp_code) == 6

    res_reg = client.post(
        "/api/auth/otp/verify",
        json={
            "identifier": "new.patient@example.com",
            "channel": "email",
            "code": otp_code,
            "purpose": "register",
            "user_data": {
                "full_name": "Phạm Minh Khoa",
                "password": "RegPass2026",
            },
        },
    )
    assert res_reg.status_code == 201
    reg_data = res_reg.get_json()
    assert reg_data["success"] is True
    assert reg_data["purpose"] == "register"
    assert reg_data["requires_login"] is True

    # Chưa tự động đăng nhập -> /api/auth/me trả authenticated=False
    assert client.get("/api/auth/me").get_json()["authenticated"] is False

    # Đăng nhập bằng tài khoản vừa tạo -> thành công
    res_login = client.post(
        "/api/auth/login",
        json={"identifier": "new.patient@example.com", "password": "RegPass2026"},
    )
    assert res_login.status_code == 200
    assert res_login.get_json()["success"] is True
    assert client.get("/api/auth/me").get_json()["authenticated"] is True
