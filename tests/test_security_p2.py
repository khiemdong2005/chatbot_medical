"""
tests/test_security_p2.py
Suite kiểm thử an ninh chuyên sâu cho các lỗ hổng P2 (Phase 8.2 Hardening):
  1. CSRF Protection (FIND-05): Kiểm tra Origin / Referer fallback trên cả Flask và FastAPI.
  2. Session Lifetime & Fixation (FIND-07): Thời gian sống phiên rõ ràng và làm sạch session cũ khi login.
  3. Logout Cookie Invalidation (FIND-07): Xóa session và phát sinh header xóa cookie.
  4. Login Brute-force Rate Limiting (FIND-06): Giới hạn 5 lần thử sai / 5 phút per IP + identifier.
  5. Chat Rate Limiting Identity: Ưu tiên user_id > guest_token > client_ip.
  6. Rate Limit Performance: Đảm bảo độ trễ kiểm tra dưới 1 miligiây.
"""
import time
from datetime import timedelta
import pytest
from starlette.testclient import TestClient

from core.main_fastapi import app as fastapi_app, flask_app_instance
from core.models import db, User
from core.rate_limit_service import rate_limit_service
from core.settings import get_settings


# ==============================================================================
# FIXTURES & HELPERS
# ==============================================================================

@pytest.fixture
def clean_rate_limits():
    """Làm sạch bộ nhớ rate limiting trước mỗi bài test."""
    rate_limit_service.clear_all()
    yield
    rate_limit_service.clear_all()


@pytest.fixture
def p2_test_user(test_app):
    """Khởi tạo tài khoản mẫu dùng cho kiểm thử CSRF và Brute-force."""
    with test_app.app_context():
        user = User.query.filter_by(email="p2_user@test.medimind").first()
        if not user:
            user = User(
                email="p2_user@test.medimind",
                full_name="Người dùng P2 Test",
                role="patient"
            )
            user.set_password("MatKhauP2Chuan123@")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        user_email = user.email
        user_role = user.role

    class UserDTO:
        id = user_id
        email = user_email
        role = user_role
        password = "MatKhauP2Chuan123@"

    return UserDTO()


def make_signed_session_cookie(user_id: int, user_role: str = "patient") -> str:
    """Tạo Flask session cookie có chữ ký hợp lệ."""
    serializer = flask_app_instance.session_interface.get_signing_serializer(flask_app_instance)
    return serializer.dumps({"user_id": user_id, "user_role": user_role})


# ==============================================================================
# 1. CSRF ORIGIN & REFERER PROTECTION TESTS (FIND-05)
# ==============================================================================

