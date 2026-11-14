"""
================================================================================
🩺 MEDIMIND PHASE 5.2 — DATA SAFETY & CONCURRENCY TEST SUITE
================================================================================
Kiểm thử toàn diện:
1. Giới hạn tần suất Chat (Rate Limiting Parity 25 req / 60s) trên Flask & FastAPI.
2. Thứ tự ưu tiên định danh: user_id > guest_token > client_ip.
3. Chống DoS: Không bypass rate limit kể cả với từ khóa cấp cứu.
4. Nhất quán Rollback CSDL: Không để lại session bẩn (poisoned) khi transaction lỗi.
5. Thread safety cho InMemoryCache: Loại bỏ RuntimeError khi delete_pattern.
6. Thread safety cho IntakeSessionManager: RLock bảo vệ state mà không block external AI.
================================================================================
"""

import os
import time
import uuid
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError
from fastapi.testclient import TestClient

from core.main_fastapi import app as fastapi_app
from core.cache_service import cache_service, InMemoryCache
from core.db_utils import commit_or_rollback, transactional_session
from core.intake_service import intake_service, IntakeSessionManager
from core.security_patch import get_rate_limit_identity, check_chat_rate_limit
from core.models import db, User, IntakeSessionRecord, MedicalAppointment


@pytest.fixture
def api_client():
    """Client gọi trực tiếp qua FastAPI Gateway."""
    return TestClient(fastapi_app)


# ==============================================================================
# 1. KIỂM THỬ GIỚI HẠN TẦN SUẤT TRÒ CHUYỆN (RATE LIMITING PARITY)
# ==============================================================================

class TestChatRateLimiting:
    """Kiểm tra chính sách giới hạn 25 requests / 60s trên cả 2 framework."""

    def setup_method(self):
        """Dọn dẹp cache trước mỗi test."""
        cache_service.clear()

    def test_rate_limit_identity_priority(self):
        """Xác nhận thứ tự ưu tiên: User ID > Guest Token > Client IP."""
        # Ưu tiên 1: User ID
        id1 = get_rate_limit_identity(user_id=42, guest_token="gst_123", client_ip="1.2.3.4")
        assert id1 == "user:42"

        # Ưu tiên 2: Guest Token khi chưa đăng nhập
        id2 = get_rate_limit_identity(user_id=None, guest_token="gst_123", client_ip="1.2.3.4")
        assert id2 == "guest:gst_123"

        # Ưu tiên 3: Client IP fallback
        id3 = get_rate_limit_identity(user_id=None, guest_token=None, client_ip="1.2.3.4")
        assert id3 == "ip:1.2.3.4"

        # Mặc định an toàn khi không có IP
        id4 = get_rate_limit_identity(user_id=None, guest_token=None, client_ip=None)
        assert id4 == "ip:127.0.0.1"

    def test_chat_rate_limit_policy_25_req_per_minute(self):
        """Gửi 25 requests thành công, request thứ 26 bị chặn (False)."""
        identity = f"test_user_{uuid.uuid4().hex[:8]}"

        # 25 requests đầu tiên được cho phép
        for i in range(25):
            allowed = check_chat_rate_limit(identity, max_requests=25, window_seconds=60, enforce=True)
            assert allowed is True, f"Request thứ {i+1} phải được cho phép"

        # Request thứ 26 bị chặn
        blocked = check_chat_rate_limit(identity, max_requests=25, window_seconds=60, enforce=True)
        assert blocked is False, "Request thứ 26 phải bị chặn bởi chính sách Rate Limit"

    def test_identity_quota_isolation(self):
        """Các định danh khác nhau có hạn ngạch độc lập, không ảnh hưởng chéo."""
        user_a = f"user_{uuid.uuid4().hex[:6]}"
        user_b = f"user_{uuid.uuid4().hex[:6]}"

        # Làm cạn kiệt quota của user_a
        for _ in range(25):
            check_chat_rate_limit(user_a, max_requests=25, window_seconds=60, enforce=True)
        assert check_chat_rate_limit(user_a, max_requests=25, window_seconds=60, enforce=True) is False

        # Quota của user_b vẫn hoàn toàn nguyên vẹn
        assert check_chat_rate_limit(user_b, max_requests=25, window_seconds=60, enforce=True) is True

    def test_fastapi_chat_rate_limiting_enforcement(self, api_client):
        """FastAPI /api/chat trả về HTTP 429 khi vượt ngưỡng."""
        with patch("core.main_fastapi.check_chat_rate_limit", return_value=False):
            res = api_client.post(
                "/api/chat",
                json={"message": "Xin chào bác sĩ"}
            )
            assert res.status_code == 429
            data = res.json()
            assert "detail" in data
            assert "quá nhanh" in data["detail"]

    def test_flask_chat_rate_limiting_enforcement(self, client):
        """Flask /api/chat trả về HTTP 429 khi vượt ngưỡng."""
        with patch("core.security_patch.check_chat_rate_limit", return_value=False):
            res = client.post(
                "/api/chat",
                json={"message": "Xin chào bác sĩ"}
            )
            assert res.status_code == 429
            data = res.get_json()
            assert "error" in data
            assert "quá nhanh" in data["error"]

    def test_emergency_query_rate_limited_no_bypass(self, api_client):
        """Kể cả từ khóa cấp cứu, khi đã rate-limit vẫn phải nhận 429 (chống DoS / cạn kiệt tài nguyên)."""
        with patch("core.main_fastapi.check_chat_rate_limit", return_value=False):
            res = api_client.post(
                "/api/chat",
                json={"message": "Tôi bị đau ngực dữ dội khó thở toát mồ hôi"}
            )
            assert res.status_code == 429
            # Không được lọt vào xử lý AI / RAG tốn kém
            assert "detail" in res.json()


