"""
tests/test_hardcode_hygiene.py
Regression suite ensuring zero hardcoded credentials/PII, static HMAC fallback secrets,
template placeholder bypasses, or stale static UI placeholders across the aaada72 architecture.
"""
import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "templates", "index.html")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "static", "js", "app.js")
AUTH_ROUTES_PATH = os.path.join(PROJECT_ROOT, "routes", "auth_routes.py")
OTP_SERVICE_PATH = os.path.join(PROJECT_ROOT, "core", "auth", "otp_service.py")


class TestGroup1NoHardcodedCredentialsOrPII:
    """Group 1: Eliminate hardcoded passwords, personal PII in JS, and static HMAC secrets."""

    def test_app_js_has_no_hardcoded_password_or_personal_pii(self):
        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()

        forbidden_tokens = (
            "MatKhau123@",
            "function quickLogin",
            "DEFAULT_USER_PROFILE",
            "function loadDemoPatientProfile",
            "0347047101",
            "0971221306",
            "Nguyễn Thành Khiêm",
        )
        for token in forbidden_tokens:
            assert token not in js, f"Found forbidden hardcoded PII/credential token in app.js: {token}"

    def test_no_static_hmac_secret_fallbacks_in_auth_or_otp(self):
        with open(AUTH_ROUTES_PATH, "r", encoding="utf-8") as f:
            auth_py = f.read()
        with open(OTP_SERVICE_PATH, "r", encoding="utf-8") as f:
            otp_py = f.read()

        assert "medimind-oauth-secret" not in auth_py
        assert "medimind-otp-fallback-dev-key-not-for-prod" not in otp_py


