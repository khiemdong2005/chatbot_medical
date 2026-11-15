import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["SECRET_KEY"] = "test-secret-key-32bytes-long-for-testing"
os.environ["SEED_DEMO_ACCOUNTS"] = "false"
os.environ["FLASK_DEBUG"] = "0"

from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

from app import create_app
from core.migrations import rollback_auth_identity_migration, run_migrations
from core.models import (
    AuthIdentity,
    ClinicalConsultation,
    MedicalDocument,
    User,
    db,
)
from core.cache_service import cache_service
from core.otp_service import otp_manager


class AuthSystemRegressionTest(unittest.TestCase):
    """Kiểm thử hồi quy toàn diện 15 kịch bản chuẩn hóa Authentication & Migration."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.uploads_dir = Path(self.tmp_dir.name) / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self.tmp_dir.name) / "test_auth.db"

        # Xóa bộ nhớ đệm rate-limit và OTP trước mỗi test
        if hasattr(cache_service, "_memory_cache"):
            cache_service._memory_cache.clear()
        otp_manager._store.clear()
        otp_manager._verified_store.clear()

        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.db_path}",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "SECRET_KEY": "test-secret-key-for-auth-regression",
                "SESSION_COOKIE_SECURE": False,
                "UPLOAD_FOLDER": str(self.uploads_dir),
            }
        )
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()
        self.tmp_dir.cleanup()

    def test_01_register_new_email_and_login(self):
        """1 & 3. Đăng ký Email mới (chuẩn hóa chữ thường) và đăng nhập Email hợp lệ."""
        res = self.client.post(
            "/api/auth/register",
            json={
                "identifier": "  Patient.One@Gmail.COM ",
                "password": "StrongPassword123!",
                "full_name": "Nguyễn Văn Một",
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["email"], "patient.one@gmail.com")
        self.assertEqual(data["user"]["phone_number"], "")

        user = User.query.filter_by(email="patient.one@gmail.com").first()
        self.assertIsNotNone(user)
        self.assertIsNone(user.phone_number)
        identity = AuthIdentity.query.filter_by(
            user_id=user.id, provider="email", provider_subject="patient.one@gmail.com"
        ).first()
        self.assertIsNotNone(identity)

        # Đăng nhập lại bằng chữ hoa/khoảng trắng
        self.client.post("/api/auth/logout")
        login_res = self.client.post(
            "/api/auth/login",
            json={"identifier": "PATIENT.ONE@gmail.com", "password": "StrongPassword123!"},
        )
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.get_json()["user"]["id"], user.id)

    def test_02_register_new_phone_no_synthetic_email_and_login(self):
        """2 & 4. Đăng ký SĐT mới (email = NULL, phone_number = E.164, tuyệt đối không tạo @phone.medimind) và đăng nhập SĐT."""
        res = self.client.post(
            "/api/auth/register",
            json={
                "identifier": "0987656789",
                "password": "PhonePassword123!",
                "full_name": "Bệnh Nhân SĐT",
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["email"], "")
        self.assertEqual(data["user"]["phone_number"], "+84987656789")
        self.assertEqual(data["user"]["display_account"], "+84987656789")
        self.assertTrue(data["user"]["is_phone_account"])

        # Kiểm tra trực tiếp trong DB: email phải là NULL, phone_number là +84987656789
        user = db.session.get(User, data["user"]["id"])
        self.assertIsNone(user.email)
        self.assertEqual(user.phone_number, "+84987656789")
        self.assertEqual(
            User.query.filter(User.email.like("%@phone.medimind%")).count(), 0
        )

        # Đăng nhập bằng cả định dạng nội địa 0987... và quốc tế +84987...
        for login_input in ("0987656789", "+84987656789", "84987656789"):
            self.client.post("/api/auth/logout")
            login_res = self.client.post(
                "/api/auth/login",
                json={"identifier": login_input, "password": "PhonePassword123!"},
            )
            self.assertEqual(login_res.status_code, 200, f"Failed for {login_input}")
            self.assertEqual(login_res.get_json()["user"]["id"], user.id)

    def test_03_google_oidc_login_and_invalid_token_rejection(self):
        """5 & 11. Đăng nhập Google OIDC hợp lệ qua `sub` và từ chối Google token giả/sai iss/aud/exp."""
        client_id = "test-google-client-id.apps.googleusercontent.com"
        valid_claims = {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": "google-oidc-sub-999888777",
            "email": "google.user@gmail.com",
            "email_verified": True,
            "name": "Google OIDC User",
            "exp": int(time.time()) + 3600,
        }

        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": client_id}):
            res = self.client.post(
                "/api/auth/google",
                json={"credential": "mock-valid-jwt-token", "_mock_token_info": valid_claims},
            )
            self.assertEqual(res.status_code, 200)
            user_data = res.get_json()["user"]
            user = db.session.get(User, user_data["id"])
            self.assertEqual(user.google_sub, "google-oidc-sub-999888777")
            # Không lưu mật khẩu Google
            self.assertFalse(user.has_usable_password())

            # Token hết hạn -> Bị từ chối 401
            expired_claims = dict(valid_claims, exp=int(time.time()) - 10)
            bad_res = self.client.post(
                "/api/auth/google",
                json={"credential": "expired-jwt", "_mock_token_info": expired_claims},
            )
            self.assertEqual(bad_res.status_code, 401)

            # Sai audience -> Bị từ chối 403
            wrong_aud_claims = dict(valid_claims, aud="other-app.apps.googleusercontent.com")
            aud_res = self.client.post(
                "/api/auth/google",
                json={"credential": "wrong-aud-jwt", "_mock_token_info": wrong_aud_claims},
            )
            self.assertEqual(aud_res.status_code, 403)

            # Email chưa xác minh -> Bị từ chối 401
            unverified_claims = dict(
                valid_claims, sub="sub-2", email="unv@gmail.com", email_verified=False
            )
            unv_res = self.client.post(
                "/api/auth/google",
                json={"credential": "unverified-jwt", "_mock_token_info": unverified_claims},
            )
            self.assertEqual(unv_res.status_code, 401)

    def test_04_legacy_migration_preserves_100_percent_data_and_rollback(self):
        """6 & 14. Migration tài khoản cũ (synthetic email) bảo toàn 100% user_id, password_hash, dữ liệu y tế và hỗ trợ rollback."""
        mig_path = Path(self.tmp_dir.name) / "legacy_mig.db"
        engine = create_engine(f"sqlite:///{mig_path}")

        pw_hash_admin = generate_password_hash("AdminSecret123!")
        pw_hash_phone = generate_password_hash("LegacyPhonePass123!")

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email VARCHAR(120) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        full_name VARCHAR(120) NOT NULL,
                        role VARCHAR(20) DEFAULT 'patient',
                        phone_number VARCHAR(20)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE medical_documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_id INTEGER NOT NULL REFERENCES users(id),
                        title VARCHAR(255)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO users (id, email, password_hash, full_name, role, phone_number)
                    VALUES
                        (1, 'sre.admin@medimind.vn', :pw1, 'SRE Admin', 'admin', '0987654321'),
                        (3, '0987656789@phone.medimind.vn', :pw2, 'Legacy Phone User', 'patient', '0987656789')
                    """
                ),
                {"pw1": pw_hash_admin, "pw2": pw_hash_phone},
            )
            conn.execute(
                text("INSERT INTO medical_documents (id, owner_id, title) VALUES (10, 3, 'Đơn thuốc cũ')")
            )

        try:
            # Chạy migration
            run_migrations(engine)

            with engine.connect() as conn:
                u1 = conn.execute(
                    text("SELECT id, email, phone_number, password_hash FROM users WHERE id = 1")
                ).fetchone()
                u3 = conn.execute(
                    text("SELECT id, email, phone_number, password_hash FROM users WHERE id = 3")
                ).fetchone()
                doc = conn.execute(
                    text("SELECT id, owner_id, title FROM medical_documents WHERE id = 10")
                ).fetchone()
                fk_errors = conn.execute(text("PRAGMA foreign_key_check")).fetchall()

            self.assertEqual(u1, (1, "sre.admin@medimind.vn", "+84987654321", pw_hash_admin))
            self.assertEqual(u3, (3, None, "+84987656789", pw_hash_phone))
            self.assertEqual(doc, (10, 3, "Đơn thuốc cũ"))
            self.assertEqual(fk_errors, [])

            # Kiểm tra rollback phục hồi nguyên trạng
            rollback_ok = rollback_auth_identity_migration(engine)
            self.assertTrue(rollback_ok)
            with engine.connect() as conn:
                u3_rb = conn.execute(
                    text("SELECT id, email, phone_number, password_hash FROM users WHERE id = 3")
                ).fetchone()
            self.assertEqual(
                u3_rb, (3, "0987656789@phone.medimind.vn", "0987656789", pw_hash_phone)
            )
        finally:
            engine.dispose()

    def test_05_account_with_both_email_and_phone_and_linking(self):
        """7, 8 & 9. Tài khoản có cả Email + SĐT + Google và từ chối trùng lặp định danh."""
        # Đăng ký bằng SĐT trước
        res = self.client.post(
            "/api/auth/register",
            json={
                "identifier": "0912345678",
                "password": "MyPassword123!",
                "full_name": "Bệnh Nhân Đa Định Danh",
            },
        )
        self.assertEqual(res.status_code, 201)
        uid = res.get_json()["user"]["id"]

        # Liên kết thêm Email (yêu cầu xác minh mật khẩu hiện tại)
        link_email_res = self.client.post(
            "/api/auth/link-identity",
            json={
                "provider": "email",
                "identifier": "multi.user@medimind.vn",
                "current_password": "MyPassword123!",
            },
        )
        self.assertEqual(link_email_res.status_code, 200)
        self.assertEqual(link_email_res.get_json()["user"]["email"], "multi.user@medimind.vn")

        # Đăng ký tài khoản khác trùng Email hoặc trùng SĐT -> Phải bị chặn 409
        dup_phone = self.client.post(
            "/api/auth/register",
            json={"identifier": "+84912345678", "password": "OtherPassword123!"},
        )
        self.assertEqual(dup_phone.status_code, 409)

        dup_email = self.client.post(
            "/api/auth/register",
            json={"identifier": "MULTI.USER@medimind.vn", "password": "OtherPassword123!"},
        )
        self.assertEqual(dup_email.status_code, 409)

        # Cả Email và SĐT đều đăng nhập vào đúng cùng 1 user_id
        for ident in ("0912345678", "+84912345678", "multi.user@medimind.vn"):
            self.client.post("/api/auth/logout")
            r = self.client.post(
                "/api/auth/login", json={"identifier": ident, "password": "MyPassword123!"}
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["user"]["id"], uid)

    def test_06_wrong_password_anti_enumeration_and_rate_limit(self):
        """10. Đăng nhập sai mật khẩu trả thông báo chung chống dò tài khoản và khóa tạm thời khi brute-force."""
        self.client.post(
            "/api/auth/register",
            json={"identifier": "victim@medimind.vn", "password": "CorrectPassword123!"},
        )
        self.client.post("/api/auth/logout")

        r_nonexist = self.client.post(
            "/api/auth/login", json={"identifier": "nobody@medimind.vn", "password": "Wrong"}
        )
        r_wrongpw = self.client.post(
            "/api/auth/login", json={"identifier": "victim@medimind.vn", "password": "Wrong"}
        )
        self.assertEqual(r_nonexist.status_code, 401)
        self.assertEqual(r_wrongpw.status_code, 401)
        # Cùng một thông điệp lỗi để chống account enumeration
        self.assertEqual(r_nonexist.get_json()["error"], r_wrongpw.get_json()["error"])

        # Thử sai quá 5 lần -> Bị khóa 429
        for _ in range(5):
            self.client.post(
                "/api/auth/login", json={"identifier": "victim@medimind.vn", "password": "Wrong"}
            )
        r_locked = self.client.post(
            "/api/auth/login",
            json={"identifier": "victim@medimind.vn", "password": "CorrectPassword123!"},
        )
        self.assertEqual(r_locked.status_code, 429)

    def test_07_forgot_reset_and_change_password_without_losing_medical_records(self):
        """12, 13 & 14. Quên mật khẩu, đặt lại mật khẩu, đổi mật khẩu, giữ nguyên user_id và hồ sơ y tế."""
        reg = self.client.post(
            "/api/auth/register",
            json={"identifier": "0933445566", "password": "OldPassword123!", "full_name": "BN Khôi Phục"},
        )
        uid = reg.get_json()["user"]["id"]

        # Tạo bản ghi y tế gắn với user_id
        doc = MedicalDocument(
            storage_filename="don_thuoc_test.pdf",
            original_filename="don_thuoc.pdf",
            file_path="don_thuoc_test.pdf",
            file_size=512,
            file_type="PDF",
            mime_type="application/pdf",
            owner_id=uid,
        )
        db.session.add(doc)
        db.session.commit()

        # Đổi mật khẩu khi đang đăng nhập
        chg = self.client.post(
            "/api/auth/change-password",
            json={
                "old_password": "OldPassword123!",
                "new_password": "MiddlePassword123!",
                "confirm_password": "MiddlePassword123!",
            },
        )
        self.assertEqual(chg.status_code, 200)
        # Session hiện tại vẫn hợp lệ sau khi đổi mật khẩu
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.get_json()["user"]["id"], uid)

        # Quên mật khẩu & Reset mật khẩu
        self.client.post("/api/auth/logout")
        fp = self.client.post("/api/auth/forgot-password", json={"identifier": "0933445566"})
        self.assertEqual(fp.status_code, 200)
        dev_otp = fp.get_json().get("dev_otp")
        self.assertIsNotNone(dev_otp)

        rp = self.client.post(
            "/api/auth/reset-password",
            json={
                "identifier": "+84933445566",
                "code": dev_otp,
                "new_password": "FinalPassword123!",
            },
        )
        self.assertEqual(rp.status_code, 200)

        # Đăng nhập bằng mật khẩu mới -> user_id và bệnh án không đổi
        login_new = self.client.post(
            "/api/auth/login",
            json={"identifier": "0933445566", "password": "FinalPassword123!"},
        )
        self.assertEqual(login_new.status_code, 200)
        self.assertEqual(login_new.get_json()["user"]["id"], uid)
        self.assertEqual(MedicalDocument.query.filter_by(owner_id=uid).count(), 1)

    def test_08_prevent_account_takeover_on_google_collision_and_linking(self):
        """15. Chống Account Takeover: Không tự động gộp Google vào tài khoản mật khẩu sẵn có nếu chưa xác minh quyền sở hữu."""
        victim_reg = self.client.post(
            "/api/auth/register",
            json={
                "identifier": "victim.owner@gmail.com",
                "password": "VictimSecretPassword123!",
                "full_name": "Chủ Tài Khoản Thật",
            },
        )
        victim_id = victim_reg.get_json()["user"]["id"]
        self.client.post("/api/auth/logout")

        client_id = "test-google-client-id.apps.googleusercontent.com"
        colliding_claims = {
            "iss": "https://accounts.google.com",
            "aud": client_id,
            "sub": "google-sub-collision-111",
            "email": "victim.owner@gmail.com",
            "email_verified": True,
            "name": "Google Colliding Login",
            "exp": int(time.time()) + 3600,
        }

        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": client_id}):
            # Chưa đăng nhập -> Phải yêu cầu xác minh mật khẩu chủ sở hữu (409 ACCOUNT_LINK_VERIFICATION_REQUIRED)
            res_blocked = self.client.post(
                "/api/auth/google",
                json={"credential": "colliding-jwt", "_mock_token_info": colliding_claims},
            )
            self.assertEqual(res_blocked.status_code, 409)
            self.assertEqual(
                res_blocked.get_json()["code"], "ACCOUNT_LINK_VERIFICATION_REQUIRED"
            )

            # Kiểm tra tài khoản nạn nhân chưa bị gắn google_sub trái phép
            victim = db.session.get(User, victim_id)
            self.assertIsNone(victim.google_sub)

            # Khi chủ tài khoản cung cấp đúng mật khẩu xác minh -> Liên kết thành công
            res_verified = self.client.post(
                "/api/auth/google",
                json={
                    "credential": "colliding-jwt",
                    "_mock_token_info": colliding_claims,
                    "password": "VictimSecretPassword123!",
                },
            )
            self.assertEqual(res_verified.status_code, 200)
            victim = db.session.get(User, victim_id)
            self.assertEqual(victim.google_sub, "google-sub-collision-111")

    def test_07_google_oauth_no_hardcoded_accounts_and_requires_real_oauth(self):
        """Không bao giờ hiển thị danh sách Gmail cá nhân gắn cứng; khi có OAuth thì mở accounts.google.com, khi thiếu .env thì báo chưa cấu hình."""
        home_html = self.client.get("/").get_data(as_text=True)
        for leaked in (
            "google-account-modal",
            "startGoogleAccountSelection",
            "Mô phỏng trải nghiệm Google Identity",
        ):
            self.assertNotIn(leaked, home_html)

        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": ""}):
            unconf = self.client.get("/api/auth/google/login?format=json")
            self.assertEqual(unconf.status_code, 503)
            self.assertFalse(unconf.get_json()["configured"])
            spoof = self.client.post("/api/auth/google", json={"email": "anyone@gmail.com", "name": "Spoof"})
            self.assertEqual(spoof.status_code, 503)

        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "real-client.apps.googleusercontent.com",
                "GOOGLE_CLIENT_SECRET": "real-secret-xyz",
            },
        ):
            conf = self.client.get("/api/auth/google/login?format=json")
            self.assertEqual(conf.status_code, 200)
            body = conf.get_json()
            self.assertTrue(body["configured"])
            self.assertIn("https://accounts.google.com/o/oauth2/v2/auth", body["auth_url"])
            self.assertIn("prompt=select_account", body["auth_url"])

    def test_08_google_link_identity_requires_verified_oidc_and_booking_facilities_validation(self):
        """Liên kết Google đòi hỏi credential OIDC hợp lệ; đặt lịch chặn ngày quá khứ/SĐT sai; lọc Quận 1 không lọt Quận 10/11/12."""
        from datetime import datetime, timedelta

        reg = self.client.post(
            "/api/auth/register",
            json={
                "identifier": "link.guard@medimind.vn",
                "password": "SafePassword123!",
                "full_name": "Bệnh Nhân Kiểm Định",
            },
        )
        self.assertEqual(reg.status_code, 201)

        with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "medimind-client.apps.googleusercontent.com"}):
            spoof_link = self.client.post(
                "/api/auth/link-identity",
                json={"provider": "google", "google_sub": "spoofed-sub-999", "email": "spoof@gmail.com"},
            )
            self.assertEqual(spoof_link.status_code, 400)

            wrong_aud = self.client.post(
                "/api/auth/link-identity",
                json={
                    "provider": "google",
                    "credential": "wrong-aud-token",
                    "_mock_token_info": {
                        "iss": "https://accounts.google.com",
                        "aud": "evil.apps.googleusercontent.com",
                        "exp": 4102444800,
                        "email_verified": True,
                        "sub": "verified-sub-777",
                        "email": "link.guard@medimind.vn",
                    },
                },
            )
            self.assertEqual(wrong_aud.status_code, 403)

            ok_link = self.client.post(
                "/api/auth/link-identity",
                json={
                    "provider": "google",
                    "credential": "valid-google-token",
                    "_mock_token_info": {
                        "iss": "https://accounts.google.com",
                        "aud": "medimind-client.apps.googleusercontent.com",
                        "exp": 4102444800,
                        "email_verified": True,
                        "sub": "verified-sub-777",
                        "email": "link.guard@medimind.vn",
                    },
                },
            )
            self.assertEqual(ok_link.status_code, 200)

        past_appt = self.client.post(
            "/api/appointments",
            json={
                "facility_id": "1",
                "facility_name": "BV Đa Khoa",
                "appointment_date": "2000-01-01",
                "appointment_time": "09:00",
                "patient_name": "Bệnh Nhân Kiểm Định",
                "patient_phone": "0912345678",
            },
        )
        self.assertEqual(past_appt.status_code, 400)

        tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
        bad_phone_appt = self.client.post(
            "/api/appointments",
            json={
                "facility_id": "1",
                "facility_name": "BV Đa Khoa",
                "appointment_date": tomorrow,
                "appointment_time": "09:00",
                "patient_name": "Bệnh Nhân Kiểm Định",
                "patient_phone": "abc-invalid",
            },
        )
        self.assertEqual(bad_phone_appt.status_code, 400)

        ok_appt = self.client.post(
            "/api/appointments",
            json={
                "facility_id": "1",
                "facility_name": "BV Đa Khoa",
                "appointment_date": tomorrow,
                "appointment_time": "09:00",
                "patient_name": "Bệnh Nhân Kiểm Định",
                "patient_phone": "0912345678",
            },
        )
        self.assertEqual(ok_appt.status_code, 201)

        q1_res = self.client.get("/api/facilities?quan_huyen=Qu%E1%BA%ADn+1&limit=50")
        self.assertEqual(q1_res.status_code, 200)
        q1_items = q1_res.get_json()["data"]
        self.assertTrue(len(q1_items) > 0)
        for item in q1_items:
            self.assertEqual(item.get("quan_huyen"), "Quận 1")

        td_res = self.client.get("/api/facilities?quan_huyen=TP.+Th%E1%BB%A7+%C4%90%E1%BB%A9c&limit=20")
        self.assertEqual(td_res.status_code, 200)
        self.assertGreater(td_res.get_json()["total"], 0)

    def test_12_security_locked_account_csrf_csp_and_input_bounds(self):
        """19. Kiểm thử bảo mật tổng hợp: Khóa tài khoản tức thì, OTP purpose, Fetch-Metadata CSRF, CSP, CRLF & giới hạn đầu vào."""
        # 1. Chặn mục đích OTP trái phép & liên kết khi chưa đăng nhập (V-01)
        bad_otp = self.client.post("/api/auth/otp/send", json={"identifier": "a@b.com", "purpose": "admin_escalate"})
        self.assertEqual(bad_otp.status_code, 400)
        unauth_link_otp = self.client.post("/api/auth/otp/send", json={"identifier": "a@b.com", "purpose": "link_identity"})
        self.assertEqual(unauth_link_otp.status_code, 401)

        # 2. Tạo User A, tạo guest_token rồi chuyển sang User B -> không lộ guest_token cũ (V-09)
        reg_a = self.client.post(
            "/api/auth/register",
            json={"identifier": "sec.user.a@gmail.com", "password": "PasswordA123!", "full_name": "Sec User A"},
        )
        self.assertEqual(reg_a.status_code, 201)
        uid_a = reg_a.get_json()["user"]["id"]
        with self.client.session_transaction() as sess:
            sess["guest_token"] = "gst_user_a_private"

        reg_b = self.client.post(
            "/api/auth/register",
            json={"identifier": "sec.user.b@gmail.com", "password": "PasswordB123!", "full_name": "Sec User B"},
        )
        self.assertEqual(reg_b.status_code, 201)
        with self.client.session_transaction() as sess:
            self.assertNotEqual(sess.get("guest_token"), "gst_user_a_private")

        # 3. Khóa tài khoản User A -> thu hồi phiên tức thì & chặn OTP login_2fa / reset_pwd (V-01, V-09)
        self.client.post("/api/auth/login", json={"identifier": "sec.user.a@gmail.com", "password": "PasswordA123!"})
        from core.otp_service import otp_manager
        ok_req, _, _ = otp_manager.request_otp("sec.user.a@gmail.com", "email", purpose="login_2fa")
        self.assertTrue(ok_req)
        active_code = otp_manager.get_active_code("sec.user.a@gmail.com", "email")

        user_a = db.session.get(User, uid_a)
        user_a.account_status = "locked"
        db.session.commit()

        self.assertEqual(self.client.get("/api/appointments").status_code, 401)
        self.assertFalse(self.client.get("/api/auth/me").get_json()["authenticated"])
        self.assertEqual(
            self.client.post("/api/auth/otp/send", json={"identifier": "sec.user.a@gmail.com", "purpose": "login_2fa"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/otp/verify",
                json={"identifier": "sec.user.a@gmail.com", "channel": "email", "code": active_code, "purpose": "login_2fa"},
            ).status_code,
            403,
        )

        # 4. Fetch Metadata Cross-Site CSRF & CSP Directives (V-08, V-10)
        csrf_res = self.client.post(
            "/api/auth/logout",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(csrf_res.status_code, 403)
        csp = csrf_res.headers.get("Content-Security-Policy", "")
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertIn("form-action 'self'", csp)

        # 5. Giới hạn độ dài & ảnh lỗi tại /api/intake/message và /api/nutrition/analyze (V-05)
        self.assertEqual(
            self.client.post("/api/intake/message", json={"message": "x" * 2005}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/intake/message", json={"message": "Đau đầu", "image": "not_base64_!!!"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/nutrition/analyze", json={"condition": "c" * 505}).status_code,
            400,
        )

        # 6. Chống tiêm header SMTP CRLF (V-10)
        from core.email_service import EmailService
        self.assertEqual(EmailService._strip_crlf("victim@x.com\r\nBcc:leak@evil.com"), "victim@x.com  Bcc:leak@evil.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