class TestCSRFProtection:
    """Kiểm thử cơ chế bảo vệ CSRF trên các endpoint thay đổi trạng thái."""

    def test_flask_trusted_origin_allowed(self, test_app, p2_test_user):
        """Flask mutating request với Origin tin cậy (http://localhost:5000) -> Cho phép."""
        client = test_app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = p2_test_user.id
            sess["user_role"] = "patient"

        res = client.post(
            "/api/auth/profile",
            headers={"Origin": "http://localhost:5000"},
            json={"full_name": "Tên Đã Đổi"}
        )
        assert res.status_code == 200

    def test_flask_untrusted_origin_rejected(self, test_app, p2_test_user):
        """Flask mutating request với Origin độc hại (http://evil-attacker.io) -> 403 FORBIDDEN."""
        client = test_app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = p2_test_user.id
            sess["user_role"] = "patient"

        res = client.post(
            "/api/auth/profile",
            headers={"Origin": "http://evil-attacker.io"},
            json={"full_name": "Tên Hacker"}
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert "Origin" in data["error"]["message"]

    def test_flask_trusted_referer_when_origin_missing_allowed(self, test_app, p2_test_user):
        """Flask: Khi Origin vắng mặt nhưng Referer hợp lệ (http://localhost:5000/profile) -> Cho phép."""
        client = test_app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = p2_test_user.id
            sess["user_role"] = "patient"

        res = client.post(
            "/api/auth/profile",
            headers={"Referer": "http://localhost:5000/profile"},
            json={"full_name": "Tên Qua Referer"}
        )
        assert res.status_code == 200

    def test_flask_untrusted_referer_when_origin_missing_rejected(self, test_app, p2_test_user):
        """Flask: Khi Origin vắng mặt nhưng Referer từ trang độc hại -> 403 FORBIDDEN."""
        client = test_app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = p2_test_user.id
            sess["user_role"] = "patient"

        res = client.post(
            "/api/auth/profile",
            headers={"Referer": "http://evil-site.com/exploit.html"},
            json={"full_name": "Tên Hacker"}
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert "Referer" in data["error"]["message"]

    def test_flask_origin_and_referer_missing_on_session_request_rejected(self, test_app, p2_test_user):
        """Flask: Khi cả Origin và Referer đều vắng mặt trên request mang Session -> 403 CSRF Protection."""
        client = test_app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = p2_test_user.id
            sess["user_role"] = "patient"

        # Gửi POST không kèm bất kỳ header Origin hay Referer nào
        res = client.post(
            "/api/auth/profile",
            json={"full_name": "Tên Bị Chặn"}
        )
        assert res.status_code == 403
        data = res.get_json()
        assert data["error"]["code"] == "FORBIDDEN"
        assert "Origin hoặc Referer" in data["error"]["message"]

    def test_fastapi_trusted_origin_allowed(self, p2_test_user):
        """FastAPI native endpoint với Origin tin cậy -> Cho phép."""
        fastapi_client = TestClient(fastapi_app)
        cookie = make_signed_session_cookie(p2_test_user.id)
        fastapi_client.cookies.set("session", cookie)

        res = fastapi_client.post(
            "/api/appointments",
            headers={"origin": "http://localhost:8000"},
            json={
                "facility_id": "test_fac",
                "facility_name": "Bệnh viện Bạch Mai",
                "department": "Khoa Nội",
                "appointment_date": "2026-12-01",
                "appointment_time": "09:00",
                "patient_name": "Nguyễn Văn Test",
                "patient_phone": "0912345678"
            }
        )
        assert res.status_code in (200, 201)

    def test_fastapi_untrusted_origin_rejected(self, p2_test_user):
        """FastAPI native endpoint với Origin độc hại -> 403 FORBIDDEN."""
        fastapi_client = TestClient(fastapi_app)
        cookie = make_signed_session_cookie(p2_test_user.id)
        fastapi_client.cookies.set("session", cookie)

        res = fastapi_client.post(
            "/api/appointments",
            headers={"origin": "http://attacker-controlled.net"},
            json={"facility_id": "test_fac"}
        )
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"

    def test_fastapi_trusted_referer_allowed(self, p2_test_user):
        """FastAPI: Origin vắng mặt nhưng Referer tin cậy -> Cho phép."""
        fastapi_client = TestClient(fastapi_app)
        cookie = make_signed_session_cookie(p2_test_user.id)
        fastapi_client.cookies.set("session", cookie)

        res = fastapi_client.post(
            "/api/appointments",
            headers={"referer": "http://localhost:8000/appointments"},
            json={
                "facility_id": "test_fac",
                "facility_name": "Bệnh viện Bạch Mai",
                "department": "Khoa Nội",
                "appointment_date": "2026-12-01",
                "appointment_time": "09:00",
                "patient_name": "Nguyễn Văn Test",
                "patient_phone": "0912345678"
            }
        )
        assert res.status_code in (200, 201)

    def test_fastapi_untrusted_referer_rejected(self, p2_test_user):
        """FastAPI: Origin vắng mặt nhưng Referer độc hại -> 403 FORBIDDEN."""
        fastapi_client = TestClient(fastapi_app)
        cookie = make_signed_session_cookie(p2_test_user.id)
        fastapi_client.cookies.set("session", cookie)

        res = fastapi_client.post(
            "/api/appointments",
            headers={"referer": "http://evil-attacker.io/page"},
            json={"facility_id": "test_fac"}
        )
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"

    def test_fastapi_missing_origin_and_referer_on_session_request_rejected(self, p2_test_user):
        """FastAPI: Cả Origin và Referer vắng mặt trên request có session -> 403 FORBIDDEN."""
        fastapi_client = TestClient(fastapi_app)
        cookie = make_signed_session_cookie(p2_test_user.id)
        fastapi_client.cookies.set("session", cookie)

        res = fastapi_client.post(
            "/api/appointments",
            json={"facility_id": "test_fac"}
        )
        assert res.status_code == 403
        data = res.json()
        assert data["error"]["code"] == "FORBIDDEN"

    def test_safe_methods_unaffected_by_csrf(self):
        """GET, HEAD, OPTIONS không bị kiểm tra CSRF Origin/Referer."""
        fastapi_client = TestClient(fastapi_app)
        # GET không có Origin/Referer
        res_get = fastapi_client.get("/health")
        assert res_get.status_code == 200

        # OPTIONS preflight request
        res_options = fastapi_client.options("/api/chat", headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST"
        })
        assert res_options.status_code == 200


# ==============================================================================
# 2. SESSION LIFETIME & FIXATION HARDENING (FIND-07)
# ==============================================================================

class TestSessionHardening:
    """Kiểm thử thời gian sống phiên và cơ chế chống Session Fixation."""

    def test_session_lifetime_configured_explicitly(self, test_app):
        """Xác nhận PERMANENT_SESSION_LIFETIME được thiết lập theo settings (120 phút)."""
        settings = get_settings()
        expected = timedelta(minutes=settings.security.session_lifetime_minutes)
        assert test_app.config["PERMANENT_SESSION_LIFETIME"] == expected
        assert test_app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert test_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    def test_login_session_fixation_protection(self, test_app, p2_test_user, clean_rate_limits):
        """Khi đăng nhập thành công, các session keys cũ phải bị làm sạch hoàn toàn (Session Fixation Prevention)."""
        client = test_app.test_client()
        client.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"

        # Giả lập kẻ tấn công gài trước dữ liệu vào session ẩn danh
        with client.session_transaction() as sess:
            sess["attacker_pre_set_key"] = "malicious_token_123"
            sess["stale_guest_data"] = "old_data"

        # Thực hiện đăng nhập hợp lệ
        res = client.post("/api/auth/login", json={
            "identifier": "p2_user@test.medimind",
            "password": "MatKhauP2Chuan123@"
        })
        assert res.status_code == 200

        # Kiểm tra session sau đăng nhập
        with client.session_transaction() as sess:
            assert sess["user_id"] == p2_test_user.id
            assert sess["user_role"] == "patient"
            # Các giá trị session cũ trước khi đăng nhập PHẢI BỊ XÓA
            assert "attacker_pre_set_key" not in sess
            assert "stale_guest_data" not in sess

    def test_logout_clears_session_and_expires_cookie(self, test_app, p2_test_user):
        """Đăng xuất phải xóa rỗng session trên server và gửi lệnh xóa cookie về client."""
        client = test_app.test_client()
        client.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"

        with client.session_transaction() as sess:
            sess["user_id"] = p2_test_user.id
            sess["user_role"] = "patient"

        res = client.post("/api/auth/logout")
        assert res.status_code == 200

        # 1. Session dictionary phải rỗng
        with client.session_transaction() as sess:
            assert "user_id" not in sess

        # 2. Header Set-Cookie phải phát sinh lệnh xóa cookie (Expires in past hoặc Max-Age=0)
        set_cookie = res.headers.get("Set-Cookie", "")
        assert "session=" in set_cookie
        assert ("Expires=" in set_cookie or "Max-Age=0" in set_cookie)


# ==============================================================================
# 3. RATE LIMITING & BRUTE-FORCE PROTECTION (FIND-06)
# ==============================================================================

class TestRateLimitingService:
    """Kiểm thử phòng chống tấn công dò mật khẩu và giới hạn tần suất yêu cầu."""

    def test_login_brute_force_rate_limited(self, test_app, p2_test_user, clean_rate_limits):
        """Thử sai mật khẩu 5 lần liên tiếp -> Lần thứ 6 bị khóa 429 RATE_LIMITED."""
        client = test_app.test_client()
        client.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"

        # 5 lần thử sai đầu tiên -> nhận 401
        for _ in range(5):
            res = client.post("/api/auth/login", json={
                "identifier": "p2_user@test.medimind",
                "password": "WrongPassword999@"
            })
            assert res.status_code == 401

        # Lần thứ 6 -> Nhận 429 RATE_LIMITED
        res_blocked = client.post("/api/auth/login", json={
            "identifier": "p2_user@test.medimind",
            "password": "WrongPassword999@"
        })
        assert res_blocked.status_code == 429
        data = res_blocked.get_json()
        assert data["error"]["code"] == "RATE_LIMITED"
        assert "tạm khóa 5 phút" in data["error"]["message"]

    def test_login_success_resets_attempt_counter(self, test_app, p2_test_user, clean_rate_limits):
        """Nhập sai vài lần nhưng sau đó nhập đúng -> Bộ đếm sai được reset."""
        client = test_app.test_client()
        client.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"

        # Nhập sai 2 lần
        for _ in range(2):
            client.post("/api/auth/login", json={
                "identifier": "p2_user@test.medimind",
                "password": "WrongPassword@"
            })

        # Nhập đúng -> Đăng nhập thành công
        res_ok = client.post("/api/auth/login", json={
            "identifier": "p2_user@test.medimind",
            "password": "MatKhauP2Chuan123@"
        })
        assert res_ok.status_code == 200

        # Thử lại mật khẩu sai -> Bộ đếm bắt đầu lại từ đầu (nhận 401, không bị 429)
        res_again = client.post("/api/auth/login", json={
            "identifier": "p2_user@test.medimind",
            "password": "WrongAgain@"
        })
        assert res_again.status_code == 401

    def test_chat_rate_limit_identity_strategy(self):
        """Kiểm tra chiến lược phân cấp identity: user_id > guest_token > IP."""
        # 1. Có cả 3 -> Lấy user_id
        id1 = rate_limit_service.get_chat_identity(user_id=42, guest_token="gst_123", client_ip="10.0.0.1")
        assert id1 == "user:42"

        # 2. Không có user_id -> Lấy guest_token
        id2 = rate_limit_service.get_chat_identity(user_id=None, guest_token="gst_123", client_ip="10.0.0.1")
        assert id2 == "guest:gst_123"

        # 3. Chỉ có IP -> Lấy IP
        id3 = rate_limit_service.get_chat_identity(user_id=None, guest_token=None, client_ip="10.0.0.1")
        assert id3 == "ip:10.0.0.1"

    def test_rate_limit_performance_sub_millisecond(self, clean_rate_limits):
        """Đo đạc hiệu năng Rate Limiting: 1,000 lần kiểm tra trong RAM phải hoàn tất dưới 50ms (< 0.05ms/op)."""
        start = time.perf_counter()
        for i in range(1000):
            rate_limit_service.check_chat_rate_limit(f"bench_user_{i % 10}", max_requests=1000, window_seconds=60)
        elapsed = time.perf_counter() - start

        # 1,000 iterations phải dưới 0.05 giây (50ms)
        assert elapsed < 0.05, f"Rate limiting quá chậm: {elapsed:.4f}s cho 1,000 lần"
        avg_microsecond = (elapsed / 1000) * 1_000_000
        print(f"\n[BENCHMARK] Rate-limit average latency: {avg_microsecond:.2f} microseconds per check.")
