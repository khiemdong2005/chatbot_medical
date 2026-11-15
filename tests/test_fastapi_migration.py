"""
tests/test_fastapi_migration.py
Kiểm thử toàn diện cho Phase 5.5 — Gradual FastAPI Migration:
1. Route Precedence & Ownership (FastAPI Native vs WSGI Middleware)
2. Facilities Native API (Pagination, Filters, Search, Markers)
3. Config Maps Native API
4. Appointments CRUD & Transaction Isolation
5. Consultations Listing & Ownership Deletion
6. Clinical Summary Semantic Data Output
7. Semantic Parity (Flask vs FastAPI Gateway)
"""
import json
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.middleware.wsgi import WSGIMiddleware

from core.main_fastapi import app, flask_gateway, FLASK_COMPAT_PREFIXES, flask_app_instance
from core.models import db, User, MedicalAppointment, ClinicalConsultation
from core.db_utils import app_db_context, transactional_session
from core.api_errors import ErrorCode


@pytest.fixture
def api_client():
    """TestClient cho FastAPI Gateway."""
    return TestClient(app, headers={"origin": "http://localhost:8000"})


@pytest.fixture
def flask_client():
    """TestClient cho Flask legacy application."""
    return flask_app_instance.test_client()


def make_signed_auth_cookie(user_id: int, guest_token: str = "gst_test_mig") -> str:
    """Sinh chuỗi cookie session đã ký tương thích hoàn toàn với Flask serializer."""
    serializer = flask_app_instance.session_interface.get_signing_serializer(flask_app_instance)
    return serializer.dumps({"user_id": user_id, "guest_token": guest_token})


def get_cookie_name() -> str:
    return getattr(flask_app_instance, "session_cookie_name", "session")


# ==============================================================================
# 1. ROUTE OWNERSHIP & WSGI REDUCTION
# ==============================================================================

class TestRouteOwnershipAndPrecedence:
    """Kiểm tra quyền sở hữu định tuyến: Native FastAPI vs WSGI Middleware."""

    def test_wsgi_compatibility_prefixes_reduced(self):
        """Khẳng định số lượng WSGI compatibility prefixes đã giảm từ 11 xuống 6."""
        assert len(FLASK_COMPAT_PREFIXES) == 6
        expected_prefixes = {"auth", "prescription", "intake", "nutrition", "scan-files", "upload-lab"}
        assert set(FLASK_COMPAT_PREFIXES) == expected_prefixes

        # Các prefix đã migrate KHÔNG ĐƯỢC CÒN trong FLASK_COMPAT_PREFIXES
        migrated_prefixes = {"facilities", "appointments", "consultations", "clinical-summary", "config"}
        for prefix in migrated_prefixes:
            assert prefix not in FLASK_COMPAT_PREFIXES

    def test_migrated_routes_have_native_fastapi_endpoints(self):
        """Kiểm tra bảng định tuyến app.routes xác nhận các route migrate trỏ trực tiếp đến FastAPI handlers."""
        native_routes = {
            "/api/facilities": "list_facilities_endpoint",
            "/api/facilities/filters": "facilities_filters_endpoint",
            "/api/facilities/map-markers": "facilities_map_markers_endpoint",
            "/api/config/maps": "get_maps_config_endpoint",
            "/api/appointments": "get_appointments_endpoint",
            "/api/appointments/{appt_id}": "delete_appointment_endpoint",
            "/api/consultations": "get_consultations_endpoint",
            "/api/consultations/{cid}": "delete_consultation_endpoint",
            "/api/clinical-summary": "get_clinical_summary_endpoint"
        }

        # Lập bản đồ path -> endpoint names
        route_endpoints = {}
        for r in app.routes:
            path = getattr(r, "path", None)
            ep = getattr(r, "endpoint", None)
            if path and ep:
                name = getattr(ep, "__name__", str(ep))
                route_endpoints.setdefault(path, []).append(name)

        for path, expected_name in native_routes.items():
            assert path in route_endpoints, f"Route {path} missing in app.routes"
            assert expected_name in route_endpoints[path], \
                f"Route {path} does not point to {expected_name}, got {route_endpoints[path]}"


# ==============================================================================
# 2. FACILITIES NATIVE API
# ==============================================================================

