"""Tests for appointment booking confirmation email delivery (Gmail / registered email)."""

import os
import smtplib
import tempfile
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-32bytes-long-for-testing")
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")
os.environ.setdefault("DEV_SEED_USERS", "false")
os.environ.setdefault("FLASK_DEBUG", "0")

from app import create_app
from core.models import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _make_client():
    tmpdir = tempfile.TemporaryDirectory()
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SECRET_KEY": "test-secret-key-32bytes-long-for-testing",
            "SESSION_COOKIE_SECURE": False,
            "UPLOAD_FOLDER": tmpdir.name,
        }
    )
    return flask_app, tmpdir


def test_booking_sends_confirmation_email_to_registered_gmail(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, server, port, timeout=10):
            self.server = server
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, user, pwd):
            pass

        def sendmail(self, sender, recipients, raw_msg):
            sent_messages.append({"sender": sender, "recipients": recipients, "raw": raw_msg})

    monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-demo")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    flask_app, tmpdir = _make_client()
    try:
        client = flask_app.test_client()
        client.post(
            "/api/auth/register",
            json={
                "identifier": "patient.gmail@gmail.com",
                "full_name": "Tran Thi Binh",
                "password": "Password123",
            },
        )
        client.post(
            "/api/auth/login",
            json={"identifier": "patient.gmail@gmail.com", "password": "Password123"},
        )

        res = client.post(
            "/api/appointments",
            headers={"Origin": "http://localhost"},
            json={
                "facility_id": "fac_vinmec",
                "facility_name": "BVĐK Quốc Tế Vinmec Central Park",
                "facility_address": "208 Nguyễn Hữu Cảnh, TP.HCM",
                "specialty": "Tim mạch",
                "appointment_date": "2026-12-01",
                "appointment_time": "08:00 - 09:30",
                "patient_name": "Tran Thi Binh",
                "patient_phone": "0912345678",
                "note": "Khám định kỳ",
            },
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert data["email_sent"] is True
        assert data["email_recipient"] == "patient.gmail@gmail.com"
        assert "patient.gmail@gmail.com" in data["message"]

        assert len(sent_messages) == 1
        assert sent_messages[0]["recipients"] == ["patient.gmail@gmail.com"]
        assert "patient.gmail@gmail.com" in sent_messages[0]["raw"]
    finally:
        with flask_app.app_context():
            db.session.remove()
            db.drop_all()
        tmpdir.cleanup()


def test_booking_prefers_explicit_email_and_succeeds_even_if_smtp_fails(monkeypatch):
    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("SMTP unreachable")

    monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-demo")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(smtplib, "SMTP", FailingSMTP)

    flask_app, tmpdir = _make_client()
    try:
        client = flask_app.test_client()
        client.post(
            "/api/auth/register",
            json={
                "identifier": "0912345679",
                "full_name": "Le Van Cuong",
                "password": "Password123",
            },
        )
        client.post(
            "/api/auth/login",
            json={"identifier": "0912345679", "password": "Password123"},
        )

        res = client.post(
            "/api/appointments",
            headers={"Origin": "http://localhost"},
            json={
                "facility_id": "fac_115",
                "facility_name": "Bệnh viện Nhân dân 115",
                "specialty": "Khám tổng quát",
                "appointment_date": "2026-12-05",
                "appointment_time": "09:30 - 11:00",
                "patient_name": "Le Van Cuong",
                "patient_phone": "0912345679",
                "patient_email": "custom.inbox@gmail.com",
            },
        )
        # Appointment is still saved safely even when SMTP fails
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert data["email_recipient"] == "custom.inbox@gmail.com"
        assert data["email_sent"] is False
    finally:
        with flask_app.app_context():
            db.session.remove()
            db.drop_all()
        tmpdir.cleanup()


def test_email_includes_previsit_summary_table_when_attached(monkeypatch):
    from email import message_from_string
    from core.auth.email_service import email_service

    captured = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, user, pwd):
            pass

        def sendmail(self, sender, recipients, raw_msg):
            captured.append(raw_msg)

    monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-demo")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    ok = email_service.send_appointment_confirmation(
        "patient.summary@gmail.com",
        {
            "id": 77,
            "facility_name": "Bệnh viện Chợ Rẫy",
            "facility_address": "201B Nguyễn Chí Thanh, Q.5, TP.HCM",
            "specialty": "Tim mạch",
            "appointment_date": "2026-12-10",
            "appointment_time": "08:00 - 09:30",
            "patient_name": "Nguyen Van An",
            "patient_phone": "0909123456",
            "note": "Đau ngực nhẹ khi gắng sức",
            "pre_visit_summary": {
                "is_confirmed": True,
                "part_a_patient_facts": {
                    "chief_complaint": "Đau tức ngực nhẹ 3 ngày",
                    "duration": "3 ngày",
                    "symptoms_present": ["Khó thở nhẹ", "Hồi hộp"],
                    "patient_reported_history": {
                        "allergies": {"status": "denied", "text": ""},
                        "medications": {"status": "reported", "text": "Amlodipine 5mg"},
                    },
                },
                "part_b_system_assessment": {
                    "triage_badge": "assessed",
                    "triage_status": "Cần khám chuyên khoa sớm",
                    "recommended_specialist": "Tim mạch",
                    "care_approach": "Khám tim mạch và đo ECG",
                },
            },
        },
    )
    assert ok is True
    assert len(captured) == 1
    msg = message_from_string(captured[0])
    decoded_parts = [
        part.get_payload(decode=True).decode("utf-8", errors="ignore")
        for part in msg.walk()
        if part.get_content_type() in ("text/plain", "text/html")
    ]
    joined = "\n".join(decoded_parts)
    assert "Bảng Tóm Tắt Thông Tin Trước Khám" in joined
    assert "Đau tức ngực nhẹ 3 ngày" in joined
    assert "Amlodipine 5mg" in joined
    assert "Cần khám chuyên khoa sớm" in joined
    assert "Khám tim mạch và đo ECG" in joined


def test_frontend_booking_email_input_and_toast_contract():
    html = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    app_js = (PROJECT_ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="book-modal-email"' in html
    assert 'id="book-summary-preview"' in html
    assert 'id="appointment-detail-modal"' in html
    assert 'onclick="openBookingPrevisitIntake()"' in html
    assert "openAppointmentDetailModal(" in html
    assert "function resetFacilityBookingForm()" in app_js
    assert "function openBookingPrevisitIntake()" in app_js
    assert "let bookingIntakeStartedForModal = false;" in app_js
    assert "resetFacilityBookingForm();" in app_js
    assert "function buildBookingSummaryPreviewHtml(" in app_js
    assert "patient_email: patEmail" in app_js
    assert "data.email_sent && data.email_recipient" in app_js
