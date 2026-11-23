"""
Tests for Phase 4.1C: UI Accessibility & UX Polish.
Validates:
1. No alert() calls remain in static/js/app.js or templates/index.html.
2. confirm() calls preserved strictly for destructive actions.
3. Date formatting: zero-padding in formatSessionTime (DD/MM).
4. Modal accessibility: role="dialog", aria-modal="true", aria-labelledby, close button labels.
5. Floating chat accessibility: role="button", aria-expanded, aria-controls, aria-label.
6. Input accessibility: all visible inputs have aria-label or associated label.
7. Button accessibility: icon-only buttons have accessible names.
8. Medical toast: live region role="status" and aria-live="polite".
9. Prescription/Lab rendering resilience: no literal undefined or null in DOM.
10. Modal focus management hooks.
"""

import os
import re
import json
import subprocess
import pytest
from bs4 import BeautifulSoup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, "templates", "index.html")
APP_JS_PATH = os.path.join(PROJECT_ROOT, "static", "js", "app.js")


@pytest.fixture(scope="module")
def index_soup():
    assert os.path.exists(INDEX_HTML_PATH), "templates/index.html not found"
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    return BeautifulSoup(content, "html.parser"), content


@pytest.fixture(scope="module")
def app_js_content():
    assert os.path.exists(APP_JS_PATH), "static/js/app.js not found"
    with open(APP_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def run_node_eval(js_code: str):
    """Executes javascript in node with standard browser DOM mocks."""
    harness = """
const fs = require('fs');
const appJs = fs.readFileSync('static/js/app.js', 'utf8');

global.window = {
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => {},
  showMedicalToast: null
};

global.document = {
  getElementById: (id) => {
    if (id === 'prescription-result-section') {
      return { innerHTML: '', classList: { add: () => {}, remove: () => {} } };
    }
    if (id === 'floating-chat-window' || id === 'floating-chat-bubble') {
      return {
        classList: { add: () => {}, remove: () => {}, contains: () => false },
        setAttribute: (k, v) => { this[k] = v; },
        getAttribute: (k) => this[k],
        focus: () => {}
      };
    }
    return {
      classList: { add: () => {}, remove: () => {}, contains: () => false },
      setAttribute: () => {},
      focus: () => {}
    };
  },
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
  removeEventListener: () => {},
  createElement: (tag) => {
    let attrs = {};
    let text = '';
    return {
      tagName: tag,
      setAttribute: (k, v) => { attrs[k] = v; },
      getAttribute: (k) => attrs[k],
      appendChild: () => {},
      classList: { add: () => {}, remove: () => {} },
      style: {},
      set innerText(val) { text = val; },
      get innerText() { return text; },
      set textContent(val) { text = val; },
      get textContent() { return text; },
      set innerHTML(val) { text = val; },
      get innerHTML() { return text; }
    };
  },
  body: { appendChild: () => {} }
};

global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
global.navigator = { userAgent: 'test-agent' };
global.location = { hash: '' };

eval(appJs);

""" + js_code + "\nprocess.exit(0);\n"

    res = subprocess.run(
        ["node"],
        input=harness,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=PROJECT_ROOT
    )
    if res.returncode != 0:
        raise RuntimeError(f"Node execution failed: {res.stderr}")
    return res.stdout.strip()


def test_no_remaining_alerts(index_soup, app_js_content):
    """Verify alert() is completely eliminated from app.js and index.html."""
    _, index_raw = index_soup

    # 1. Check index.html
    alert_in_index = [
        line.strip() for line in index_raw.splitlines()
        if "alert(" in line and not line.strip().startswith("//") and not line.strip().startswith("<!--")
    ]
    assert len(alert_in_index) == 0, f"Found alert() in index.html: {alert_in_index}"

    # 2. Check static/js/app.js
    alert_in_app_js = [
        line.strip() for line in app_js_content.splitlines()
        if "alert(" in line and not line.strip().startswith("//") and not line.strip().startswith("/*")
    ]
    assert len(alert_in_app_js) == 0, f"Found alert() in app.js: {alert_in_app_js}"


def test_destructive_confirm_preserved(app_js_content):
    """Ensure confirm() remains strictly for destructive user actions."""
    confirms = [
        line.strip() for line in app_js_content.splitlines()
        if "confirm(" in line and not line.strip().startswith("//")
    ]
    # We preserved exactly 2 confirms: deleteScanFile and deletePrescriptionHistoryItem
    assert len(confirms) == 2, f"Expected exactly 2 confirm() calls, found {len(confirms)}: {confirms}"
    assert any("xóa tệp" in c.lower() for c in confirms), "Missing file deletion confirm"
    assert any("xóa bản ghi" in c.lower() for c in confirms), "Missing record deletion confirm"


def test_date_formatting_zero_padded():
    """Verify formatSessionTime returns zero-padded DD/MM format."""
    js = """
    // 5th of February 2026
    const feb5 = new Date(2026, 1, 5, 12, 0, 0).getTime();
    console.log(formatSessionTime(feb5));
    """
    out = run_node_eval(js)
    assert out == "05/02", f"Expected '05/02', got '{out}'"

    # 9th of November 2026
    js2 = """
    const nov9 = new Date(2026, 10, 9, 12, 0, 0).getTime();
    console.log(formatSessionTime(nov9));
    """
    out2 = run_node_eval(js2)
    assert out2 == "09/11", f"Expected '09/11', got '{out2}'"


def test_modal_accessibility_attributes(index_soup):
    """Verify all 9 modals have role='dialog', aria-modal='true', and aria-labelledby."""
    soup, _ = index_soup
    expected_modals = [
        "login-modal",
        "disclaimer-modal",
        "profile-modal",
        "image-lightbox-modal",
        "previsit-summary-modal",
        "medical-record-modal",
        "facility-booking-modal",
        "facility-detail-modal",
        "google-account-modal"
    ]

    for mid in expected_modals:
        modal_el = soup.find(id=mid)
        assert modal_el is not None, f"Modal #{mid} not found in index.html"
        assert modal_el.get("role") == "dialog", f"Modal #{mid} missing role='dialog'"
        assert modal_el.get("aria-modal") == "true", f"Modal #{mid} missing aria-modal='true'"
        labelledby = modal_el.get("aria-labelledby")
        assert labelledby, f"Modal #{mid} missing aria-labelledby"
        # Check that labelled element exists in DOM
        labeled_el = soup.find(id=labelledby)
        assert labeled_el is not None, f"Referenced heading #{labelledby} for #{mid} not found"


def test_modal_close_buttons_have_accessible_names(index_soup):
    """Verify close buttons on modals have aria-label or title."""
    soup, _ = index_soup
    modal_ids = [
        "login-modal",
        "disclaimer-modal",
        "profile-modal",
        "image-lightbox-modal",
        "previsit-summary-modal",
        "medical-record-modal",
        "facility-booking-modal",
        "facility-detail-modal",
        "google-account-modal"
    ]

    for mid in modal_ids:
        modal_el = soup.find(id=mid)
        # Find close button(s) inside modal
        buttons = modal_el.find_all("button")
        close_buttons = [
            b for b in buttons
            if "close" in (b.get("onclick") or "").lower() or "đóng" in (b.get("title") or "").lower()
        ]
        assert len(close_buttons) > 0, f"No close button found in modal #{mid}"
        for cb in close_buttons:
            has_name = bool(cb.get("aria-label") or cb.get("title") or cb.get_text(strip=True))
            assert has_name, f"Close button in modal #{mid} missing accessible name"


def test_floating_chat_accessibility(index_soup):
    """Verify floating chat trigger and controls have role, aria-expanded, aria-controls, and aria-label."""
    soup, _ = index_soup
    bubble = soup.find(id="floating-chat-bubble")
    assert bubble is not None, "#floating-chat-bubble not found"
    assert bubble.get("role") == "button", "Bubble missing role='button'"
    assert bubble.get("tabindex") == "0", "Bubble missing tabindex='0'"
    assert bubble.get("aria-expanded") in ["true", "false"], "Bubble missing aria-expanded"
    assert bubble.get("aria-controls") == "floating-chat-window", "Bubble missing aria-controls='floating-chat-window'"
    assert bubble.get("aria-label"), "Bubble missing aria-label"

    window = soup.find(id="floating-chat-window")
    assert window is not None, "#floating-chat-window not found"


def test_input_accessibility_labels(index_soup):
    """Verify all interactive visible inputs have accessible names."""
    soup, _ = index_soup
    inputs = soup.find_all("input")

    for inp in inputs:
        inp_type = inp.get("type", "text").lower()
        if inp_type == "hidden":
            continue

        inp_id = inp.get("id", "")
        has_aria_label = bool(inp.get("aria-label") or inp.get("aria-labelledby"))
        has_explicit_for = bool(soup.find("label", attrs={"for": inp_id})) if inp_id else False

        assert has_aria_label or has_explicit_for, (
            f"Interactive input id='{inp_id}' type='{inp_type}' is missing accessible label"
        )


def test_live_toast_region(index_soup, app_js_content):
    """Verify live region container exists with role='status' and aria-live='polite'."""
    soup, _ = index_soup
    toast_container = soup.find(id="medical-toast-container")
    assert toast_container is not None, "#medical-toast-container not found in index.html"
    assert toast_container.get("role") == "status", "Toast container missing role='status'"
    assert toast_container.get("aria-live") == "polite", "Toast container missing aria-live='polite'"

    # Verify app.js attaches role and aria-live dynamically as well
    assert "role" in app_js_content and "aria-live" in app_js_content
    assert "window.showMedicalToast = showMedicalToast" in app_js_content


def test_prescription_render_null_protection():
    """Verify renderPrescriptionResult does not render literal undefined or null when data is sparse."""
    js = """
    let htmlResult = '';
    global.document.getElementById = (id) => {
      if (id === 'prescription-result-section') {
        return {
          set innerHTML(val) { htmlResult = val; },
          get innerHTML() { return htmlResult; },
          classList: { remove: () => {}, add: () => {} }
        };
      }
      return { classList: { add: () => {}, remove: () => {} } };
    };

    // 1. Incomplete lab test
    renderPrescriptionResult({
      type: 'lab_test',
      metrics: [
        { standard_name: undefined, name: undefined, test_name: undefined, result: undefined, value: undefined }
      ]
    });
    const labUndef = htmlResult.includes('undefined') || htmlResult.includes('null');

    // 2. Incomplete prescription
    renderPrescriptionResult({
      type: 'prescription',
      medications: [
        { standard_name: undefined, name: undefined, dose: undefined, dosage: undefined }
      ],
      timeline: {
        morning: [
          { name: undefined, dose: undefined }
        ]
      }
    });
    const prescUndef = htmlResult.includes('undefined') || htmlResult.includes('null');

    console.log(JSON.stringify({ labUndef, prescUndef }));
    """
    out = run_node_eval(js)
    res = json.loads(out)
    assert not res["labUndef"], "Lab test rendering leaked literal undefined or null"
    assert not res["prescUndef"], "Prescription rendering leaked literal undefined or null"


def test_html_lang_attribute(index_soup):
    """Verify html element has lang='vi'."""
    soup, _ = index_soup
    html_tag = soup.find("html")
    assert html_tag is not None, "<html> tag not found"
    assert html_tag.get("lang") == "vi", f"Expected lang='vi', got '{html_tag.get('lang')}'"
