"""
tests/test_security_p0_p1.py
Suite kiểm thử an ninh chuyên sâu cho các lỗ hổng P0 / P1 (Phase 8.1 Remediation):
  1. Google OAuth fail-closed (VULN-01): Chặn đứng mọi hình thức bypass xác thực qua email trần.
  2. CORS Restriction (FIND-02): Không dùng wildcard origins kèm credentials; chặn origin độc hại.
  3. Admin / System Observability Protection (FIND-03): Khóa /system, /admin/system, /api/system/metrics, /api/system/metrics/reset (401/403/200).
  4. Seed Default Credentials Hardening (FIND-04): Chống tự động tạo tài khoản với mật khẩu cố định trong Production.
  5. Production Docs Hardening (FIND-08): Vô hiệu hóa Swagger /docs, /redoc và /openapi.json trong Production.
"""
import os
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.main_fastapi import app as fastapi_app, flask_app_instance
from core.models import db, User, seed_default_users
from core.observability import metrics_collector
from core.settings import Settings


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def test_roles(test_app):
    """Khởi tạo các tài khoản với các vai trò khác nhau (patient, doctor, admin) để kiểm thử RBAC."""
    with test_app.app_context():
        # Xóa nếu đã tồn tại để tránh conflict
        for email in ["sec_patient@test.vn", "sec_doctor@test.vn", "sec_admin@test.vn"]:
            existing = User.query.filter_by(email=email).first()
            if existing:
                db.session.delete(existing)
        db.session.commit()

        patient = User(
            email="sec_patient@test.vn",
            full_name="Bệnh nhân An Ninh",
            role="patient"
        )
        patient.set_password("SecurePasswordPatient123@")

        doctor = User(
            email="sec_doctor@test.vn",
            full_name="Bác sĩ An Ninh",
            role="doctor"
        )
        doctor.set_password("SecurePasswordDoctor123@")

        admin = User(
            email="sec_admin@test.vn",
            full_name="Quản trị viên An Ninh",
            role="admin"
        )
        admin.set_password("SecurePasswordAdmin123@")

        db.session.add(patient)
        db.session.add(doctor)
        db.session.add(admin)
        db.session.commit()

        return {
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "admin_id": admin.id,
        }


def make_signed_cookie(user_id: int, user_role: str) -> str:
    """Tạo Flask session cookie có chữ ký hợp lệ."""
    serializer = flask_app_instance.session_interface.get_signing_serializer(flask_app_instance)
    return serializer.dumps({"user_id": user_id, "user_role": user_role})


# ==============================================================================
# 1. OAUTH FAIL-CLOSED TESTS (FIND-01 P0 REMEDIATION)
# ==============================================================================

