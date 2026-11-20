"""
Phase 5 regression tests:
- EmailService / SmsService honest failure (no fake dev True on SMTP fail, no plaintext OTP stdout leak)
- User.account_status != 'active' enforcement on login, /api/auth/me, FastAPI require_authenticated_user
- Google OAuth unconfigured honest toast (no broken fake modal popup)
- CSKCB Facility booking resolution without CarePlus fallback & server-side canonicalization
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app as flask_app
from core.appointment_service import create_user_appointment
from core.email_service import EmailService
from core.facilities_service import load_facilities_data
from core.main_fastapi import app as fastapi_app
from core.models import MedicalAppointment, User, db
from core.sms_service import SmsService


APP_JS_PATH = Path("static/js/app.js")


def _make_signed_session(user_id: int) -> str:
    serializer = flask_app.session_interface.get_signing_serializer(flask_app)
    return serializer.dumps({"user_id": user_id})


def _run_node(script: str) -> str:
    setup = """
global.window = global;
global.window.addEventListener = () => null;
global.window.removeEventListener = () => null;
global.localStorage = { getItem: () => null, setItem: () => null, removeItem: () => null };
global.sessionStorage = { getItem: () => null, setItem: () => null, removeItem: () => null };
const elements = {};
global.__setEl = (id, obj) => { elements[id] = obj; };
global.document = {
  activeElement: null,
  getElementById: (id) => elements[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => null,
  createElement: () => ({ classList: { add: () => null, remove: () => null } })
};
global.navigator = { clipboard: null };
global.location = { search: '', pathname: '', hash: '' };
"""
    full_script = (
        f"{setup}\n{APP_JS_PATH.read_text(encoding='utf-8')}\n"
        f"(async () => {{\n{script}\n}})().then(() => process.exit(0)).catch(err => {{ console.error(err); process.exit(1); }});"
    )
    res = subprocess.run(
        ["node"],
        input=full_script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    if res.returncode != 0:
        raise AssertionError(f"Node error ({res.returncode}): {res.stderr}")
    return res.stdout


def test_email_and_sms_services_no_fake_success_and_no_otp_leak(monkeypatch, capsys):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ALLOW_DEV_OTP_SIMULATOR", "0")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("FLASK_DEBUG", "true")

    # 1. Unconfigured EmailService returns False honestly
    monkeypatch.setenv("SMTP_SERVER", "")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    es_unconf = EmailService()
    assert es_unconf.send_verification_otp("user@example.com", "654321", purpose="reset_pwd") is False
    out = capsys.readouterr().out
    assert "654321" not in out

    # 2. Configured EmailService failing SMTP MUST return False even in ENV=development and NOT print OTP
    monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "badpass123")
    es_fail = EmailService()
    with patch("smtplib.SMTP", side_effect=RuntimeError("SMTP AUTH failed")):
        assert es_fail.send_verification_otp("user@example.com", "987654", purpose="register") is False
    out = capsys.readouterr().out
    assert "987654" not in out

    # 3. Unconfigured SmsService returns False honestly when not in test/simulator mode
    monkeypatch.setenv("SPEEDSMS_AUTH_TOKEN", "")
    ss_unconf = SmsService()
    assert ss_unconf.send_otp_sms("0912345678", "246810") is False
    out = capsys.readouterr().out
    assert "246810" not in out

    # 4. Non-type-2 SpeedSMS without sender returns False honestly
    monkeypatch.setenv("SPEEDSMS_AUTH_TOKEN", "fake_token_12345")
    monkeypatch.setenv("SPEEDSMS_SMS_TYPE", "5")
    monkeypatch.setenv("SPEEDSMS_SENDER", "")
    ss_no_sender = SmsService()
    assert ss_no_sender.send_otp_sms("0912345678", "112233") is False


def test_suspended_user_blocked_everywhere():
    with flask_app.app_context():
        u = User(email="suspended_phase5@example.com", full_name="Suspended User", account_status="suspended")
        u.set_password("StrongPass123!")
        db.session.add(u)
        db.session.commit()
        uid = u.id

    try:
        client = flask_app.test_client()

        # Wrong password still returns uniform 401 (VULN-02)
        r_bad = client.post(
            "/api/auth/login",
            json={"identifier": "suspended_phase5@example.com", "password": "WrongPassword!"},
            headers={"Origin": "http://localhost:8000"},
        )
        assert r_bad.status_code == 401

        # Correct password returns 403 for suspended account
        r_susp = client.post(
            "/api/auth/login",
            json={"identifier": "suspended_phase5@example.com", "password": "StrongPass123!"},
            headers={"Origin": "http://localhost:8000"},
        )
        assert r_susp.status_code == 403

        # Existing session cookie for suspended user is cleared on /api/auth/me & rejected on FastAPI routes
        cookie_val = _make_signed_session(uid)
        cookie_name = flask_app.config.get("SESSION_COOKIE_NAME", "session")
        client.set_cookie(cookie_name, cookie_val)
        me_res = client.get("/api/auth/me")
        assert me_res.status_code == 200
        assert me_res.get_json()["authenticated"] is False

        api_client = TestClient(fastapi_app, headers={"origin": "http://localhost:8000"})
        api_client.cookies.set(cookie_name, cookie_val)
        appt_res = api_client.get("/api/appointments")
        assert appt_res.status_code == 403
    finally:
        with flask_app.app_context():
            db.session.query(User).filter_by(id=uid).delete()
            db.session.commit()


def test_facility_booking_uses_actual_cskcb_facility_and_google_oauth_unconfigured():
    facilities = load_facilities_data()
    assert len(facilities) > 0
    real_fac = next((f for f in facilities if "careplus" not in str(f.get("ten", "")).lower()), facilities[0])
    real_id = str(real_fac["id"])

    # Server-side canonicalization binds exact CSKCB hospital name/address
    with flask_app.app_context():
        u = User(email="appt_phase5@example.com", full_name="Patient Booking")
        u.set_password("StrongPass123!")
        db.session.add(u)
        db.session.commit()
        uid = u.id

    try:
        ok, payload, status = create_user_appointment(
            uid,
            {
                "facility_id": real_id,
                "facility_name": "Wrong Sent Name",
                "appointment_date": "2026-12-20",
                "appointment_time": "08:00 - 09:30",
                "patient_name": "Nguyen Van A",
                "patient_phone": "0912345678",
            },
        )
        assert ok is True
        assert status == 201
        expected_name = (real_fac.get("ten") or real_fac.get("ten_ngan") or "").strip()
        assert payload["appointment"]["facility_name"] == expected_name
    finally:
        with flask_app.app_context():
            db.session.query(MedicalAppointment).filter_by(user_id=uid).delete()
            db.session.query(User).filter_by(id=uid).delete()
            db.session.commit()

    # Frontend JS test: openFacilityBookingModal & handleFacilityBookingSubmit never fall back to CarePlus
    _run_node("""
currentLang = 'vi';
currentUser = { id: 1, full_name: 'Patient Demo', phone_number: '0912345678' };
const nameEl = { innerText: '' };
const addrEl = { innerText: '' };
const idEl = { value: '' };
const dateEl = { value: '', min: '' };
const modalEl = { classList: { remove: () => null, add: () => null } };
__setEl('book-modal-facility-name', nameEl);
__setEl('book-modal-facility-address', addrEl);
__setEl('book-modal-facility-id', idEl);
__setEl('book-modal-date', dateEl);
__setEl('facility-booking-modal', modalEl);
__setEl('book-modal-spec', { value: 'Tim mạch' });
__setEl('book-modal-time', { value: '08:00 - 09:30' });
__setEl('book-modal-note', { value: 'Khám định kỳ' });
__setEl('book-modal-name', { value: 'Patient Demo' });
__setEl('book-modal-phone', { value: '0912345678' });

openFacilityBookingModal('cskcb_888', {
  id: 'cskcb_888',
  ten: 'Bệnh viện Chợ Rẫy',
  dia_chi_hien_thi_tren_web: '201B Nguyễn Chí Thanh, Quận 5, TP.HCM'
});

if (idEl.value !== 'cskcb_888' || nameEl.innerText !== 'Bệnh viện Chợ Rẫy') {
  throw new Error('Facility booking modal fell back to wrong hospital: ' + nameEl.innerText);
}

let postedBody = null;
global.fetch = async (url, opts) => {
  if (url === '/api/appointments') {
    postedBody = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ success: true }) };
  }
  if (url.startsWith('/api/auth/google/login')) {
    return { ok: true, json: async () => ({ success: false, configured: false }) };
  }
  return { ok: true, json: async () => ({}) };
};

let toastMsg = '';
showMedicalToast = (m) => { toastMsg = m; };
await handleFacilityBookingSubmit({ preventDefault: () => null });
if (!postedBody || postedBody.facility_id !== 'cskcb_888' || postedBody.facility_name !== 'Bệnh viện Chợ Rẫy') {
  throw new Error('Submitted wrong facility: ' + JSON.stringify(postedBody));
}

// Unconfigured Google OAuth must NOT show #google-account-modal
let googleModalOpened = false;
__setEl('google-account-modal', { classList: { remove: () => { googleModalOpened = true; }, add: () => null } });
await handleGoogleSignIn('login');
if (googleModalOpened) {
  throw new Error('Broken Google modal should not open when GOOGLE_CLIENT_ID is unconfigured');
}
if (!toastMsg.includes('Google')) {
  throw new Error('Expected informative Google OAuth toast, got: ' + toastMsg);
}
""")
