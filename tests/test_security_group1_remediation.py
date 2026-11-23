"""Regression tests verifying all Group 1 security remediations:
C-01, H-01, H-03, H-04, M-02, M-05, L-02, L-03, L-04.
"""

import json
import pathlib
import time
import uuid
from unittest.mock import patch

import pytest

from app import app as flask_app
from core.ai.llm_provider import _GroqHTTPError, _GroqModels
from core.auth.rate_limit_service import MemoryRateLimitBackend, rate_limit_service
from core.facilities.appointment_service import create_user_appointment
from core.models import MedicalDocument, User, db
from core.routers.deps import extract_request_identity as deps_extract_identity
from core.settings import settings


APP_JS = pathlib.Path(__file__).resolve().parent.parent / "static" / "js" / "app.js"
ORIGIN_HEADERS = {"Origin": "http://localhost:8000"}


def _sign_cookie(user_id: int) -> str:
    serializer = flask_app.session_interface.get_signing_serializer(flask_app)
    return serializer.dumps({"user_id": user_id})


# ---------------------------------------------------------------------------
# C-01: Frontend escapeHtml & OCR/Notification DOM XSS hardening
# ---------------------------------------------------------------------------

def test_c01_escape_html_encodes_quotes_and_no_unsafe_ocr_sinks():
    src = APP_JS.read_text(encoding="utf-8")

    # escapeHtml must encode double and single quotes explicitly
    assert ".replace(/\"/g, '&quot;')" in src
    assert ".replace(/'/g, '&#39;')" in src

    # Previously unescaped OCR/Lab fields must now go through escapeHtml
    assert "${data.doc_title ||" not in src
    assert "LOINC: ${m.loinc_code}" not in src
    assert "${m.computed_flag || m.status ||" not in src
    assert "${data.interpretation.replace(" not in src
    assert "${m.purpose || m.category ||" not in src
    assert ">${m.strength}</strong>" not in src

    # Inline onclick handlers with dynamic strings replaced by data-action delegation
    assert "onclick=\"markMedicationTaken('" not in src
    assert "onclick=\"askBotAboutSpecificMedicine('" not in src
    assert "onclick=\"handleNotificationClick('" not in src
    assert 'data-action="mark-med-taken"' in src
    assert 'data-action="ask-medicine"' in src
    assert 'data-action="notif-appointment"' in src


# ---------------------------------------------------------------------------
# H-01: FastAPI session cookie max_age expiration enforcement
# ---------------------------------------------------------------------------

def test_h01_fastapi_cookie_deserializer_rejects_expired_cookie():
    cookie_name = flask_app.config.get("SESSION_COOKIE_NAME", "session")

    class _FakeRequest:
        def __init__(self, cookie_val: str):
            self.cookies = {cookie_name: cookie_val}
            self.headers = {}

    cookie_val = _sign_cookie(42)
    req = _FakeRequest(cookie_val)

    # Fresh cookie works
    uid, _, _ = deps_extract_identity(req)
    assert uid == 42

    # Expired cookie (simulate lifetime=1s and fast-forward itsdangerous timestamp)
    original_lifetime = flask_app.permanent_session_lifetime
    try:
        flask_app.permanent_session_lifetime = 1
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=int(time.time()) + 3600):
            expired_uid, _, _ = deps_extract_identity(req)
            assert expired_uid is None
    finally:
        flask_app.permanent_session_lifetime = original_lifetime


# ---------------------------------------------------------------------------
# H-03: /api/prescription/confirm auth + schema validation + upload-lab error hiding
# ---------------------------------------------------------------------------

def test_h03_prescription_confirm_requires_auth_ownership_and_validates_schema():
    uid1_email = f"g1_u1_{uuid.uuid4().hex[:8]}@example.com"
    uid2_email = f"g1_u2_{uuid.uuid4().hex[:8]}@example.com"
    with flask_app.app_context():
        u1 = User(email=uid1_email, full_name="Owner One", role="patient")
        u1.set_password("StrongPass123!")
        u2 = User(email=uid2_email, full_name="Other Two", role="patient")
        u2.set_password("StrongPass123!")
        db.session.add_all([u1, u2])
        db.session.commit()
        u1_id, u2_id = u1.id, u2.id

        doc = MedicalDocument(
            owner_id=u1_id,
            storage_filename=f"g1_{uuid.uuid4().hex[:8]}.jpg",
            original_filename="rx.jpg",
            file_path="uploads/rx.jpg",
            file_size=1024,
            file_type="image/jpeg",
            doc_type="ocr_draft",
        )
        db.session.add(doc)
        db.session.commit()
        doc_id = doc.id

    try:
        client = flask_app.test_client()

        cookie_name = flask_app.config.get("SESSION_COOKIE_NAME", "session")

        # Unauthenticated without document_id must still return 401 (no longer 200 echo)
        r_unauth_empty = client.post("/api/prescription/confirm", json={"diagnosis": "test"}, headers=ORIGIN_HEADERS)
        assert r_unauth_empty.status_code == 401

        # Authenticated missing document_id -> 400
        client.set_cookie(cookie_name, _sign_cookie(u1_id))
        r_missing_id = client.post("/api/prescription/confirm", json={"diagnosis": "test"}, headers=ORIGIN_HEADERS)
        assert r_missing_id.status_code == 400

        # Other user -> 404
        client.set_cookie(cookie_name, _sign_cookie(u2_id))
        r_other = client.post("/api/prescription/confirm", json={"document_id": doc_id}, headers=ORIGIN_HEADERS)
        assert r_other.status_code == 404

        # Owner succeeds and unknown/injected keys + dangerous preview_image_url are stripped
        client.set_cookie(cookie_name, _sign_cookie(u1_id))
        r_ok = client.post(
            "/api/prescription/confirm",
            json={
                "document_id": doc_id,
                "diagnosis": "Viêm họng cấp",
                "preview_image_url": "javascript:alert(1)",
                "unexpected_evil_key": {"nested": "drop_me"},
                "medications": [{"name": "Paracetamol", "strength": "500mg"}],
            },
            headers=ORIGIN_HEADERS,
        )
        assert r_ok.status_code == 200
        saved = r_ok.get_json()["data"]
        assert "unexpected_evil_key" not in saved
        assert "preview_image_url" not in saved
        assert saved["diagnosis"] == "Viêm họng cấp"

        with flask_app.app_context():
            refreshed = db.session.get(MedicalDocument, doc_id)
            parsed = json.loads(refreshed.parsed_data)
            assert "unexpected_evil_key" not in parsed
            assert refreshed.doc_type == "prescription"
    finally:
        with flask_app.app_context():
            db.session.query(MedicalDocument).filter_by(id=doc_id).delete()
            db.session.query(User).filter(User.id.in_([u1_id, u2_id])).delete()
            db.session.commit()


