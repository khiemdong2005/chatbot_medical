"""
tests/test_user_preferences.py
Kiểm thử toàn diện tính năng Cài đặt cá nhân hóa (STT #39):
1. Bảo vệ RBAC: GET/PUT /api/auth/preferences yêu cầu phiên đăng nhập (401).
2. Giá trị mặc định an toàn & lưu bền vững vào cột User.preferences trên CSDL.
3. Trả kèm preferences trong /api/auth/me và /api/auth/login.
4. Kiểm định đầu vào chặt chẽ (lang, timezone, date_format, push_notif -> 400 nếu sai).
5. Migration 2026_11_25_user_preferences_json tự động bổ sung cột preferences trên DB cũ.
6. Xác minh hợp đồng Frontend: đọc lại medimind_settings, gọi /api/auth/preferences, xin quyền Notification, formatUserDate.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app import create_app
from core.shared.migrations import run_migrations
from core.shared.models import DEFAULT_USER_PREFERENCES, User, db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def prefs_client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        user = User(email="prefs.user@example.com", full_name="Lê Minh Anh", role="patient")
        user.set_password("StrongPass123")
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    yield app, client


def test_preferences_require_authentication(prefs_client):
    _, client = prefs_client

    res_get = client.get("/api/auth/preferences")
    assert res_get.status_code == 401

    res_put = client.put(
        "/api/auth/preferences",
        json={"lang": "en", "timezone": "UTC+9"},
        headers={"Origin": "http://localhost"},
    )
    assert res_put.status_code == 401


def test_preferences_get_update_persist_and_expose_in_auth_me(prefs_client):
    _, client = prefs_client
    csrf = {"Origin": "http://localhost"}

    login_res = client.post(
        "/api/auth/login",
        json={"identifier": "prefs.user@example.com", "password": "StrongPass123"},
    )
    assert login_res.status_code == 200
    assert login_res.get_json()["user"]["preferences"] == DEFAULT_USER_PREFERENCES

    # GET mặc định
    res_get = client.get("/api/auth/preferences")
    assert res_get.status_code == 200
    assert res_get.get_json()["preferences"] == DEFAULT_USER_PREFERENCES

    # PUT cập nhật (hỗ trợ cả snake_case)
    res_put = client.put(
        "/api/auth/preferences",
        json={
            "lang": "en",
            "timezone": "UTC+9",
            "date_format": "YYYY-MM-DD",
            "push_notif": False,
        },
        headers=csrf,
    )
    assert res_put.status_code == 200
    updated = res_put.get_json()["preferences"]
    assert updated == {
        "lang": "en",
        "timezone": "UTC+9",
        "date_format": "YYYY-MM-DD",
        "push_notif": False,
    }

    # Xác nhận bền vững qua GET /api/auth/preferences và GET /api/auth/me
    assert client.get("/api/auth/preferences").get_json()["preferences"] == updated
    me_data = client.get("/api/auth/me").get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["preferences"] == updated

    # Hỗ trợ cả camelCase
    res_camel = client.put(
        "/api/auth/preferences",
        json={"dateFormat": "MM/DD/YYYY", "pushNotif": True},
        headers=csrf,
    )
    assert res_camel.status_code == 200
    assert res_camel.get_json()["preferences"]["date_format"] == "MM/DD/YYYY"
    assert res_camel.get_json()["preferences"]["push_notif"] is True


def test_preferences_reject_invalid_values(prefs_client):
    _, client = prefs_client
    csrf = {"Origin": "http://localhost"}

    client.post(
        "/api/auth/login",
        json={"identifier": "prefs.user@example.com", "password": "StrongPass123"},
    )

    for bad_payload in (
        {"lang": "fr"},
        {"timezone": "Mars/Olympus"},
        {"date_format": "DD.MM.YY"},
        {"push_notif": "yes"},
    ):
        res = client.put("/api/auth/preferences", json=bad_payload, headers=csrf)
        assert res.status_code == 400
        assert res.get_json()["success"] is False

    # Giá trị trong DB không bị ghi hỏng
    assert client.get("/api/auth/preferences").get_json()["preferences"] == DEFAULT_USER_PREFERENCES


def test_migration_adds_preferences_column_to_legacy_users_table():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(120) NOT NULL,
                role VARCHAR(20) DEFAULT 'patient'
            );
        """))
        conn.execute(text("CREATE TABLE medical_appointments (id INTEGER PRIMARY KEY, note TEXT)"))

    run_migrations(engine)
    # Chạy lại lần 2 xác nhận idempotent
    run_migrations(engine)

    cols = {col["name"] for col in inspect(engine).get_columns("users")}
    assert "preferences" in cols


def test_frontend_preferences_read_sync_and_push_permission_contract():
    js_text = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "localStorage.getItem('medimind_settings')" in js_text
    assert "fetch('/api/auth/preferences'" in js_text
    assert "Notification.requestPermission()" in js_text
    assert "window.formatUserDate = formatUserDate" in js_text
    assert "PREFERENCES_UPDATED" in js_text