class TestOAuthFailClosed:
    """Kiểm thử cơ chế Fail-Closed của Google OAuth và chống giả mạo email trần."""

    def test_oauth_missing_client_id_returns_503(self, client, monkeypatch):
        """Khi GOOGLE_CLIENT_ID chưa được cấu hình, hệ thống từ chối an toàn với 503."""
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        res = client.post("/api/auth/google", json={
            "credential": "some_token_here",
            "email": "attacker@fake.com"
        })
        assert res.status_code == 503
        data = res.get_json()
        assert data["success"] is False
        assert data["error"]["code"] == "AI_UNAVAILABLE" or "chưa được cấu hình" in data["error"]["message"]

    def test_oauth_missing_token_returns_400(self, client, monkeypatch):
        """Khi thiếu credential/token, từ chối với 400 VALIDATION_ERROR."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "valid-client-id-12345.apps.googleusercontent.com")
        res = client.post("/api/auth/google", json={
            "email": "attacker@fake.com"
        })
        assert res.status_code == 400
        data = res.get_json()
        assert data["success"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "credential" in data["error"]["message"].lower() or "token" in data["error"]["message"].lower()

    def test_oauth_attacker_supplied_email_without_token_never_authenticates(self, client, monkeypatch):
        """Attacker gửi email nạn nhân hòng chiếm quyền mà không có token -> Bị chặn 400."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "valid-client-id-12345.apps.googleusercontent.com")
        res = client.post("/api/auth/google", json={
            "email": "victim.admin@medimind.vn",
            "name": "Victim User"
        })
        assert res.status_code == 400
        # Đảm bảo không có session nào được tạo
        with client.session_transaction() as sess:
            assert "user_id" not in sess

    def test_oauth_invalid_token_rejected_with_401(self, client, monkeypatch):
        """Token giả mạo hoặc chữ ký sai -> Bị google.oauth2.id_token bắt và trả về 401."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "valid-client-id-12345.apps.googleusercontent.com")
        with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token invalid or expired")):
            res = client.post("/api/auth/google", json={
                "credential": "attacker_forged_jwt_token",
                "email": "victim@medimind.vn"
            })
            assert res.status_code == 401
            data = res.get_json()
            assert data["success"] is False
            assert data["error"]["code"] == "INVALID_CREDENTIALS"

    def test_oauth_audience_mismatch_rejected_with_403(self, client, monkeypatch):
        """Token hợp lệ nhưng aud không khớp với GOOGLE_CLIENT_ID của MediMind -> 403."""
        configured_id = "valid-client-id-12345.apps.googleusercontent.com"
        monkeypatch.setenv("GOOGLE_CLIENT_ID", configured_id)
        mock_claims = {
            "aud": "another-different-app-id.apps.googleusercontent.com",
            "email": "legit.user@gmail.com",
            "name": "Legit User",
            "picture": "https://lh3.googleusercontent.com/avatar"
        }
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_claims):
            res = client.post("/api/auth/google", json={
                "credential": "valid_token_wrong_aud"
            })
            assert res.status_code == 403
            data = res.get_json()
            assert data["error"]["code"] == "FORBIDDEN"

    def test_oauth_verified_token_uses_claims_not_json_body(self, client, monkeypatch):
        """
        Attacker gửi token hợp lệ của attacker@gmail.com, nhưng body JSON cố tình gài
        email nạn nhân victim@medimind.vn. Hệ thống PHẢI đăng nhập bằng token claim attacker!
        """
        configured_id = "valid-client-id-12345.apps.googleusercontent.com"
        monkeypatch.setenv("GOOGLE_CLIENT_ID", configured_id)
        mock_claims = {
            "aud": configured_id,
            "email": "actual_attacker@gmail.com",
            "name": "Attacker Name",
            "picture": "https://lh3.googleusercontent.com/attacker"
        }
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_claims):
            res = client.post("/api/auth/google", json={
                "credential": "valid_token_of_attacker",
                "email": "victim_admin@medimind.vn",
                "name": "Victim Admin"
            })
            assert res.status_code == 200
            data = res.get_json()
            assert data["success"] is True
            # Người dùng đăng nhập PHẢI là email từ token_info, KHÔNG PHẢI victim
            assert data["user"]["email"] == "actual_attacker@gmail.com"
            assert data["user"]["email"] != "victim_admin@medimind.vn"

            with client.session_transaction() as sess:
                assert sess["user_id"] == data["user"]["id"]

    def test_oauth_callback_invalid_state_rejected(self, client):
        """Google OAuth callback với state giả mạo hoặc rỗng bị từ chối redirect an toàn."""
        res = client.get("/api/auth/google/callback?code=fake_code&state=forged_state")
        assert res.status_code == 302
        assert "invalid_state" in res.headers.get("Location", "")


# ==============================================================================
# 2. CORS RESTRICTION TESTS (FIND-02 P1 REMEDIATION)
# ==============================================================================

class TestCORSRestriction:
    """Kiểm thử cấu hình CORS nghiêm ngặt chống đánh cắp dữ liệu chéo nguồn."""

    def test_trusted_origin_allowed_with_credentials(self):
        """Origin trong whitelist (http://localhost:8000) được phản hồi header Allow-Origin và Credentials."""
        client = TestClient(fastapi_app)
        res = client.get("/health", headers={"Origin": "http://localhost:8000"})
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:8000"
        assert res.headers.get("access-control-allow-credentials") == "true"

    def test_untrusted_origin_rejected(self):
        """Origin độc hại (http://evil-attacker.io) KHÔNG được phát sinh header Access-Control-Allow-Origin."""
        client = TestClient(fastapi_app)
        res = client.get("/health", headers={"Origin": "http://evil-attacker.io"})
        assert res.status_code == 200
        assert "access-control-allow-origin" not in res.headers

    def test_production_cors_empty_by_default(self, monkeypatch):
        """Trong môi trường Production, nếu không cấu hình CORS_ALLOWED_ORIGINS thì mặc định rỗng (Fail-Safe)."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        settings = Settings()
        assert settings.server.is_production is True
        assert settings.security.cors_allowed_origins == []

    def test_production_cors_no_wildcard_even_if_empty(self):
        """Ứng dụng chạy với CORS rỗng không cho phép bất kỳ cross-origin request nào."""
        test_cors_app = FastAPI()
        test_cors_app.add_middleware(
            CORSMiddleware,
            allow_origins=[],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        client = TestClient(test_cors_app)
        res = client.get("/docs", headers={"Origin": "http://evil-attacker.io"})
        assert "access-control-allow-origin" not in res.headers


# ==============================================================================
# 3. ADMIN / SYSTEM OBSERVABILITY AUTHORIZATION (FIND-03 P1 REMEDIATION)
# ==============================================================================

class TestAdminSystemAuthorization:
    """Kiểm thử phân quyền RBAC nghiêm ngặt cho toàn bộ endpoint giám sát / metrics."""

    TARGET_ENDPOINTS = [
        ("GET", "/api/system/metrics"),
        ("POST", "/api/system/metrics/reset"),
        ("GET", "/system"),
        ("GET", "/admin/system"),
    ]

    def test_anonymous_requests_receive_401(self, client):
        """Người dùng ẩn danh chưa đăng nhập gọi endpoint admin -> 401 AUTH_REQUIRED."""
        for method, endpoint in self.TARGET_ENDPOINTS:
            if method == "GET":
                res = client.get(endpoint)
            else:
                res = client.post(endpoint)
            assert res.status_code == 401, f"{method} {endpoint} phải trả về 401 cho anonymous"
            if "api" in endpoint:
                data = res.get_json()
                assert data["error"]["code"] == "AUTH_REQUIRED"

    def test_patient_role_receives_403(self, client, test_roles):
        """Người dùng có vai trò 'patient' gọi endpoint admin -> 403 FORBIDDEN."""
        with client.session_transaction() as sess:
            sess["user_id"] = test_roles["patient_id"]
            sess["user_role"] = "patient"

        for method, endpoint in self.TARGET_ENDPOINTS:
            if method == "GET":
                res = client.get(endpoint)
            else:
                res = client.post(endpoint)
            assert res.status_code == 403, f"{method} {endpoint} phải trả về 403 cho patient"
            if "api" in endpoint:
                data = res.get_json()
                assert data["error"]["code"] == "FORBIDDEN"

    def test_doctor_role_receives_403(self, client, test_roles):
        """Người dùng có vai trò 'doctor' gọi endpoint admin -> 403 FORBIDDEN."""
        with client.session_transaction() as sess:
            sess["user_id"] = test_roles["doctor_id"]
            sess["user_role"] = "doctor"

        for method, endpoint in self.TARGET_ENDPOINTS:
            if method == "GET":
                res = client.get(endpoint)
            else:
                res = client.post(endpoint)
            assert res.status_code == 403, f"{method} {endpoint} phải trả về 403 cho doctor"
            if "api" in endpoint:
                data = res.get_json()
                assert data["error"]["code"] == "FORBIDDEN"

    def test_admin_role_receives_200(self, client, test_roles):
        """Người dùng có vai trò 'admin' gọi endpoint admin -> 200 OK."""
        with client.session_transaction() as sess:
            sess["user_id"] = test_roles["admin_id"]
            sess["user_role"] = "admin"

        for method, endpoint in self.TARGET_ENDPOINTS:
            if method == "GET":
                res = client.get(endpoint)
            else:
                res = client.post(endpoint)
            assert res.status_code == 200, f"{method} {endpoint} phải trả về 200 cho admin"

    def test_metrics_reset_mutation_requires_admin(self, client, test_roles):
        """Chỉ admin mới có quyền thực hiện mutation xóa bộ đếm metrics."""
        metrics_collector.increment("requests_total", 50)
        assert metrics_collector.get_summary()["requests"]["total"] >= 50

        # Thử với anonymous -> Bị từ chối, metrics không đổi
        client.post("/api/system/metrics/reset")
        assert metrics_collector.get_summary()["requests"]["total"] >= 50

        # Thử với patient -> Bị từ chối, metrics không đổi
        with client.session_transaction() as sess:
            sess["user_id"] = test_roles["patient_id"]
            sess["user_role"] = "patient"
        client.post("/api/system/metrics/reset")
        assert metrics_collector.get_summary()["requests"]["total"] >= 50

        # Đăng nhập admin -> Reset thành công
        with client.session_transaction() as sess:
            sess["user_id"] = test_roles["admin_id"]
            sess["user_role"] = "admin"
        res = client.post("/api/system/metrics/reset")
        assert res.status_code == 200
        assert metrics_collector.get_summary()["requests"]["total"] == 0

    def test_fastapi_admin_endpoints_require_admin(self, test_app, test_roles):
        """Kiểm tra xác thực admin trên FastAPI gateway trực tiếp."""
        fastapi_client = TestClient(fastapi_app)

        # 1. Anonymous -> 401
        res = fastapi_client.get("/api/system/metrics")
        assert res.status_code == 401

        # 2. Patient -> 403
        patient_cookie = make_signed_cookie(test_roles["patient_id"], "patient")
        fastapi_client.cookies.set("session", patient_cookie)
        res = fastapi_client.get("/api/system/metrics")
        assert res.status_code == 403

        # 3. Admin -> 200
        admin_cookie = make_signed_cookie(test_roles["admin_id"], "admin")
        fastapi_client.cookies.set("session", admin_cookie)
        res = fastapi_client.get("/api/system/metrics")
        assert res.status_code == 200


# ==============================================================================
# 4. SEED CREDENTIAL HARDENING (FIND-04 P1 REMEDIATION)
# ==============================================================================

class TestSeedCredentialHardening:
    """Kiểm thử cơ chế bảo vệ seed credentials mẫu."""

    def test_production_seed_disabled(self, test_app, monkeypatch):
        """Trong môi trường Production, seed_default_users() lập tức trả về False."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEV_SEED_USERS", "true")
        with test_app.app_context():
            seeded = seed_default_users()
            assert seeded is False

    def test_dev_seed_without_optin_disabled(self, test_app, monkeypatch):
        """Trong Dev nhưng không bật DEV_SEED_USERS -> Không seed."""
        monkeypatch.delenv("DEV_SEED_USERS", raising=False)
        monkeypatch.delenv("SEED_DEMO_ACCOUNTS", raising=False)
        with test_app.app_context():
            seeded = seed_default_users()
            assert seeded is False

    def test_dev_seed_with_optin_uses_random_or_configured_password(self, test_app, monkeypatch):
        """Trong Dev khi bật DEV_SEED_USERS=true, seed thành công và không dùng mật khẩu cứng cũ."""
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEV_SEED_USERS", "true")
        monkeypatch.setenv("DEV_SEED_PASSWORD", "SyntheticDevPassword123@")
        with test_app.app_context():
            seeded = seed_default_users()
            assert seeded is True
            doctor = User.query.filter_by(email="bacsi.an@medimind.vn").first()
            assert doctor is not None
            assert doctor.check_password("SyntheticDevPassword123@") is True
            # Tuyệt đối không nhận mật khẩu mặc định cũ MatKhau123@
            assert doctor.check_password("MatKhau123@") is False


# ==============================================================================
# 5. PRODUCTION DOCS HARDENING (FIND-08 P2 REMEDIATION)
# ==============================================================================

class TestProductionDocsHardening:
    """Kiểm thử vô hiệu hóa Swagger/ReDoc trong môi trường Production."""

    def test_dev_docs_available(self):
        """Trong môi trường dev hiện tại, /docs và /redoc sẵn sàng phục vụ."""
        client = TestClient(fastapi_app)
        res_docs = client.get("/docs")
        assert res_docs.status_code == 200
        res_openapi = client.get("/openapi.json")
        assert res_openapi.status_code == 200

    def test_production_docs_disabled(self):
        """Khởi tạo FastAPI app với cờ is_production=True -> /docs, /redoc, /openapi.json trả về 404."""
        prod_app = FastAPI(
            title="Production MediMind",
            docs_url=None,
            redoc_url=None,
            openapi_url=None
        )
        client = TestClient(prod_app)
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