# ==============================================================================
# 2. KIỂM THỬ NHẤT QUÁN ROLLBACK CSDL & CHỐNG SESSION POISONING
# ==============================================================================

class TestDatabaseRollbackSafety:
    """Kiểm tra commit_or_rollback và transactional_session giữ session luôn sạch."""

    def test_commit_or_rollback_on_success(self, test_app):
        """Commit bình thường thành công không phát sinh lỗi."""
        with test_app.app_context():
            commit_or_rollback()

    def test_commit_or_rollback_cleans_dirty_session_on_failure(self, test_app):
        """Khi commit thất bại, rollback tự động giải phóng toàn bộ dirty/new state."""
        with test_app.app_context():
            # Thêm đối tượng vào session
            user = User(
                email=f"fail_test_{uuid.uuid4().hex[:6]}@medimind.vn",
                full_name="Test Rollback",
                role="patient"
            )
            db.session.add(user)
            assert len(db.session.new) > 0

            # Giả lập lỗi CSDL khi commit
            with patch.object(db.session, "commit", side_effect=SQLAlchemyError("Disk I/O Error")):
                with pytest.raises(SQLAlchemyError):
                    commit_or_rollback()

            # Xác nhận sau rollback, session sạch hoàn toàn
            assert len(db.session.new) == 0
            assert len(db.session.dirty) == 0

            # Giao dịch kế tiếp vẫn hoạt động bình thường (không bị InvalidRequestError / Poisoned session)
            user_ok = User(
                email=f"success_test_{uuid.uuid4().hex[:6]}@medimind.vn",
                full_name="Test OK",
                role="patient"
            )
            user_ok.set_password("SecurePass123@")
            db.session.add(user_ok)
            commit_or_rollback()
            assert user_ok.id is not None

    def test_transactional_session_context_manager(self, test_app):
        """Context manager transactional_session tự động rollback khi có ngoại lệ."""
        with test_app.app_context():
            with pytest.raises(ValueError):
                with transactional_session() as s:
                    u = User(
                        email=f"ctx_{uuid.uuid4().hex[:6]}@medimind.vn",
                        full_name="Ctx Test",
                        role="patient"
                    )
                    u.set_password("Pass123@")
                    s.add(u)
                    raise ValueError("Simulated business error")

            # Session đã được rollback sạch sẽ
            assert len(db.session.new) == 0
            assert len(db.session.dirty) == 0

    def test_route_mutation_handles_commit_failure_gracefully(self, client):
        """Endpoint mutation bắt lỗi commit an toàn, trả về 500 JSON không lộ stack trace."""
        with patch("app.commit_or_rollback", side_effect=SQLAlchemyError("DB write failure")):
            res = client.post(
                "/api/auth/register",
                json={
                    "identifier": f"err_{uuid.uuid4().hex[:6]}@test.vn",
                    "full_name": "Test Error",
                    "password": "Password123@",
                    "role": "patient"
                }
            )
            assert res.status_code == 500
            data = res.get_json()
            assert data.get("success") is False
            assert "Không thể lưu thông tin" in data.get("error", "")


# ==============================================================================
# 3. KIỂM THỬ THREAD SAFETY CHO INMEMORYCACHE
# ==============================================================================

