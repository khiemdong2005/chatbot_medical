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


