"""
tests/test_google_oauth_unconfigured.py
Regression test suite verifying fail-closed Google Quick Login behavior when
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are missing or left as template placeholders.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "templates", "index.html")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "static", "js", "app.js")
ENV_EXAMPLE_PATH = os.path.join(PROJECT_ROOT, ".env.example")


class TestGoogleOAuthUnconfiguredBackend:
    """Backend must fail closed when Google OAuth keys are unset or placeholders."""

    @pytest.mark.parametrize(
        "client_id,client_secret",
        [
            ("", ""),
            ("your_google_client_id_here", "your_google_client_secret_here"),
            ("YOUR_GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_SECRET"),
            ("<client-id>", "<client-secret>"),
            ("123456-real.apps.googleusercontent.com", ""),
            ("123456-real.apps.googleusercontent.com", "your_google_client_secret_here"),
        ],
    )
    def test_google_login_json_rejects_missing_or_placeholder_keys(
        self, client, monkeypatch, client_id, client_secret
    ):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", client_id)
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", client_secret)

        res = client.get("/api/auth/google/login?intent=login&format=json")
        assert res.status_code == 503
        data = res.get_json()
        assert data["success"] is False
        assert data["configured"] is False
        assert "auth_url" not in data

    @pytest.mark.parametrize(
        "client_id,client_secret",
        [
            ("", ""),
            ("your_google_client_id_here", "your_google_client_secret_here"),
        ],
    )
    def test_google_login_redirect_never_points_to_google_when_unconfigured(
        self, client, monkeypatch, client_id, client_secret
    ):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", client_id)
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", client_secret)

        res = client.get("/api/auth/google/login?intent=login")
        assert res.status_code == 302
        location = res.headers.get("Location", "")
        assert "accounts.google.com" not in location
        assert "google_auth=error" in location
        assert "error_reason=unconfigured" in location

    def test_google_id_token_endpoint_rejects_placeholder_client_id(self, client, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "your_google_client_id_here")

        res = client.post("/api/auth/google", json={"credential": "some_token"})
        assert res.status_code == 503
        data = res.get_json()
        assert data["success"] is False

    def test_google_login_succeeds_with_valid_credentials(self, client, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "1234567890-valid.apps.googleusercontent.com")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-valid-secret-value")
        monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

        res = client.get("/api/auth/google/login?intent=login&format=json")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["configured"] is True
        assert data["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=1234567890-valid.apps.googleusercontent.com" in data["auth_url"]


class TestGoogleOAuthFrontendAndTemplateHygiene:
    """Frontend must not expose hardcoded personal Gmail accounts or dead mock modal."""

    def test_index_html_has_no_mock_google_modal_or_personal_gmails(self):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        assert 'id="google-account-modal"' not in html
        assert "Mô phỏng trải nghiệm Google Identity" not in html
        assert "startGoogleAccountSelection(" not in html
        assert "accounts.google.com/gsi/client" not in html

        for leaked_email in (
            "lecongluyen9a1@gmail.com",
            "lecongluyenwork26@gmail.com",
            "anktusneiem@gmail.com",
            "nguyenngocanhtufb@gmail.com",
        ):
            assert leaked_email not in html

    def test_app_js_has_no_dead_mock_google_chooser_handlers(self):
        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()

        for dead_symbol in (
            "google-account-modal",
            "startGoogleAccountSelection",
            "submitCustomGoogleAccount",
            "setGoogleModalState",
            "closeGoogleAccountModal",
        ):
            assert dead_symbol not in js

    def test_env_example_uses_api_google_callback_route(self):
        with open(ENV_EXAMPLE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback" in content

    def test_handle_google_signin_unconfigured_shows_toast_without_redirect(self):
        if not shutil.which("node"):
            pytest.skip("Node.js not available in environment")

        script = r"""
const fs = require('fs');
const vm = require('vm');
const appJs = fs.readFileSync('static/js/app.js', 'utf8');

