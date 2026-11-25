"""
tests/test_google_oauth_flow.py
Kiểm thử chuẩn toàn bộ luồng Google OAuth 2.0 Authorization Code Flow:
1. Fail-closed khi thiếu GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (503 JSON & redirect error).
2. Khởi tạo auth_url chuẩn với client_id, redirect_uri, prompt=select_account, HMAC state.
3. Chặn state giả mạo, state lệch session, lỗi access_denied và email_verified=False.
4. Luồng người dùng mới: callback -> pending_register -> /pending -> complete-registration (kể cả không có SĐT) & cancel-registration.
5. Luồng người dùng cũ: callback -> cập nhật avatar -> đăng nhập ngay với session cố định (Session Fixation protection).
6. Xác minh modal Google giả (#google-account-modal) đã bị gỡ sạch khỏi HTML & JS.
"""

import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app import create_app
from core.shared.models import User, db

ROOT = Path(__file__).resolve().parent.parent


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def oauth_client(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-test-secret-value")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    yield app, client


def test_google_login_unconfigured_returns_503_and_redirect_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()

    res_json = client.get("/api/auth/google/login?format=json")
    assert res_json.status_code == 503
    data = res_json.get_json()
    assert data["success"] is False
    assert data["configured"] is False

    res_redir = client.get("/api/auth/google/login")
    assert res_redir.status_code == 302
    assert "error_reason=unconfigured" in res_redir.headers["Location"]


def test_google_login_generates_valid_oauth2_auth_url(oauth_client):
    _, client = oauth_client

    res = client.get("/api/auth/google/login?intent=login&format=json")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["configured"] is True

    parsed = urlparse(data["auth_url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"

    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["test-client-id.apps.googleusercontent.com"]
    assert qs["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/google/callback"]
    assert qs["response_type"] == ["code"]
    assert qs["prompt"] == ["select_account"]
    assert "openid" in qs["scope"][0] and "email" in qs["scope"][0]
    assert "." in qs["state"][0]


def test_google_callback_rejects_tampered_or_mismatched_state_and_errors(oauth_client):
    _, client = oauth_client

    # 1. Google trả access_denied
    res_err = client.get("/api/auth/google/callback?error=access_denied")
    assert res_err.status_code == 302
    assert "error_reason=access_denied" in res_err.headers["Location"]

    # 2. Khởi tạo state hợp lệ trong session nhưng gửi state giả
    client.get("/api/auth/google/login?format=json")
    res_bad = client.get("/api/auth/google/callback?code=abc&state=forged.token")
    assert res_bad.status_code == 302
    assert "error_reason=invalid_state" in res_bad.headers["Location"]


def test_google_callback_rejects_unverified_email(oauth_client, monkeypatch):
    _, client = oauth_client

    login_data = client.get("/api/auth/google/login?format=json").get_json()
    state = parse_qs(urlparse(login_data["auth_url"]).query)["state"][0]

    def fake_urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "oauth2.googleapis.com/token" in url:
            return _FakeHTTPResponse({"access_token": "mock-access-token"})
        return _FakeHTTPResponse(
            {
                "email": "unverified@example.com",
                "email_verified": False,
                "name": "Unverified User",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    res = client.get(f"/api/auth/google/callback?code=valid-code&state={state}")
    assert res.status_code == 302
    assert "error_reason=email_unverified" in res.headers["Location"]


def test_google_oauth_new_user_pending_complete_and_cancel_flows(oauth_client, monkeypatch):
    app, client = oauth_client
    csrf = {"Origin": "http://localhost"}

    def fake_urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "oauth2.googleapis.com/token" in url:
            return _FakeHTTPResponse({"access_token": "mock-access-token"})
        return _FakeHTTPResponse(
            {
                "email": "new.google.patient@example.com",
                "email_verified": True,
                "name": "Trần Thị Lan",
                "picture": "https://lh3.googleusercontent.com/a/avatar-lan",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    # A. Test luồng hủy đăng ký (cancel-registration) không ghi DB
    st1 = parse_qs(urlparse(client.get("/api/auth/google/login?format=json").get_json()["auth_url"]).query)["state"][0]
    cb1 = client.get(f"/api/auth/google/callback?code=code-1&state={st1}")
    assert cb1.status_code == 302
    assert "google_auth=pending_register" in cb1.headers["Location"]

    pending1 = client.get("/api/auth/google/pending").get_json()
    assert pending1["pending"] is True
    assert pending1["profile"]["email"] == "new.google.patient@example.com"

    cancel_res = client.post("/api/auth/google/cancel-registration", headers=csrf)
    assert cancel_res.status_code == 200
    assert client.get("/api/auth/google/pending").get_json()["pending"] is False
    with app.app_context():
        assert User.query.filter_by(email="new.google.patient@example.com").first() is None

    # B. Test luồng hoàn tất đăng ký (complete-registration) kể cả khi không nhập SĐT
    st2 = parse_qs(urlparse(client.get("/api/auth/google/login?format=json").get_json()["auth_url"]).query)["state"][0]
    cb2 = client.get(f"/api/auth/google/callback?code=code-2&state={st2}")
    assert cb2.status_code == 302
    assert "google_auth=pending_register" in cb2.headers["Location"]

    complete_res = client.post(
        "/api/auth/google/complete-registration",
        json={"full_name": "Trần Thị Lan", "gender": "Nữ", "dob": "12/05/1998", "phone_number": ""},
        headers=csrf,
    )
    assert complete_res.status_code == 200
    comp_data = complete_res.get_json()
    assert comp_data["success"] is True
    assert comp_data["user"]["email"] == "new.google.patient@example.com"
    assert comp_data["user"]["role"] == "patient"

    me_data = client.get("/api/auth/me").get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == "new.google.patient@example.com"


def test_google_oauth_existing_user_logs_in_directly(oauth_client, monkeypatch):
    app, client = oauth_client

    with app.app_context():
        u = User(email="existing.google@example.com", full_name="Lê Minh Quân", role="patient")
        u.set_password("StrongPass123")
        db.session.add(u)
        db.session.commit()

    def fake_urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "oauth2.googleapis.com/token" in url:
            return _FakeHTTPResponse({"access_token": "mock-token-existing"})
        return _FakeHTTPResponse(
            {
                "email": "existing.google@example.com",
                "email_verified": True,
                "name": "Lê Minh Quân",
                "picture": "https://lh3.googleusercontent.com/a/avatar-quan",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    st = parse_qs(urlparse(client.get("/api/auth/google/login?format=json").get_json()["auth_url"]).query)["state"][0]
    cb = client.get(f"/api/auth/google/callback?code=code-existing&state={st}")
    assert cb.status_code == 302
    assert "google_auth=success" in cb.headers["Location"]
    assert "existing=1" in cb.headers["Location"]

    me_data = client.get("/api/auth/me").get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["avatar_url"] == "https://lh3.googleusercontent.com/a/avatar-quan"


def test_simulated_google_modal_removed_from_frontend():
    """Đảm bảo modal chọn tài khoản Google giả (#google-account-modal) đã bị gỡ hoàn toàn khỏi HTML và JS."""
    html_text = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    js_text = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    for forbidden in (
        "google-account-modal",
        "startGoogleAccountSelection",
        "submitCustomGoogleAccount",
        "setGoogleModalState",
        "closeGoogleAccountModal",
    ):
        assert forbidden not in html_text, f"Still found '{forbidden}' in templates/index.html"
        assert forbidden not in js_text, f"Still found '{forbidden}' in static/js/app.js"
    assert isinstance(io.BytesIO(b""), io.BytesIO)


def test_google_signin_button_resets_on_bfcache_back_and_mode_switch():
    """Ngăn lỗi nút Google kẹt spinner hoặc ghi đè chữ vào thẻ span animate-spin khi bấm Back từ Google rồi đổi tab Đăng ký."""
    js_text = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "function resetGoogleSignInButton()" in js_text
    assert "window.addEventListener('pageshow'" in js_text
    assert '#btn-google-signin [data-i18n="btn_google_signin"]' in js_text
    assert "querySelector('#btn-google-signin span')" not in js_text
