"""
Kiểm thử tự động ổ khóa phân quyền Admin Monitoring Guard
(Assert-based self-check, không phụ thuộc framework ngoài)
"""
import os
import sys

# Đảm bảo PYTHONPATH trỏ tới thư mục gốc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from core.models import db, User

def run_checks():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()

    with app.app_context():
        db.create_all()
        # Tạo 1 bệnh nhân và 1 admin
        patient = User(email="patient@test.com", full_name="Bệnh Nhân Test", role="patient")
        patient.set_password("pass123")
        admin = User(email="admin@test.com", full_name="Admin Nitax", role="admin")
        admin.set_password("pass123")
        db.session.add_all([patient, admin])
        db.session.commit()
        patient_id = patient.id
        admin_id = admin.id

    print("[*] Test 1: Khách vãng lai (Chưa đăng nhập) truy cập /monitoring...")
    res = client.get("/monitoring")
    assert res.status_code == 302, f"Expected 302 redirect, got {res.status_code}"
    assert "notice=admin_required" in res.headers.get("Location", "")
    print("    -> PASS: Bị chuyển hướng 302 sang trang đăng nhập!")

    print("[*] Test 2: Khách vãng lai gọi API /api/monitoring/status...")
    res = client.get("/api/monitoring/status")
    assert res.status_code == 403, f"Expected 403 Forbidden, got {res.status_code}"
    data = res.get_json()
    assert data["success"] is False
    assert data["code"] == "FORBIDDEN_ADMIN_REQUIRED"
    print("    -> PASS: Bị chặn đứng 403 FORBIDDEN_ADMIN_REQUIRED!")

    print("[*] Test 3: Khách vãng lai gọi API /api/monitoring/alert/test...")
    res = client.post("/api/monitoring/alert/test")
    assert res.status_code == 403, f"Expected 403 Forbidden, got {res.status_code}"
    print("    -> PASS: Bị chặn đứng 403!")

    print("[*] Test 4: Bệnh nhân thường (role='patient') truy cập...")
    with client.session_transaction() as sess:
        sess["user_id"] = patient_id
        sess["user_role"] = "patient"
    res = client.get("/monitoring")
    assert res.status_code == 302, f"Expected 302 redirect for patient, got {res.status_code}"
    res = client.get("/api/monitoring/status")
    assert res.status_code == 403, f"Expected 403 Forbidden for patient, got {res.status_code}"
    print("    -> PASS: Bệnh nhân thường không được phép xem!")

    print("[*] Test 5: Quản trị viên (role='admin') truy cập...")
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
        sess["user_role"] = "admin"
    res = client.get("/monitoring")
    assert res.status_code == 200, f"Expected 200 OK for admin, got {res.status_code}"
    res = client.get("/api/monitoring/status")
    assert res.status_code == 200, f"Expected 200 OK for admin status API, got {res.status_code}"
    data = res.get_json()
    assert data["status"] == "healthy"
    print("    -> PASS: Admin truy cập thành công mượt mà!")

    print("[*] Test 6: Truy cập bằng chìa khóa SRE bí mật (ADMIN_MONITORING_KEY)...")
    with client.session_transaction() as sess:
        sess.clear() # Đăng xuất hoàn toàn
    
    # Dùng query param ?admin_key=...
    res = client.get("/monitoring?admin_key=medimind-sre-nitax-master-2026-key")
    assert res.status_code == 200, f"Expected 200 with admin_key, got {res.status_code}"

    # Kiểm tra polling status tiếp theo (nhờ session flag đã cấp)
    res_status = client.get("/api/monitoring/status")
    assert res_status.status_code == 200, f"Expected 200 via session flag, got {res_status.status_code}"
    print("    -> PASS: Mở khóa bằng SRE secret key & tự động ghi nhận cờ phiên!")

    print("[*] Test 7: Prometheus metrics endpoint...")
    res = client.get("/metrics")
    assert res.status_code == 200
    assert b"http_requests_total" in res.data
    print("    -> PASS: /metrics thu thập dữ liệu thành công!")

    print("\n>>> TẤT CẢ 7 BÀI TEST BẢO MẬT ADMIN ĐỀU PASS 100% HOÀN HẢO! <<<")

if __name__ == "__main__":
    run_checks()