class TestFacilitiesMigration:
    """Kiểm thử tính năng danh mục cơ sở y tế trên FastAPI native router."""

    def test_facilities_pagination_and_defaults(self, api_client):
        res = api_client.get("/api/facilities")
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        assert data.get("page") == 1
        assert data.get("limit") == 12
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) <= 12

    def test_facilities_custom_page_and_limit(self, api_client):
        res = api_client.get("/api/facilities?page=2&limit=5")
        assert res.status_code == 200
        data = res.json()
        assert data.get("page") == 2
        assert data.get("limit") == 5
        assert len(data["data"]) <= 5

    def test_facilities_filters_stats(self, api_client):
        res = api_client.get("/api/facilities/filters")
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        assert "loai_hinh" in data
        assert "quan_huyen" in data
        assert "chuyen_khoa" in data
        assert isinstance(data["loai_hinh"], dict)
        assert isinstance(data["quan_huyen"], list)
        assert isinstance(data["chuyen_khoa"], list)

    def test_facilities_search_and_category_filter(self, api_client):
        res = api_client.get("/api/facilities?search=Bệnh+viện&loai_hinh=Bệnh+viện")
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        for item in data["data"]:
            lh = (item.get("loai_hinh") or "").lower()
            assert "bệnh viện" in lh or "benh vien" in lh or "bệnh" in lh

    def test_facilities_map_markers(self, api_client):
        res = api_client.get("/api/facilities/map-markers")
        assert res.status_code == 200
        data = res.json()
        assert data.get("success") is True
        assert "markers" in data
        assert len(data["markers"]) > 0
        first = data["markers"][0]
        assert "id" in first
        assert "name" in first
        assert "lat" in first
        assert "lng" in first
        assert isinstance(first["lat"], (int, float))
        assert isinstance(first["lng"], (int, float))


# ==============================================================================
# 3. CONFIG MAPS NATIVE API
# ==============================================================================

class TestConfigMapsMigration:
    """Kiểm thử cấu hình maps trên FastAPI native router."""

    def test_get_maps_config(self, api_client):
        res = api_client.get("/api/config/maps")
        assert res.status_code == 200
        data = res.json()
        assert "has_key" in data
        assert "key" in data
        assert isinstance(data["has_key"], bool)
        assert isinstance(data["key"], str)


# ==============================================================================
# 4. APPOINTMENTS NATIVE API
# ==============================================================================

