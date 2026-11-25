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


def test_frontend_first_login_onboarding_sync_contract():
    app_js = (PROJECT_ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "let isFirstLoginOnboarding = false;" in app_js
    assert "if (data.needs_onboarding || currentUser.needs_onboarding)" in app_js
    assert "openGoogleOnboardingModal(currentUser, false, { firstLogin: true })" in app_js
    assert "complete_onboarding: true" in app_js
    assert "(isPendingGoogleRegistration || isFirstLoginOnboarding) ? 'Xác nhận & Vào ứng dụng' : 'Lưu thông tin'" in app_js
