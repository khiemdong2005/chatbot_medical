"""
================================================================================
🩺 MEDIMIND PHASE 5.1 — GATEWAY PARITY & INTAKE PERSISTENCE TEST SUITE
================================================================================
Kiểm thử toàn diện:
1. Parity giữa FastAPI Gateway và các endpoint kế thừa từ Flask WSGI.
2. Bảo toàn độ ưu tiên (Precedence Invariant) cho các route FastAPI Native.
3. Đồng bộ lưu trữ Intake Session bền vững vào SQLite (chống silent bypass).
4. Khôi phục dữ liệu sau khi xóa bộ nhớ (RAM Reset / Restart Simulation).
5. Tính trung thực của cờ history_saved (No Silent Success khi DB fail).
6. Cách ly dữ liệu đa người dùng (Multi-user Tenant Isolation).
7. Định danh khách vãng lai (Guest Token) & Tài khoản đăng nhập (Session Cookie).
================================================================================
"""

import os
import json
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from core.main_fastapi import app as fastapi_app
from core.intake_service import intake_service, IntakeSessionManager, intake_db_context
from core.models import db, IntakeSessionRecord, User


@pytest.fixture
def api_client():
    """Client gọi trực tiếp qua FastAPI Gateway (không qua Flask client)."""
    return TestClient(fastapi_app, headers={"origin": "http://localhost:8000"})


# ==============================================================================
# 1. PARITY KIỂM THỬ ĐẦU CUỐI CÁC ROUTE FLASK QUA FASTAPI GATEWAY
# ==============================================================================

class TestGatewayParityRouting:
    """Xác nhận không một endpoint nghiệp vụ nào bị 404 do Gateway không mount."""

    def test_facilities_endpoint_resolves(self, api_client):
        """GET /api/facilities trả về 200 kèm danh sách cơ sở y tế."""
        res = api_client.get("/api/facilities")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert "data" in data or isinstance(data, list)

    def test_facilities_map_markers_resolves(self, api_client):
        """GET /api/facilities/map-markers trả về 200."""
        res = api_client.get("/api/facilities/map-markers")
        assert res.status_code == 200
        data = res.json()
        assert "markers" in data or "data" in data

    def test_appointments_auth_required_resolves(self, api_client):
        """GET /api/appointments trả về 401 khi chưa đăng nhập (KHÔNG PHẢI 404)."""
        res = api_client.get("/api/appointments")
        assert res.status_code == 401, f"Expected 401 auth required, got {res.status_code}"
        assert res.status_code != 404

    def test_nutrition_options_resolves(self, api_client):
        """POST /api/nutrition/options trả về 400 (validation) hoặc 200 khi body hợp lệ, KHÔNG PHẢI 404."""
        res = api_client.post("/api/nutrition/options", json={})
        assert res.status_code in (400, 422), f"Expected validation error, got {res.status_code}"
        assert res.status_code != 404

        # Thử với body hợp lệ theo schema yêu cầu (condition + recipe_type)
        valid_res = api_client.post("/api/nutrition/options", json={"condition": "Mệt mỏi", "recipe_type": "food"})
        assert valid_res.status_code == 200
        data = valid_res.json()
        assert data.get("success") is True

    def test_nutrition_analyze_resolves(self, api_client):
        """POST /api/nutrition/analyze trả về 400 hoặc 200, KHÔNG PHẢI 404."""
        res = api_client.post("/api/nutrition/analyze", json={})
        assert res.status_code in (400, 422)
        assert res.status_code != 404

    def test_scan_files_auth_required_resolves(self, api_client):
        """GET /api/scan-files trả về 401 khi chưa đăng nhập, KHÔNG PHẢI 404."""
        res = api_client.get("/api/scan-files")
        assert res.status_code == 401
        assert res.status_code != 404

    def test_consultations_auth_required_resolves(self, api_client):
        """GET /api/consultations trả về 401 khi chưa đăng nhập, KHÔNG PHẢI 404."""
        res = api_client.get("/api/consultations")
        assert res.status_code == 401
        assert res.status_code != 404

    def test_clinical_summary_auth_required_resolves(self, api_client):
        """GET /api/clinical-summary trả về 401 khi chưa đăng nhập, KHÔNG PHẢI 404."""
        res = api_client.get("/api/clinical-summary")
        assert res.status_code == 401
        assert res.status_code != 404

    def test_upload_lab_auth_required_resolves(self, api_client):
        """POST /api/upload-lab trả về 401 khi chưa đăng nhập, KHÔNG PHẢI 404."""
        res = api_client.post("/api/upload-lab", json={})
        assert res.status_code == 401
        assert res.status_code != 404

    def test_config_maps_resolves(self, api_client):
        """GET /api/config/maps trả về 200."""
        res = api_client.get("/api/config/maps")
        assert res.status_code == 200
        data = res.json()
        assert "has_key" in data or "maps_api_key" in data