class TestAppointmentsMigration:
    """Kiểm thử Đặt lịch khám: Xác thực, CRUD, Phân lập dữ liệu & Rollback."""

    def test_appointments_unauthenticated_returns_canonical_401(self, api_client):
        res = api_client.get("/api/appointments")
        assert res.status_code == 401
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == ErrorCode.AUTH_REQUIRED.value

    def test_create_appointment_unauthenticated_returns_canonical_401(self, api_client):
        res = api_client.post("/api/appointments", json={})
        assert res.status_code == 401
        data = res.json()
        assert data["error"]["code"] == ErrorCode.AUTH_REQUIRED.value

    def test_create_appointment_validation_error(self, api_client):
        user_id = 9001
        signed_cookie = make_signed_auth_cookie(user_id)
        api_client.cookies.set(get_cookie_name(), signed_cookie)

        # Thiếu các trường bắt buộc (date, time, patient_name, patient_phone)
        res = api_client.post("/api/appointments", json={
            "facility_name": "Phòng khám Đa khoa"
        })
        assert res.status_code == 400
        data = res.json()
        assert data["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "Vui lòng điền đầy đủ" in data["error"]["message"]

    def test_appointments_crud_lifecycle(self, api_client):
        user_id = 9002
        signed_cookie = make_signed_auth_cookie(user_id)
        api_client.cookies.set(get_cookie_name(), signed_cookie)

        # 1. Tạo lịch hẹn thành công
        payload = {
            "facility_id": "fac_test_101",
            "facility_name": "Bệnh viện Chợ Rẫy",
            "facility_address": "201B Nguyễn Chí Thanh, Quận 5",
            "specialty": "Tim mạch",
            "appointment_date": "20/12/2026",
            "appointment_time": "09:30",
            "patient_name": "Nguyễn Văn Test",
            "patient_phone": "0901234567",
            "note": "Khám định kỳ"
        }
        res_create = api_client.post("/api/appointments", json=payload)
        assert res_create.status_code == 201
        data_create = res_create.json()
        assert data_create.get("success") is True
        appt = data_create.get("appointment")
        assert appt is not None
        appt_id = appt["id"]
        assert appt["facility_name"] == "Bệnh viện Chợ Rẫy"

        # 2. Lấy danh sách lịch hẹn
        res_list = api_client.get("/api/appointments")
        assert res_list.status_code == 200
        data_list = res_list.json()
        assert data_list.get("status") == "success"
        user_appts = data_list.get("appointments", [])
        assert any(a["id"] == appt_id for a in user_appts)

        # 3. Hủy lịch hẹn
        res_del = api_client.delete(f"/api/appointments/{appt_id}")
        assert res_del.status_code == 200
        assert res_del.json().get("success") is True

        # 4. Xác nhận đã xóa
        res_list_after = api_client.get("/api/appointments")
        assert not any(a["id"] == appt_id for a in res_list_after.json().get("appointments", []))

    def test_appointments_cross_user_isolation(self, api_client):
        """User B không thể hủy lịch hẹn của User A."""
        user_a = 9003
        user_b = 9004

        # User A tạo lịch hẹn
        cookie_a = make_signed_auth_cookie(user_a)
        api_client.cookies.set(get_cookie_name(), cookie_a)

        res_a = api_client.post("/api/appointments", json={
            "facility_name": "BV Bạch Mai",
            "appointment_date": "22/12/2026",
            "appointment_time": "14:00",
            "patient_name": "User A",
            "patient_phone": "0911222333"
        })
        assert res_a.status_code == 201
        appt_id = res_a.json()["appointment"]["id"]

        # Chuyển sang User B và cố tình xóa lịch của User A -> Phải nhận 404 NOT_FOUND
        cookie_b = make_signed_auth_cookie(user_b)
        api_client.cookies.set(get_cookie_name(), cookie_b)

        res_b_del = api_client.delete(f"/api/appointments/{appt_id}")
        assert res_b_del.status_code == 404
        assert res_b_del.json()["error"]["code"] == ErrorCode.NOT_FOUND.value

    def test_appointment_db_rollback_on_failure(self, api_client):
        """Xác nhận nếu commit lỗi thì thực hiện rollback và trả về 500 PERSISTENCE_ERROR."""
        user_id = 9005
        cookie = make_signed_auth_cookie(user_id)
        api_client.cookies.set(get_cookie_name(), cookie)

        with patch("core.appointment_service.commit_or_rollback", side_effect=RuntimeError("Simulated DB Crash")):
            res = api_client.post("/api/appointments", json={
                "facility_name": "Phòng khám Lỗi",
                "appointment_date": "25/12/2026",
                "appointment_time": "10:00",
                "patient_name": "Rollback Test",
                "patient_phone": "0900000000"
            })
            assert res.status_code == 500
            data = res.json()
            assert data["error"]["code"] == ErrorCode.PERSISTENCE_ERROR.value


# ==============================================================================
# 5. CONSULTATIONS NATIVE API
# ==============================================================================

class TestConsultationsMigration:
    """Kiểm thử Lịch sử tư vấn: Liệt kê, Xóa phiên và Phân lập người dùng."""

    def test_consultations_unauthenticated_returns_401(self, api_client):
        res = api_client.get("/api/consultations")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED.value

    def test_consultations_list_and_delete(self, api_client):
        user_id = 9010
        cookie = make_signed_auth_cookie(user_id)
        api_client.cookies.set(get_cookie_name(), cookie)

        conv_id = f"conv_cons_{uuid.uuid4().hex[:8]}"

        # Tạo sẵn bản ghi tư vấn trong CSDL với message và answer đầy đủ
        with app_db_context() as sess:
            cons = ClinicalConsultation(
                user_id=user_id,
                conversation_id=conv_id,
                message="Tôi bị đau bụng",
                answer="Bạn nên đi khám chuyên khoa tiêu hóa.",
                confirmed_summary=json.dumps({"part_a": "Triệu chứng dạ dày"})
            )
            sess.add(cons)
            sess.commit()
            cid = cons.id

        # 1. Liệt kê
        res_list = api_client.get("/api/consultations")
        assert res_list.status_code == 200
        data = res_list.json()
        assert data.get("status") == "success"
        assert any(c["id"] == cid for c in data.get("consultations", []))

        # 2. Xóa
        res_del = api_client.delete(f"/api/consultations/{cid}")
        assert res_del.status_code == 200
        assert "Đã xóa" in res_del.json().get("message", "")

        # 3. Xóa lại phiên không tồn tại -> 404
        res_del_again = api_client.delete(f"/api/consultations/{cid}")
        assert res_del_again.status_code == 404
        assert res_del_again.json()["error"]["code"] == ErrorCode.NOT_FOUND.value


# ==============================================================================
# 6. CLINICAL SUMMARY NATIVE API
# ==============================================================================

class TestClinicalSummaryMigration:
    """Kiểm thử Phiếu tóm tắt trước khám: no_data vs dữ liệu thực tế."""

    def test_clinical_summary_unauthenticated_returns_401(self, api_client):
        res = api_client.get("/api/clinical-summary")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED.value

    def test_clinical_summary_empty_account_returns_no_data(self, api_client):
        user_id = 9020
        cookie = make_signed_auth_cookie(user_id)
        api_client.cookies.set(get_cookie_name(), cookie)

        res = api_client.get("/api/clinical-summary")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "no_data"
        assert "Chưa có dữ liệu" in data.get("message", "")

    def test_clinical_summary_with_confirmed_summary(self, api_client):
        user_id = 9021
        cookie = make_signed_auth_cookie(user_id)
        api_client.cookies.set(get_cookie_name(), cookie)

        # Tạo user và consultation trong DB
        with app_db_context() as sess:
            # Tạo hoặc cập nhật User
            u = sess.get(User, user_id)
            if not u:
                u = User(id=user_id, email=f"user_{user_id}@test.medimind", password_hash="hash", full_name="Trần Văn Khỏe")
                sess.add(u)

            cons = ClinicalConsultation(
                user_id=user_id,
                conversation_id=f"conv_sum_{uuid.uuid4().hex[:6]}",
                message="Tôi bị sốt và ho",
                answer="Lời khuyên bác sĩ: Uống nhiều nước và nghỉ ngơi.",
                confirmed_summary=json.dumps({
                    "part_a_patient_facts": {"chief_complaint": "Sốt nhẹ, ho có đờm"},
                    "part_b_doctor_guide": {"suggested_specialty": "Tai Mũi Họng"}
                })
            )
            sess.add(cons)
            sess.commit()

        res = api_client.get("/api/clinical-summary")
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "success"
        assert "summary" in data
        assert data["summary"]["part_a_patient_facts"]["chief_complaint"] == "Sốt nhẹ, ho có đờm"
        assert data["patient_name"] == "Trần Văn Khỏe"
        assert data["patient_id"] == f"BN-2026-{user_id:04d}"


# ==============================================================================
# 7. PARITY KIỂM THỬ ĐẦU CUỐI: FLASK CLIENT VS FASTAPI GATEWAY
# ==============================================================================

class TestSemanticParityFlaskVsFastAPI:
    """Đối chiếu ngữ nghĩa và mã HTTP giữa Flask handler cũ và FastAPI Native mới."""

    def test_facilities_parity(self, api_client, flask_client):
        res_fastapi = api_client.get("/api/facilities?limit=5")
        res_flask = flask_client.get("/api/facilities?limit=5")

        assert res_fastapi.status_code == res_flask.status_code == 200
        data_fa = res_fastapi.json()
        data_fl = res_flask.get_json()

        assert data_fa["total"] == data_fl["total"]
        assert data_fa["limit"] == data_fl["limit"] == 5
        assert len(data_fa["data"]) == len(data_fl["data"]) == 5

    def test_facilities_filters_parity(self, api_client, flask_client):
        res_fastapi = api_client.get("/api/facilities/filters")
        res_flask = flask_client.get("/api/facilities/filters")

        assert res_fastapi.status_code == res_flask.status_code == 200
        data_fa = res_fastapi.json()
        data_fl = res_flask.get_json()

        assert data_fa["total"] == data_fl["total"]
        assert set(data_fa["loai_hinh"].keys()) == set(data_fl["loai_hinh"].keys())

    def test_config_maps_parity(self, api_client, flask_client):
        res_fastapi = api_client.get("/api/config/maps")
        res_flask = flask_client.get("/api/config/maps")

        assert res_fastapi.status_code == res_flask.status_code == 200
        data_fa = res_fastapi.json()
        data_fl = res_flask.get_json()

        assert data_fa["has_key"] == data_fl["has_key"]
        assert data_fa["key"] == data_fl["key"]

    def test_unauthenticated_endpoints_both_return_401(self, api_client, flask_client):
        endpoints = [
            "/api/appointments",
            "/api/consultations",
            "/api/clinical-summary"
        ]
        for ep in endpoints:
            res_fa = api_client.get(ep)
            res_fl = flask_client.get(ep)
            assert res_fa.status_code == 401, f"FastAPI {ep} did not return 401"
            assert res_fl.status_code == 401, f"Flask {ep} did not return 401"
