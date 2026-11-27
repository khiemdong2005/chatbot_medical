"""Tests for synced first-login profile onboarding dialog (matching Google OAuth flow)."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-32bytes-long-for-testing")
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")
os.environ.setdefault("DEV_SEED_USERS", "false")
os.environ.setdefault("FLASK_DEBUG", "0")

from app import create_app
from core.models import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _make_client():
    tmpdir = tempfile.TemporaryDirectory()
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SECRET_KEY": "test-secret-key-32bytes-long-for-testing",
            "SESSION_COOKIE_SECURE": False,
            "UPLOAD_FOLDER": tmpdir.name,
        }
    )
    return flask_app, tmpdir


def test_first_time_registration_triggers_onboarding_dialog_on_first_login_only():
    flask_app, tmpdir = _make_client()
    try:
        client = flask_app.test_client()

        # 1. Register new account -> requires_login=True and needs_onboarding=True
        reg_res = client.post(
            "/api/auth/register",
            json={
                "identifier": "firstlogin_user@example.com",
                "full_name": "Nguyen Van Moi",
                "password": "Password123",
            },
        )
        assert reg_res.status_code == 201
        reg_data = reg_res.get_json()
        assert reg_data["success"] is True
        assert reg_data["requires_login"] is True
        assert reg_data["user"]["needs_onboarding"] is True

        # Still unauthenticated until explicit login
        me_before = client.get("/api/auth/me").get_json()
        assert me_before["authenticated"] is False

        # 2. First login -> needs_onboarding=True
        login1_res = client.post(
            "/api/auth/login",
            json={
                "identifier": "firstlogin_user@example.com",
                "password": "Password123",
            },
        )
        assert login1_res.status_code == 200
        login1_data = login1_res.get_json()
        assert login1_data["success"] is True
        assert login1_data["needs_onboarding"] is True
        assert login1_data["user"]["needs_onboarding"] is True

        # /api/auth/me also reflects needs_onboarding=True before confirmation
        me_first = client.get("/api/auth/me").get_json()
        assert me_first["authenticated"] is True
        assert me_first["user"]["needs_onboarding"] is True

        # 3. Submit onboarding profile dialog -> marks onboarding_completed=True
        prof_res = client.post(
            "/api/auth/profile",
            headers={"Origin": "http://localhost"},
            json={
                "name": "Nguyen Van Moi",
                "gender": "Nam",
                "dob": "15/08/1998",
                "phone_number": "0912345678",
                "complete_onboarding": True,
            },
        )
        assert prof_res.status_code == 200
        prof_data = prof_res.get_json()
        assert prof_data["success"] is True
        assert prof_data["user"]["dob"] == "15/08/1998"
        assert prof_data["user"]["phone_number"] == "0912345678"
        assert prof_data["user"]["needs_onboarding"] is False

        # 4. Logout & Second login -> needs_onboarding=False (straight to app)
        client.post("/api/auth/logout", headers={"Origin": "http://localhost"})
        login2_res = client.post(
            "/api/auth/login",
            json={
                "identifier": "firstlogin_user@example.com",
                "password": "Password123",
            },
        )
        assert login2_res.status_code == 200
        login2_data = login2_res.get_json()
        assert login2_data["success"] is True
        assert login2_data["needs_onboarding"] is False
        assert login2_data["user"]["needs_onboarding"] is False
    finally:
        with flask_app.app_context():
            db.session.remove()
            db.drop_all()
        tmpdir.cleanup()


def test_otp_registration_triggers_onboarding_dialog_on_first_login_and_2fa():
    from unittest.mock import patch

    flask_app, tmpdir = _make_client()
    try:
        client = flask_app.test_client()

        # 1. Register via /api/auth/otp/verify (live web OTP registration flow)
        with patch("core.auth.otp_service.otp_manager.verify_otp", return_value=(True, "")):
            reg_res = client.post(
                "/api/auth/otp/verify",
                json={
                    "identifier": "otp_new_user@example.com",
                    "channel": "email",
                    "code": "123456",
                    "purpose": "register",
                    "user_data": {
                        "full_name": "Tran Thi OTP",
                        "password": "Password123",
                        "gender": "Nữ",
                        "dob": "20/05/1999",
                    },
                },
            )
        assert reg_res.status_code == 201
        reg_data = reg_res.get_json()
        assert reg_data["success"] is True
        assert reg_data["requires_login"] is True
        assert reg_data["user"]["needs_onboarding"] is True

        # 2. First password login -> needs_onboarding=True
        login1_res = client.post(
            "/api/auth/login",
            json={"identifier": "otp_new_user@example.com", "password": "Password123"},
        )
        assert login1_res.status_code == 200
        login1_data = login1_res.get_json()
        assert login1_data["needs_onboarding"] is True
        assert login1_data["user"]["needs_onboarding"] is True

        # 3. First 2FA OTP login before completing onboarding -> needs_onboarding=True
        client.post("/api/auth/logout", headers={"Origin": "http://localhost"})
        with patch("core.auth.otp_service.otp_manager.verify_otp", return_value=(True, "")):
            otp_login_res = client.post(
                "/api/auth/otp/verify",
                json={
                    "identifier": "otp_new_user@example.com",
                    "channel": "email",
                    "code": "654321",
                    "purpose": "login_2fa",
                },
            )
        assert otp_login_res.status_code == 200
        otp_login_data = otp_login_res.get_json()
        assert otp_login_data["needs_onboarding"] is True
        assert otp_login_data["user"]["needs_onboarding"] is True

        # 4. Complete onboarding -> subsequent logins skip popup
        prof_res = client.post(
            "/api/auth/profile",
            headers={"Origin": "http://localhost"},
            json={"name": "Tran Thi OTP", "complete_onboarding": True},
        )
        assert prof_res.status_code == 200
        assert prof_res.get_json()["user"]["needs_onboarding"] is False

        client.post("/api/auth/logout", headers={"Origin": "http://localhost"})
        login2_res = client.post(
            "/api/auth/login",
            json={"identifier": "otp_new_user@example.com", "password": "Password123"},
        )
        assert login2_res.status_code == 200
        assert login2_res.get_json()["needs_onboarding"] is False
    finally:
        with flask_app.app_context():
            db.session.remove()
            db.drop_all()
        tmpdir.cleanup()


def test_frontend_first_login_onboarding_sync_contract():
    app_js = (PROJECT_ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "let isFirstLoginOnboarding = false;" in app_js
    assert "if (data.needs_onboarding || currentUser.needs_onboarding)" in app_js
    assert "if (data.needs_onboarding || currentUser?.needs_onboarding)" in app_js
    assert "if (googleOnboarding || currentUser.needs_onboarding)" in app_js
    assert "openGoogleOnboardingModal(currentUser, false, { firstLogin: true })" in app_js
    assert "complete_onboarding: true" in app_js
    assert "(isPendingGoogleRegistration || isFirstLoginOnboarding) ? 'Xác nhận & Vào ứng dụng' : 'Lưu thông tin'" in app_js
    assert "sessionStorage.removeItem('medimind_profile_draft')" in app_js


def test_google_oauth_existing_unonboarded_user_triggers_onboarding_flag(monkeypatch):
    import json
    from urllib.parse import parse_qs, urlparse

    class _FakeResp:
        def __init__(self, payload):
            self._raw = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-test-secret-value")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback")

    flask_app, tmpdir = _make_client()
    try:
        client = flask_app.test_client()
        reg_res = client.post(
            "/api/auth/register",
            json={
                "identifier": "hybrid.google@example.com",
                "full_name": "Le Hybrid",
                "password": "Password123",
            },
        )
        assert reg_res.status_code == 201

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "oauth2.googleapis.com/token" in url:
                return _FakeResp({"access_token": "mock-token"})
            return _FakeResp(
                {
                    "email": "hybrid.google@example.com",
                    "email_verified": True,
                    "name": "Le Hybrid",
                    "picture": "https://lh3.googleusercontent.com/a/hybrid",
                }
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        # First Google sign-in for registered user who hasn't finished onboarding -> onboarding=1
        st1 = parse_qs(urlparse(client.get("/api/auth/google/login?format=json").get_json()["auth_url"]).query)["state"][0]
        cb1 = client.get(f"/api/auth/google/callback?code=c1&state={st1}")
        assert cb1.status_code == 302
        assert "google_auth=success" in cb1.headers["Location"]
        assert "onboarding=1" in cb1.headers["Location"]
        assert client.get("/api/auth/me").get_json()["user"]["needs_onboarding"] is True

        # Complete onboarding -> subsequent Google sign-in does NOT set onboarding=1
        prof_res = client.post(
            "/api/auth/profile",
            headers={"Origin": "http://localhost"},
            json={"name": "Le Hybrid", "dob": "10/10/1999", "phone_number": "0909123456", "complete_onboarding": True},
        )
        assert prof_res.status_code == 200
        assert prof_res.get_json()["user"]["needs_onboarding"] is False

        st2 = parse_qs(urlparse(client.get("/api/auth/google/login?format=json").get_json()["auth_url"]).query)["state"][0]
        cb2 = client.get(f"/api/auth/google/callback?code=c2&state={st2}")
        assert cb2.status_code == 302
        assert "google_auth=success" in cb2.headers["Location"]
        assert "onboarding=1" not in cb2.headers["Location"]
    finally:
        with flask_app.app_context():
            db.session.remove()
            db.drop_all()
        tmpdir.cleanup()