# ---------------------------------------------------------------------------
# H-04 & L-03: OTP send IP rate limit, login IP spraying cap & memory eviction
# ---------------------------------------------------------------------------

def test_h04_otp_send_ip_rate_limit_and_login_spraying_cap():
    rate_limit_service.clear_all()
    try:
        client = flask_app.test_client()
        ip_headers = {**ORIGIN_HEADERS, "REMOTE_ADDR": "198.51.100.77"}

        # First 5 OTP send requests across distinct emails succeed (or non-429)
        for i in range(5):
            r = client.post(
                "/api/auth/otp/send",
                json={"identifier": f"spray_{i}_{uuid.uuid4().hex[:6]}@example.com", "purpose": "login_2fa"},
                headers=ip_headers,
                environ_base={"REMOTE_ADDR": "198.51.100.77"},
            )
            assert r.status_code != 429

        # 6th request from same IP must be blocked with 429
        r_blocked = client.post(
            "/api/auth/otp/send",
            json={"identifier": f"spray_6_{uuid.uuid4().hex[:6]}@example.com", "purpose": "login_2fa"},
            headers=ip_headers,
            environ_base={"REMOTE_ADDR": "198.51.100.77"},
        )
        assert r_blocked.status_code == 429

        # IP-level login spraying cap blocks after max_attempts across different users
        for _ in range(3):
            assert rate_limit_service.check_login_ip_rate_limit("203.0.113.9", max_attempts=3, window_seconds=60)
        assert not rate_limit_service.check_login_ip_rate_limit("203.0.113.9", max_attempts=3, window_seconds=60)
    finally:
        rate_limit_service.clear_all()


def test_l03_memory_rate_limit_backend_evicts_and_bounds_size():
    backend = MemoryRateLimitBackend(max_entries=100, cleanup_interval=1.0)
    for i in range(150):
        backend.check_and_increment(f"k:{i}", max_requests=5, window_seconds=60)
    assert len(backend._store) <= 100


# ---------------------------------------------------------------------------
# M-02: GROQ_BASE_URL strict allowlist
# ---------------------------------------------------------------------------

def test_m02_groq_base_url_allowlist(monkeypatch):
    client = _GroqModels(api_key="test-key")

    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    assert client._endpoint() == "https://api.groq.com/openai/v1/chat/completions"

    for bad_url in (
        "http://api.groq.com/openai/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://evil.example.com/openai/v1",
        "https://api.groq.com/other/path",
        "https://api.groq.com/openai/v1?foo=bar",
    ):
        monkeypatch.setenv("GROQ_BASE_URL", bad_url)
        with pytest.raises(_GroqHTTPError):
            client._endpoint()


# ---------------------------------------------------------------------------
# M-05 & L-04: Flask production docs gating & /.well-known/security.txt
# ---------------------------------------------------------------------------

def test_m05_flask_docs_hidden_in_production_and_l04_security_txt(monkeypatch):
    client = flask_app.test_client()

    # L-04: RFC 9116 security.txt available
    r_sec = client.get("/.well-known/security.txt")
    assert r_sec.status_code == 200
    assert "text/plain" in r_sec.content_type
    assert "Contact:" in r_sec.get_data(as_text=True)
    assert "Expires:" in r_sec.get_data(as_text=True)

    # M-05: /docs and /openapi.json return 404 when production mode enabled
    monkeypatch.setattr(settings.server, "env", "production")
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# ---------------------------------------------------------------------------
# L-02: Appointment booking input length & format validation
# ---------------------------------------------------------------------------

def test_l02_appointment_input_validation():
    base = {
        "facility_name": "Bệnh viện Bạch Mai",
        "specialty": "Nội tổng quát",
        "appointment_date": "2026-12-20",
        "appointment_time": "09:30",
        "patient_name": "Nguyễn Văn An",
        "patient_phone": "0912345678",
        "note": "Khám định kỳ",
    }

    # Oversized note rejected
    ok, res, code = create_user_appointment(1, {**base, "note": "A" * 1001})
    assert not ok and code == 400

    # Invalid date format rejected
    ok, res, code = create_user_appointment(1, {**base, "appointment_date": "not-a-date"})
    assert not ok and code == 400

    # Invalid time format rejected
    ok, res, code = create_user_appointment(1, {**base, "appointment_time": "invalid-time"})
    assert not ok and code == 400

    # Invalid phone rejected
    ok, res, code = create_user_appointment(1, {**base, "patient_phone": "123"})
    assert not ok and code == 400

    # Non-dict payload rejected cleanly without 500
    ok, res, code = create_user_appointment(1, ["not", "a", "dict"])  # type: ignore[arg-type]
    assert not ok and code == 400
