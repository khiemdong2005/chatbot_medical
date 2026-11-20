import io
import pytest
from core.models import db, User, MedicalDocument


def test_unauthenticated_cannot_update_profile(client, test_users):
    """Kiểm thử 1: Không đăng nhập không sửa được hồ sơ."""
    # Thử sửa hồ sơ khi không có session
    res = client.post("/api/auth/profile", json={
        "name": "Hacker Name",
        "gender": "Nữ"
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data["success"] is False
    assert "đăng nhập" in data["error"]


def test_cannot_hijack_profile_via_json_id(client, test_users):
    """Kiểm thử 1b: Kẻ tấn công không thể chiếm quyền sửa hồ sơ bằng id trong JSON."""
    user_a_id = test_users["user_a_id"]
    
    # Kẻ tấn công gửi id của User A trong JSON mà không có session
    res = client.post("/api/auth/profile", json={
        "id": user_a_id,
        "name": "Attacker Hijacked Name"
    })
    assert res.status_code == 401

    # Kiểm tra trong DB: tên User A không hề bị thay đổi
    user_a = db.session.get(User, user_a_id)
    assert user_a.full_name == "Nguyễn Văn A"


def test_unauthenticated_cannot_list_or_delete_documents(client):
    """Kiểm thử 1c: Không đăng nhập không liệt kê hoặc xóa tài liệu."""
    res_list = client.get("/api/scan-files")
    assert res_list.status_code == 401

    res_del = client.delete("/api/scan-files/1")
    assert res_del.status_code == 401


def test_user_a_cannot_access_or_delete_user_b_documents(client, test_users, temp_dirs):
    """Kiểm thử 2: User A không sửa/xóa tài liệu của user B."""
    user_a_id = test_users["user_a_id"]
    user_b_id = test_users["user_b_id"]

    # Tạo 1 tài liệu thuộc về User B
    with client.application.app_context():
        doc_b = MedicalDocument(
            storage_filename="secret_doc_user_b.pdf",
            original_filename="xet_nghiem_mau_b.pdf",
            file_path="secret_doc_user_b.pdf",
            file_size=1024,
            file_type="PDF",
            mime_type="application/pdf",
            owner_id=user_b_id
        )
        db.session.add(doc_b)
        db.session.commit()
        doc_b_id = doc_b.id

    # Đăng nhập với tư cách User A
    with client.session_transaction() as sess:
        sess["user_id"] = user_a_id
        sess["user_role"] = "patient"

    # User A liệt kê danh sách tài liệu -> Không được nhìn thấy tài liệu của User B
    res_list = client.get("/api/scan-files")
    assert res_list.status_code == 200
    files = res_list.get_json()["files"]
    assert len(files) == 0  # User A chưa có file nào

    # User A cố tình gửi yêu cầu xóa tài liệu của User B -> Bị từ chối (404)
    res_delete = client.delete(f"/api/scan-files/{doc_b_id}")
    assert res_delete.status_code == 404

    # Kiểm tra trong DB: Tài liệu của User B vẫn an toàn
    with client.application.app_context():
        doc_check = db.session.get(MedicalDocument, doc_b_id)
        assert doc_check is not None
        assert doc_check.owner_id == user_b_id


def test_public_registration_never_grants_doctor_or_admin(client):
    """Kiểm thử 2b: Client không thể tự cấp quyền doctor/admin khi đăng ký."""
    # Client gửi payload cố tình đòi role 'doctor'
    res = client.post("/api/auth/register", json={
        "identifier": "attacker.doctor@test.com",
        "password": "MatKhau123@",
        "full_name": "Kẻ mạo danh Bác sĩ",
        "role": "doctor"
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    # Vai trò bắt buộc phải là patient
    assert data["user"]["role"] == "patient"

    # Kiểm tra trong DB
    user = User.query.filter_by(email="attacker.doctor@test.com").first()
    assert user is not None
    assert user.role == "patient"

    # Thử đòi role 'admin'
    res_admin = client.post("/api/auth/register", json={
        "identifier": "attacker.admin@test.com",
        "password": "MatKhau123@",
        "full_name": "Kẻ mạo danh Admin",
        "role": "admin"
    })
    assert res_admin.status_code == 201
    user_admin = User.query.filter_by(email="attacker.admin@test.com").first()
    assert user_admin.role == "patient"


def test_prescription_scan_requires_login_and_links_owner(client, test_users):
    """Kiểm thử: Upload file lên /api/prescription/scan bắt buộc đăng nhập và lưu liên kết owner_id."""
    # 1. Chưa đăng nhập -> Trả 401
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    res_unauth = client.post(
        "/api/prescription/scan",
        data={"file": (io.BytesIO(png_bytes), "don_thuoc.png")},
        content_type="multipart/form-data"
    )
    assert res_unauth.status_code == 401

    # 2. Đã đăng nhập với User A -> Thành công và liên kết owner_id
    user_a_id = test_users["user_a_id"]
    with client.session_transaction() as sess:
        sess["user_id"] = user_a_id

    res_auth = client.post(
        "/api/prescription/scan",
        data={"file": (io.BytesIO(png_bytes), "don_thuoc.png")},
        content_type="multipart/form-data"
    )
    # Endpoint trả về JSON phân tích (có thể là failed/needs_review nếu mock không có OCR, nhưng phải có status_code 200)
    assert res_auth.status_code == 200
    data = res_auth.get_json()
    assert "document_id" in data

    # Kiểm tra trong CSDL tài liệu đã được tạo và gắn đúng owner_id = User A
    with client.application.app_context():
        doc = db.session.get(MedicalDocument, data["document_id"])
        assert doc is not None
        assert doc.owner_id == user_a_id


def test_cannot_access_or_modify_other_user_intake_session(client, test_users):
    """Kiểm thử: User B không thể đọc, sửa hoặc xác nhận phiên hỏi bệnh của User A."""
    user_a_id = test_users["user_a_id"]
    user_b_id = test_users["user_b_id"]

    # 1. User A tạo phiên tư vấn
    with client.session_transaction() as sess:
        sess["user_id"] = user_a_id
    res_a = client.post("/api/intake/session", json={})
    assert res_a.status_code == 200
    cid_a = res_a.get_json()["conversation_id"]

    # User A cập nhật dữ kiện
    client.post("/api/intake/update-fact", json={"conversation_id": cid_a, "field": "chief_complaint", "value": "Đau bụng cấp"})

    # 2. User B đăng nhập và thử đọc tóm tắt của User A
    with client.session_transaction() as sess:
        sess["user_id"] = user_b_id

    res_b_get = client.get(f"/api/intake/summary/{cid_a}")
    assert res_b_get.status_code == 403

    # User B thử sửa dữ kiện của User A
    res_b_update = client.post("/api/intake/update-fact", json={
        "conversation_id": cid_a,
        "field": "chief_complaint",
        "value": "Đã bị User B sửa lậu"
    })
    assert res_b_update.status_code == 403

    # User B thử xác nhận thay cho User A
    res_b_confirm = client.post("/api/intake/confirm-summary", json={"conversation_id": cid_a})
    assert res_b_confirm.status_code == 403

    # 3. Khách lạ (chưa đăng nhập) cũng bị từ chối 403
    with client.session_transaction() as sess:
        sess.clear()

    res_guest_get = client.get(f"/api/intake/summary/{cid_a}")
    assert res_guest_get.status_code == 403


def test_email_otp_verify_does_not_burn_otp_on_short_password_and_completes_with_valid_password(client, monkeypatch):
    """Đảm bảo password < 8 ký tự bị từ chối trước khi tiêu thụ OTP, và password >= 8 tạo user + session thành công."""
    from pathlib import Path
    from core.models import OtpRecord

    captured_codes = []

    def fake_send_otp(email, code, full_name=None, purpose="register"):
        captured_codes.append(code)
        return True

    monkeypatch.setattr("core.otp_service.email_service.send_verification_otp", fake_send_otp)

    target_email = "verify.flow@example.com"
    res_send = client.post("/api/auth/otp/send", json={
        "identifier": target_email,
        "channel": "email",
        "purpose": "register",
        "full_name": "Verify Flow User",
    })
    assert res_send.status_code == 200
    assert res_send.get_json()["success"] is True
    assert len(captured_codes) == 1
    otp_code = captured_codes[0]

    # 1. Mật khẩu 6 ký tự bị chặn 400 nhưng KHÔNG làm cháy mã OTP trong DB
    res_short = client.post("/api/auth/otp/verify", json={
        "identifier": target_email,
        "channel": "email",
        "code": otp_code,
        "purpose": "register",
        "user_data": {
            "full_name": "Verify Flow User",
            "password": "123456",
            "gender": "Nam",
        },
    })
    assert res_short.status_code == 400
    assert "8" in res_short.get_json()["error"]

    with client.application.app_context():
        otp_row = OtpRecord.query.filter_by(key=f"email:{target_email}").first()
        assert otp_row is not None
        assert otp_row.consumed is False

    # 2. Với mật khẩu >= 8 ký tự và đúng mã OTP cũ -> tạo tài khoản + cấp session đăng nhập ngay
    res_ok = client.post("/api/auth/otp/verify", json={
        "identifier": target_email,
        "channel": "email",
        "code": otp_code,
        "purpose": "register",
        "user_data": {
            "full_name": "Verify Flow User",
            "password": "StrongPassword123",
            "gender": "Nam",
        },
    })
    assert res_ok.status_code == 201
    ok_data = res_ok.get_json()
    assert ok_data["success"] is True
    assert ok_data["user"]["email"] == target_email

    res_me = client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.get_json()["authenticated"] is True

    # 3. Kiểm tra UI index.html & app.js đồng bộ chuẩn 8 ký tự, hiển thị rule và toast z-[120] trên auth modal z-[70]
    root = Path(__file__).resolve().parents[1]
    index_html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="register-password" required minlength="8"' in index_html
    assert 'id="register-confirm-password" required minlength="8"' in index_html
    assert 'id="register-password-rule"' in index_html
    assert 'id="forgot-password-rule"' in index_html
    assert 'id="settings-password-rule"' in index_html
    assert 'data-i18n="pwd_rule_min8"' in index_html
    assert 'id="medical-toast-container"' in index_html and "z-[120]" in index_html
    assert "password.trim().length < 8" in app_js
    assert "initPasswordRuleHints" in app_js
    assert "register_email" in app_js and "register_phone" in app_js
    assert "openGoogleOnboardingModal(currentUser, false, { source: onboardingSource })" in app_js
    assert "z-[120]" in app_js

    # 4. Sau khi đăng ký OTP thành công, cập nhật hồ sơ qua /api/auth/profile hoạt động cả với Gmail & SĐT
    res_prof = client.post("/api/auth/profile", json={
        "name": "Verify Flow Updated",
        "gender": "Nữ",
        "dob": "15/08/1995",
        "phone_number": "0912345678",
    })
    assert res_prof.status_code == 200
    prof_data = res_prof.get_json()
    assert prof_data["success"] is True
    assert prof_data["user"]["full_name"] == "Verify Flow Updated"
    assert prof_data["user"]["dob"] == "15/08/1995"
    assert prof_data["user"]["phone_number"] == "0912345678"


def test_forgot_password_reset_flow_and_vuln02_enumeration_protection(client, monkeypatch):
    """Kiểm thử end-to-end Quên mật khẩu: chống dò tài khoản (VULN-02), policy >= 8 (VULN-04), đổi mật khẩu DB & đăng nhập lại."""
    from pathlib import Path
    from core.models import OtpRecord, OtpVerifiedRecord

    sent_items = []

    def fake_send_otp(email, code, full_name=None, purpose="register"):
        sent_items.append((email, code, purpose))
        return True

    monkeypatch.setattr("core.otp_service.email_service.send_verification_otp", fake_send_otp)

    # Tạo tài khoản mẫu ban đầu
    target_email = "forgot.user@example.com"
    with client.application.app_context():
        u = User(email=target_email, full_name="Forgot User", role="patient")
        u.set_password("OldPassword123")
        db.session.add(u)
        db.session.commit()

    # 1. Email không tồn tại -> silent no-op trả 200 giống hệt, KHÔNG tạo OTP và KHÔNG gửi email (VULN-02)
    unknown_email = "nobody.forgot@example.com"
    res_unknown = client.post("/api/auth/otp/send", json={
        "identifier": unknown_email,
        "channel": "email",
        "purpose": "reset_pwd",
    })
    assert res_unknown.status_code == 200
    assert res_unknown.get_json()["success"] is True
    assert len(sent_items) == 0
    with client.application.app_context():
        assert OtpRecord.query.filter_by(key=f"email:{unknown_email}").first() is None

    # 2. Email tồn tại -> gửi OTP thật và có cùng HTTP status & message trung lập
    res_real = client.post("/api/auth/otp/send", json={
        "identifier": target_email,
        "channel": "email",
        "purpose": "reset_pwd",
    })
    assert res_real.status_code == 200
    assert res_real.get_json()["message"] == res_unknown.get_json()["message"]
    assert len(sent_items) == 1
    assert sent_items[0][2] == "reset_pwd"
    otp_code = sent_items[0][1]

    # 3. Mật khẩu mới < 8 ký tự -> chặn 400 (VULN-04) nhưng KHÔNG đốt mã OTP
    res_short = client.post("/api/auth/otp/verify", json={
        "identifier": target_email,
        "channel": "email",
        "code": otp_code,
        "purpose": "reset_pwd",
        "user_data": {"new_password": "123456"},
    })
    assert res_short.status_code == 400
    assert "8" in res_short.get_json()["error"]
    with client.application.app_context():
        rec = OtpRecord.query.filter_by(key=f"email:{target_email}").first()
        assert rec is not None and rec.consumed is False

    # 4. Đúng OTP + mật khẩu mới >= 8 ký tự -> cập nhật mật khẩu trong DB, consume OTP sạch
    res_reset = client.post("/api/auth/otp/verify", json={
        "identifier": target_email,
        "channel": "email",
        "code": otp_code,
        "purpose": "reset_pwd",
        "user_data": {"new_password": "NewPassword999"},
    })
    assert res_reset.status_code == 200
    reset_data = res_reset.get_json()
    assert reset_data["success"] is True
    assert reset_data["reset_completed"] is True
    with client.application.app_context():
        assert OtpVerifiedRecord.query.filter_by(key=f"email:{target_email}").first() is None

    # 5. Mật khẩu cũ bị từ chối 401, mật khẩu mới đăng nhập thành công 200
    res_old_login = client.post("/api/auth/login", json={
        "identifier": target_email,
        "password": "OldPassword123",
    })
    assert res_old_login.status_code == 401

    res_new_login = client.post("/api/auth/login", json={
        "identifier": target_email,
        "password": "NewPassword999",
    })
    assert res_new_login.status_code == 200
    assert res_new_login.get_json()["success"] is True

    # 6. Kiểm tra Frontend có startForgotPasswordFlow, nhánh 'forgot' và confirm password
    root = Path(__file__).resolve().parents[1]
    index_html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="forgot-confirm-password"' in index_html
    assert "function startForgotPasswordFlow()" in app_js
    assert "} else if (mode === 'forgot')" in app_js
    assert "completedPurpose === 'reset_pwd'" in app_js