# ==============================================================================
# 2. FASTAPI NATIVE ROUTE PRECEDENCE INVARIANT
# ==============================================================================

class TestNativeRoutePrecedence:
    """Đảm bảo các route Native của FastAPI không bị Flask WSGI đánh chặn (shadow)."""

    def test_health_is_native_fastapi(self, api_client):
        res = api_client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_ready_is_native_fastapi(self, api_client):
        res = api_client.get("/ready")
        assert res.status_code in (200, 503)
        data = res.json()
        assert "rag" in data
        assert "gemini" in data

    def test_system_metrics_is_native_fastapi(self, api_client):
        from app import app as flask_app
        serializer = flask_app.session_interface.get_signing_serializer(flask_app)
        api_client.cookies.set("session", serializer.dumps({"user_id": 999, "user_role": "admin"}))
        res = api_client.get("/api/system/metrics")
        assert res.status_code == 200
        data = res.json()
        assert "requests" in data
        assert "uptime_seconds" in data
        assert "components" in data

    def test_system_dashboard_page_is_native_fastapi(self, api_client):
        from app import app as flask_app
        serializer = flask_app.session_interface.get_signing_serializer(flask_app)
        api_client.cookies.set("session", serializer.dumps({"user_id": 999, "user_role": "admin"}))
        res = api_client.get("/system")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")

    def test_chat_is_native_fastapi(self, api_client):
        """POST /api/chat xử lý bằng Native FastAPI Endpoint trả về hợp đồng lâm sàng."""
        res = api_client.post("/api/chat", json={
            "message": "Bác sĩ ơi, tôi bị sốt nhẹ và mệt mỏi từ sáng nay",
            "lang": "vi"
        })
        assert res.status_code == 200
        data = res.json()
        assert "answer" in data
        assert "risk_level" in data
        assert "is_emergency" in data
        assert "sources" in data

    def test_migrated_routes_are_native_fastapi(self):
        """Phase 5.5: Các route đã migrate là Native FastAPI endpoint trong router table, không qua WSGI."""
        from core.main_fastapi import app, flask_gateway
        from starlette.middleware.wsgi import WSGIMiddleware

        migrated_prefixes = [
            "/api/facilities",
            "/api/facilities/filters",
            "/api/facilities/map-markers",
            "/api/config/maps",
            "/api/appointments",
            "/api/consultations",
            "/api/clinical-summary"
        ]

        # Lập bản đồ path -> list endpoints
        route_map = {}
        for r in app.routes:
            path = getattr(r, "path", None)
            ep = getattr(r, "endpoint", None)
            app_target = getattr(r, "app", None)
            if path:
                route_map.setdefault(path, []).append((ep, app_target))

        for target_path in migrated_prefixes:
            matched_key = target_path if target_path in route_map else (f"{target_path}/" if f"{target_path}/" in route_map else target_path.rstrip("/"))
            assert matched_key in route_map, f"Target path {target_path} missing in app.routes"
            endpoints = route_map[matched_key]
            for ep, app_target in endpoints:
                assert not isinstance(ep, WSGIMiddleware) and ep != flask_gateway, \
                    f"Path {target_path} is still pointing to WSGIMiddleware!"
                assert not isinstance(app_target, WSGIMiddleware) and app_target != flask_gateway, \
                    f"Path {target_path} app is still pointing to WSGIMiddleware!"