class TestCacheConcurrency:
    """Kiểm tra tính an toàn đa luồng của InMemoryCache dưới tải cao."""

    def test_in_memory_cache_multithreaded_read_write(self):
        """Đọc và ghi đồng thời từ nhiều worker thread không gây crash hay race condition."""
        cache = InMemoryCache()
        errors = []

        def worker(w_id):
            try:
                for i in range(50):
                    k = f"key_{w_id}_{i}"
                    cache.set(k, f"val_{i}", ttl=10)
                    val = cache.get(k)
                    assert val == f"val_{i}"
                    cache.delete(k)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(8)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0

    def test_in_memory_cache_delete_pattern_race_condition(self):
        """Xóa theo pattern trong khi các thread khác đang ghi không gây RuntimeError: dict changed size."""
        cache = InMemoryCache()
        stop_event = threading.Event()
        errors = []

        def writer():
            try:
                idx = 0
                while not stop_event.is_set():
                    cache.set(f"test_pat:{idx}", idx, ttl=5)
                    idx += 1
            except Exception as e:
                errors.append(e)

        def cleaner():
            try:
                for _ in range(30):
                    cache.delete_pattern("test_pat:*")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Chạy 4 writers và 2 cleaners đồng thời
        threads = [threading.Thread(target=writer) for _ in range(4)]
        cleaner_threads = [threading.Thread(target=cleaner) for _ in range(2)]

        for t in threads + cleaner_threads:
            t.start()

        for ct in cleaner_threads:
            ct.join()

        stop_event.set()
        for wt in threads:
            wt.join()

        assert len(errors) == 0, f"Phát hiện lỗi race condition: {errors}"

    def test_in_memory_cache_concurrent_rate_limiting(self):
        """50 threads đồng thời gọi rate limit, đúng 25 threads được pass và 25 threads bị block."""
        cache = InMemoryCache()
        identity = f"concurrent_rate_id_{uuid.uuid4().hex[:6]}"
        results = []

        def call_limit():
            blocked = cache.check_rate_limit(identity, max_requests=25, window_seconds=60)
            results.append(blocked)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(call_limit) for _ in range(50)]
            for f in as_completed(futures):
                f.result()

        assert len(results) == 50
        allowed_count = results.count(False)
        blocked_count = results.count(True)
        assert allowed_count == 25, f"Chính xác 25 requests được duyệt, thực tế: {allowed_count}"
        assert blocked_count == 25, f"Chính xác 25 requests bị chặn, thực tế: {blocked_count}"


# ==============================================================================
# 4. KIỂM THỬ THREAD SAFETY CHO INTAKESESSIONMANAGER
# ==============================================================================

class TestIntakeConcurrency:
    """Kiểm tra IntakeSessionManager được bảo vệ bởi RLock khi nhiều luồng truy cập."""

    def test_intake_concurrent_process_message_updates(self, test_app):
        """Nhiều luồng đồng thời cập nhật dữ kiện cho cùng 1 phiên không làm hỏng state."""
        with test_app.app_context():
            cid = f"test_concurrent_intake_{uuid.uuid4().hex[:8]}"
            gst = f"gst_{uuid.uuid4().hex[:8]}"
            intake_service.get_or_create_session(cid, guest_token=gst)
            errors = []

            def send_msg(text):
                try:
                    res = intake_service.process_message(cid, text, guest_token=gst)
                    assert res is not None
                    assert "status" in res
                except Exception as e:
                    errors.append(e)

            messages = [
                "Tôi bị đau bụng từ 2 ngày trước",
                "Cơn đau âm ỉ vùng thượng vị",
                "Tôi không sốt",
                "Tôi có tiền sử dị ứng penicillin",
                "Tôi đang uống paracetamol"
            ]

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(send_msg, m) for m in messages]
                for f in as_completed(futures):
                    f.result()

            assert len(errors) == 0

            # Kiểm tra trạng thái cuối cùng nhất quán
            session = intake_service.get_or_create_session(cid, guest_token=gst)
            assert session["turn_count"] == 5
            assert len(session["messages"]) == 10  # 5 user + 5 assistant replies
            assert any("penicillin" in a for a in session["facts"]["allergies"])

    def test_intake_concurrent_read_and_update_fact(self, test_app):
        """Đọc summary và cập nhật fact đồng thời không gây deadlock."""
        with test_app.app_context():
            cid = f"test_intake_fact_race_{uuid.uuid4().hex[:8]}"
            gst = f"gst_{uuid.uuid4().hex[:8]}"
            intake_service.get_or_create_session(cid, guest_token=gst)
            errors = []

            def read_worker():
                try:
                    for _ in range(20):
                        intake_service.get_summary(cid, guest_token=gst)
                except Exception as e:
                    errors.append(e)

            def write_worker():
                try:
                    for i in range(20):
                        intake_service.update_fact(cid, "duration", f"{i+1} ngày", guest_token=gst)
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=4) as executor:
                f1 = executor.submit(read_worker)
                f2 = executor.submit(read_worker)
                f3 = executor.submit(write_worker)
                f4 = executor.submit(write_worker)

                for f in [f1, f2, f3, f4]:
                    f.result(timeout=5.0)  # Khẳng định không bị deadlock trong 5 giây

            assert len(errors) == 0
