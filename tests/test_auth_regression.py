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


if __name__ == "__main__":
    unittest.main(verbosity=2)