# ==============================================================================
# 3. FASTAPI INTAKE PERSISTENCE & TRUTHFULNESS
# ==============================================================================

class TestIntakePersistenceArchitecture:
    """Xác nhận việc ghi và đọc IntakeSessionRecord diễn ra thực sự dưới SQLite."""

    def test_fastapi_chat_persists_intake_to_sqlite(self, api_client):
        """FastAPI chat với conversation_id tạo bản ghi thực tế trong SQLite."""
        conv_id = f"conv_test_persist_{uuid.uuid4().hex[:8]}"

        res = api_client.post("/api/chat", json={
            "message": "Tôi bị đau quặn bụng từng cơn và buồn nôn",
            "conversation_id": conv_id,
            "lang": "vi"
        })
        assert res.status_code == 200
        data = res.json()
        assert data.get("conversation_id") == conv_id
        assert data.get("history_saved") is True

        # Kiểm tra trực tiếp trong SQLite database
        with intake_db_context():
            rec = IntakeSessionRecord.query.filter_by(conversation_id=conv_id).first()
            assert rec is not None, "Bản ghi IntakeSessionRecord phải tồn tại trong CSDL!"
            assert rec.conversation_id == conv_id
            facts = json.loads(rec.facts_json)
            assert len(facts.get("present_symptoms", [])) > 0 or facts.get("chief_complaint")
            messages = json.loads(rec.messages_json)
            assert len(messages) >= 2  # user + assistant

    def test_restart_simulation_restores_from_sqlite(self, api_client):
        """Mô phỏng khởi động lại server: Xóa sạch RAM cache, phiên vẫn nạp lại được từ SQLite."""
        conv_id = f"conv_test_restart_{uuid.uuid4().hex[:8]}"

        # 1. Tạo phiên qua FastAPI chat
        res1 = api_client.post("/api/chat", json={
            "message": "Tôi bị sốt cao 39 độ liên tục 2 ngày",
            "conversation_id": conv_id,
            "lang": "vi"
        })
        assert res1.status_code == 200
        guest_token = res1.cookies.get("guest_token")

        # 2. XÓA BỘ NHỚ RAM (Mô phỏng Process Restart / Memory Purge)
        intake_service._sessions.clear()
        assert conv_id not in intake_service._sessions

        # 3. Gửi tiếp lượt chat thứ 2 với cùng conversation_id và guest_token
        headers = {"X-Guest-Token": guest_token} if guest_token else {}
        cookies = {"guest_token": guest_token} if guest_token else {}
        res2 = api_client.post(
            "/api/chat",
            json={
                "message": "Tôi đã uống paracetamol nhưng chưa hạ sốt",
                "conversation_id": conv_id,
                "lang": "vi"
            },
            headers=headers,
            cookies=cookies
        )
        assert res2.status_code == 200
        data2 = res2.json()

        # Phiên phải được phục hồi từ SQLite và tiếp tục thu thập
        assert data2.get("conversation_id") == conv_id
        assert data2.get("history_saved") is True

        # Đọc lại từ DB để kiểm tra số lượt hội thoại
        with intake_db_context():
            rec = IntakeSessionRecord.query.filter_by(conversation_id=conv_id).first()
            assert rec is not None
            messages = json.loads(rec.messages_json)
            # Phải có ít nhất 2 lượt hỏi-đáp (tổng cộng 4 messages)
            assert len(messages) >= 4

    def test_truthful_history_saved_when_db_write_fails(self, api_client):
        """Khi việc ghi CSDL thất bại, history_saved PHẢI là False, không được báo giả True."""
        conv_id = f"conv_test_failure_{uuid.uuid4().hex[:8]}"

        # Mock DB commit ném ngoại lệ khi ghi CSDL
        with patch("core.models.db.session.commit", side_effect=Exception("Mô phỏng lỗi disk I/O")):
            res = api_client.post("/api/chat", json={
                "message": "Tôi bị nhức đầu dữ dội",
                "conversation_id": conv_id,
                "lang": "vi"
            })
            assert res.status_code == 200
            data = res.json()
            # Câu trả lời lâm sàng vẫn phải trả về an toàn
            assert "answer" in data
            assert len(data["answer"]) > 0
            # Nhưng cờ lưu trữ phải trung thực báo FALSE
            assert data.get("history_saved") is False, "Khi DB write fail, history_saved không được phép là True!"
            # Câu trả lời lâm sàng vẫn phải trả về an toàn
            assert "answer" in data
            assert len(data["answer"]) > 0
            # Nhưng cờ lưu trữ phải trung thực báo FALSE
            assert data.get("history_saved") is False, "Khi DB write fail, history_saved không được phép là True!"