class TestGroup2PlaceholderBypassGuards:
    """Group 2: Template placeholder values from .env.example must be treated as unconfigured."""

    def test_secret_key_placeholder_rejected_in_production(self, monkeypatch):
        from core.settings import Settings

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "your_strong_random_secret_key_here")
        settings = Settings()

        with pytest.raises(RuntimeError):
            settings.get_effective_secret_key(testing=False)

    def test_google_maps_placeholder_not_exposed_in_index_or_fastapi_config(self, client, monkeypatch):
        from starlette.testclient import TestClient
        from core.main_fastapi import app as fastapi_app
        from core.settings import reset_settings

        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "your_google_maps_api_key_here")
        reset_settings()
        try:
            home = client.get("/")
            assert home.status_code == 200
            assert "your_google_maps_api_key_here" not in home.get_data(as_text=True)

            tc = TestClient(fastapi_app)
            fastapi_home = tc.get("/")
            assert fastapi_home.status_code == 200
            assert "your_google_maps_api_key_here" not in fastapi_home.text

            res = tc.get("/api/config/maps")
            assert res.status_code == 200
            data = res.json()
            assert data["has_key"] is False
            assert data["key"] == ""
        finally:
            reset_settings()

    def test_gemini_profile_placeholder_does_not_shadow_real_gemini_key(self, monkeypatch):
        from core.llm_provider import llm_provider

        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_CHAT_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_NUTRITION_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_OCR_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_CHAT_API_KEY", "your_chat_gemini_api_key_here")
        monkeypatch.setenv("GEMINI_NUTRITION_API_KEY", "your_nutrition_gemini_api_key_here")
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyValidFallbackKey1234567890")

        assert llm_provider.resolve_api_key(profile="chat") == "AIzaSyValidFallbackKey1234567890"
        assert llm_provider.resolve_api_key(profile="nutrition") == "AIzaSyValidFallbackKey1234567890"

    def test_dev_seed_password_placeholder_is_not_used_as_user_password(self, test_app, monkeypatch):
        from core.models import User, db, seed_default_users

        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEV_SEED_USERS", "true")
        monkeypatch.setenv("DEV_SEED_PASSWORD", "your_dev_seed_password_here")

        with test_app.app_context():
            existing = User.query.filter_by(email="benhnhan.an@gmail.com").first()
            if existing:
                db.session.delete(existing)
                db.session.commit()

            assert seed_default_users() is True
            seeded = User.query.filter_by(email="benhnhan.an@gmail.com").first()
            assert seeded is not None
            assert seeded.check_password("your_dev_seed_password_here") is False

    def test_prescription_service_resolves_gemini_key_dynamically_and_rejects_placeholder(self, monkeypatch):
        from core.ocr import prescription_service

        monkeypatch.setenv("GEMINI_API_KEY", "your_google_gemini_api_key_here")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        assert prescription_service._resolve_gemini_ocr_key() == ""

        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyDynamicOcrKey1234567890")
        assert prescription_service._resolve_gemini_ocr_key() == "AIzaSyDynamicOcrKey1234567890"

    def test_consultation_service_uses_dynamic_year_for_patient_id(self):
        consult_path = os.path.join(PROJECT_ROOT, "core", "chat", "consultation_service.py")
        with open(consult_path, "r", encoding="utf-8") as f:
            py = f.read()
        assert "BN-2026-" not in py

    def test_openrouter_and_groq_placeholders_treated_as_unconfigured(self, monkeypatch):
        from core.llm_provider import llm_provider
        from core.nutrition_ai import NutritionAIError, select_recipes

        monkeypatch.setenv("AI_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "your_groq_api_key_here")
        monkeypatch.setenv("OPENROUTER_API_KEY", "your_openrouter_api_key_here")
        monkeypatch.delenv("OPENROUTER_NUTRITION_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_CHAT_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_OCR_API_KEY", raising=False)

        assert llm_provider.is_groq_active() is False
        assert llm_provider.is_openrouter_active() is False
        assert llm_provider.is_configured(explicit_key="your_openrouter_api_key_here") is False

        with pytest.raises(NutritionAIError) as exc_info:
            select_recipes("gout", "bữa chính", [{"id": "r1"}], [])
        assert exc_info.value.code == "not_configured"

    def test_speedsms_placeholder_treated_as_unconfigured(self, monkeypatch):
        from core.sms_service import SmsService

        monkeypatch.setenv("SPEEDSMS_AUTH_TOKEN", "your_speedsms_token_here")
        svc = SmsService()
        assert svc.is_configured() is False

    def test_smtp_placeholder_treated_as_unconfigured(self, monkeypatch):
        from core.email_service import EmailService

        monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
        monkeypatch.setenv("SMTP_USERNAME", "your_email@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "your_app_specific_password_here")
        svc = EmailService()
        assert svc.is_configured() is False


class TestGroup3UiStaticPlaceholdersCleaned:
    """Group 3: Remove static fake profile defaults and dead mock strings."""

    def test_index_html_profile_modal_has_no_hardcoded_fake_email_or_id(self):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        assert "nguyenvana@gmail.com" not in html
        assert "#BN-2026-0004" not in html

    def test_app_js_has_no_dead_mock_google_i18n_or_hardcoded_fallback_patient_ids(self):
        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()

        assert "Mô phỏng trải nghiệm Google Identity" not in js
        assert "Xác thực Google Identity Services hoàn tất" not in js
        assert "currentUser.id || 8429" not in js
        assert "currentUser.id || 4" not in js
        assert "#BN-2026-" not in js

    def test_notification_engine_has_no_hardcoded_demo_items_and_renders_real_data(self):
        import json
        import shutil
        import subprocess

        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()

        for fake_token in (
            "demo_appt_1",
            "Multivitamin & Khoáng chất tổng hợp",
            "Men vi sinh Probiotic / Tiêu hóa",
            "Omega-3 Tinh khiết & Magie B6",
        ):
            assert fake_token not in js, f"Found hardcoded fake notification in app.js: {fake_token}"

        if not shutil.which("node"):
            pytest.skip("Node.js not available in environment")

        script = r"""
const fs = require('fs');
const vm = require('vm');
const appJs = fs.readFileSync('static/js/app.js', 'utf8');

let mockAppts = [];
const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  URLSearchParams,
  encodeURIComponent,
  window: {
    navigator: { userAgent: 'Mozilla/5.0 Chrome/125.0' },
    location: { search: '', pathname: '/', hash: '' },
    history: { replaceState: () => {} },
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  },
  document: {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    createElement: () => ({
      classList: { add: () => {}, remove: () => {}, contains: () => false },
      setAttribute: () => {},
      appendChild: () => {},
      style: {},
    }),
    body: { appendChild: () => {} },
    documentElement: { classList: { add: () => {}, remove: () => {}, contains: () => false } },
  },
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  navigator: { userAgent: 'Mozilla/5.0 Chrome/125.0' },
  fetch: async (url) => {
    if (url === '/api/appointments') {
      return { ok: true, json: async () => ({ appointments: mockAppts }) };
    }
    return { ok: false, status: 401, json: async () => ({}) };
  },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(appJs, sandbox);

(async () => {
  // Case 1: Empty state (no appointments, no prescriptions) -> 0 notifications
  mockAppts = [];
  vm.runInContext('cachedUserAppointments = []; cachedPrescriptionHistory = [];', sandbox);
  await sandbox.buildAllNotifications();
  const emptyCount = vm.runInContext('cachedAllNotifications.length', sandbox);

  // Case 2: Real appointment + real prescription -> real notifications only
  mockAppts = [{
    id: 77,
    facility_name: 'Bệnh viện Chợ Rẫy',
    specialty: 'Nội Tổng Quát',
    appointment_date: '2026-12-01',
    appointment_time: '08:00',
    status: 'confirmed',
  }];
  vm.runInContext(`cachedPrescriptionHistory = [{
    doc_type: 'prescription',
    diagnosis: 'Viêm họng cấp',
    facility: 'Bệnh viện Chợ Rẫy',
    summary: 'Paracetamol 500mg'
  }];`, sandbox);
  await sandbox.buildAllNotifications();
  const realNotifs = vm.runInContext('cachedAllNotifications', sandbox);

  console.log(JSON.stringify({ emptyCount, realNotifs }));
})();
"""
        proc = subprocess.run(
            ["node", "-e", script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        assert result["emptyCount"] == 0
        types = [n["type"] for n in result["realNotifs"]]
        assert "appointment" in types
        assert "medication" in types
        assert all(not n.get("isDemo") for n in result["realNotifs"])