const assignedUrls = [];
const toasts = [];
const btn = {
  disabled: false,
  innerHTML: '<span>Đăng nhập bằng Google</span>',
};

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  AbortController,
  URLSearchParams,
  encodeURIComponent,
  window: {
    navigator: { userAgent: 'Mozilla/5.0 Chrome/125.0' },
    location: {
      search: '',
      pathname: '/',
      hash: '',
      assign: (u) => assignedUrls.push(u),
    },
    history: { replaceState: () => {} },
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  },
  document: {
    getElementById: (id) => (id === 'btn-google-signin' ? btn : null),
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
  fetch: async () => ({
    ok: false,
    status: 503,
    json: async () => ({
      success: false,
      configured: false,
      error: 'Chưa cấu hình GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET trong .env.',
    }),
  }),
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(appJs, sandbox);

sandbox.showMedicalToast = (msg, type) => toasts.push({ msg, type });
sandbox.currentLang = 'vi';

(async () => {
  await sandbox.handleGoogleSignIn('login');
  console.log(JSON.stringify({
    assignedUrls,
    toasts,
    btnDisabled: btn.disabled,
    btnRestored: btn.innerHTML === '<span>Đăng nhập bằng Google</span>',
  }));
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
        assert result["assignedUrls"] == []
        assert result["btnDisabled"] is False
        assert result["btnRestored"] is True
        assert len(result["toasts"]) == 1
        assert result["toasts"][0]["type"] == "warning"
        assert "[object Object]" not in str(result["toasts"][0]["msg"])
        assert "Google" in result["toasts"][0]["msg"]

    def test_google_button_recovers_after_bfcache_back_and_toggle_auth_mode(self):
        """Reproduces Back-from-Google + switch to Register: text must never be injected into animate-spin."""
        if not shutil.which("node"):
            pytest.skip("Node.js not available in environment")

        script = r"""
const fs = require('fs');
const vm = require('vm');
const appJs = fs.readFileSync('static/js/app.js', 'utf8');

const windowListeners = {};
const initialHtml = '<svg class="w-5 h-5"></svg><span data-i18n="btn_google_signin" class="font-semibold text-white">Đăng nhập bằng Google</span>';

// Minimal DOM element tracking innerHTML & child spans accurately
function makeGoogleButton() {
  return {
    id: 'btn-google-signin',
    disabled: false,
    dataset: {},
    innerHTML: initialHtml,
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    querySelector(sel) {
      if (sel === 'span[data-i18n="btn_google_signin"]') {
        if (!this.innerHTML.includes('data-i18n="btn_google_signin"')) return null;
        return {
          set innerText(v) {
            btn.innerHTML = btn.innerHTML.replace(/(<span[^>]*data-i18n="btn_google_signin"[^>]*>)[^<]*(<\/span>)/, `$1${v}$2`);
          },
          set className(_) {},
        };
      }
      if (sel === 'span') {
        const m = this.innerHTML.match(/<span([^>]*)>([^<]*)<\/span>/);
        if (!m) return null;
        return {
          set innerText(v) {
            btn.innerHTML = btn.innerHTML.replace(/<span([^>]*)>[^<]*<\/span>/, `<span$1>${v}</span>`);
          },
          set className(_) {},
        };
      }
      return null;
    },
  };
}

const btn = makeGoogleButton();
const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  AbortController,
  URLSearchParams,
  encodeURIComponent,
  window: {
    navigator: { userAgent: 'Mozilla/5.0 Chrome/125.0' },
    location: { search: '', pathname: '/', hash: '', assign: () => {} },
    history: { replaceState: () => {} },
    addEventListener: (ev, fn) => {
      windowListeners[ev] = windowListeners[ev] || [];
      windowListeners[ev].push(fn);
    },
    removeEventListener: () => {},
    dispatchEvent: () => {},
  },
  document: {
    getElementById: (id) => (id === 'btn-google-signin' ? btn : null),
    querySelector: (sel) => {
      if (sel === '#btn-google-signin span[data-i18n="btn_google_signin"]') {
        return btn.querySelector('span[data-i18n="btn_google_signin"]');
      }
      if (sel === '#btn-google-signin span') {
        return btn.querySelector('span');
      }
      return null;
    },
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
  fetch: async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      success: true,
      configured: true,
      auth_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
    }),
  }),
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(appJs, sandbox);

(async () => {
  // 1. User clicks Google Sign-In -> redirects to Google with button in loading state
  await sandbox.handleGoogleSignIn('login');

  // 2a. User presses browser Back (bfcache restores page via pageshow)
  (windowListeners.pageshow || []).forEach(fn => fn({ persisted: true }));
  const afterPageshow = { disabled: btn.disabled, html: btn.innerHTML };

  // 2b. Even if pageshow didn't fire, switching to Register tab must restore button & never spin text
  await sandbox.handleGoogleSignIn('login');
  sandbox.toggleAuthMode('register');
  const afterToggle = { disabled: btn.disabled, html: btn.innerHTML };

  console.log(JSON.stringify({ afterPageshow, afterToggle }));
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

        assert result["afterPageshow"]["disabled"] is False
        assert "animate-spin" not in result["afterPageshow"]["html"]
        assert "Đang chuyển tới Google..." not in result["afterPageshow"]["html"]

        assert result["afterToggle"]["disabled"] is False
        assert "animate-spin" not in result["afterToggle"]["html"]
        assert "Đang chuyển tới Google..." not in result["afterToggle"]["html"]
        assert 'data-i18n="btn_google_signin"' in result["afterToggle"]["html"]