# ==============================================================================
# 4. MULTI-USER TENANT ISOLATION & IDENTITY MAPPING
# ==============================================================================

class TestTenantIsolationAndIdentity:
    """Đảm bảo quyền riêng tư và đối soát định danh khách/người dùng."""

    def test_multi_user_isolation(self, api_client):
        """User A không thể can thiệp hoặc truy cập phiên của User B."""
        conv_id_a = f"conv_user_a_{uuid.uuid4().hex[:8]}"
        conv_id_b = f"conv_user_b_{uuid.uuid4().hex[:8]}"
        guest_a = "gst_user_alpha_111"
        guest_b = "gst_user_beta_222"

        # Khách A tạo phiên
        res_a = api_client.post(
            "/api/chat",
            json={"message": "Tôi bị đau lưng", "conversation_id": conv_id_a},
            headers={"X-Guest-Token": guest_a}
        )
        assert res_a.status_code == 200

        # Khách B tạo phiên
        res_b = api_client.post(
            "/api/chat",
            json={"message": "Tôi bị viêm da", "conversation_id": conv_id_b},
            headers={"X-Guest-Token": guest_b}
        )
        assert res_b.status_code == 200

        # Khách B cố tình gửi tin vào phiên của Khách A -> PHẢI BỊ CHẶN 403
        res_hack = api_client.post(
            "/api/chat",
            json={"message": "Tôi muốn sửa phiên của A", "conversation_id": conv_id_a},
            headers={"X-Guest-Token": guest_b}
        )
        assert res_hack.status_code == 403, f"Expected 403 Forbidden, got {res_hack.status_code}"

    def test_guest_token_stability(self, api_client):
        """Khách mới tinh nhận guest_token trong cookie và duy trì định danh qua các lượt."""
        conv_id = f"conv_guest_flow_{uuid.uuid4().hex[:8]}"

        res1 = api_client.post("/api/chat", json={
            "message": "Tôi muốn hỏi về triệu chứng cảm cúm",
            "conversation_id": conv_id
        })
        assert res1.status_code == 200
        assigned_guest = res1.cookies.get("guest_token")
        assert assigned_guest is not None
        assert assigned_guest.startswith("gst_")

        # Kiểm tra trong DB phiên được gán đúng guest_token này
        with intake_db_context():
            rec = IntakeSessionRecord.query.filter_by(conversation_id=conv_id).first()
            assert rec is not None
            assert rec.guest_token == assigned_guest

    def test_authenticated_user_session_persists_user_id(self, api_client):
        """Khi có Flask session cookie hợp lệ, FastAPI chat nhận diện đúng user_id và lưu vào DB."""
        from core.main_fastapi import flask_app_instance
        serializer = flask_app_instance.session_interface.get_signing_serializer(flask_app_instance)
        cookie_name = getattr(flask_app_instance, "session_cookie_name", "session")

        test_user_id = 8888
        signed_cookie_val = serializer.dumps({"user_id": test_user_id, "guest_token": "gst_auth_888"})
        conv_id = f"conv_auth_{uuid.uuid4().hex[:8]}"

        api_client.cookies.set(cookie_name, signed_cookie_val)
        res = api_client.post(
            "/api/chat",
            json={"message": "Tôi tái khám huyết áp", "conversation_id": conv_id}
        )
        assert res.status_code == 200

        with intake_db_context():
            rec = IntakeSessionRecord.query.filter_by(conversation_id=conv_id).first()
            assert rec is not None
            assert rec.user_id == test_user_id
            assert rec.guest_token == "gst_auth_888"

