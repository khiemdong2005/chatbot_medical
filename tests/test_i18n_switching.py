"""Regression checks for the bilingual page controls."""

import subprocess
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "static" / "js" / "app.js"


def run_node(script: str) -> None:
    result = subprocess.run(
        ["node"],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_static_labels_and_placeholder_switch_both_ways():
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("const STATIC_VI_EN_TEXT = {")
    end = source.index("\nfunction toggleLanguageDropdown", start)
    snippet = source[start:end]
    script = f"""
const assert = require('assert');
let currentLang = 'en';
const textNode = {{ nodeValue: '  Gợi ý món ăn  ', parentElement: {{ closest: () => null }} }};
const userMessage = {{ nodeValue: 'Gợi ý món ăn', parentElement: {{ closest: () => ({{ id: 'chat-messages' }}) }} }};
const attrs = {{ placeholder: 'Ví dụ: gút, ít đường, không cay, bữa tối nhẹ…' }};
const input = {{
  closest: () => null,
  hasAttribute: key => Object.hasOwn(attrs, key),
  getAttribute: key => attrs[key],
  setAttribute: (key, value) => {{ attrs[key] = value; }}
}};
global.NodeFilter = {{ SHOW_TEXT: 4 }};
global.document = {{
  body: {{}},
  createTreeWalker: () => {{ const nodes = [textNode, userMessage]; return {{ nextNode: () => nodes.shift() || null }}; }},
  querySelectorAll: () => [input]
}};
{snippet}
translateStaticDom();
assert.strictEqual(textNode.nodeValue, '  Suggested Dishes  ');
assert.strictEqual(userMessage.nodeValue, 'Gợi ý món ăn');
assert.strictEqual(attrs.placeholder, 'Example: gout, low sugar, mild food, light dinner…');
currentLang = 'vi';
translateStaticDom();
assert.strictEqual(textNode.nodeValue, '  Gợi ý món ăn  ');
assert.strictEqual(attrs.placeholder, 'Ví dụ: gút, ít đường, không cay, bữa tối nhẹ…');
"""
    run_node(script)


def test_language_change_notifies_dynamic_views():
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("function setLanguage(lang) {")
    end = source.index("\nfunction applyLanguage()", start)
    snippet = source[start:end]
    script = f"""
const assert = require('assert');
let currentLang = 'vi';
let applied = 0;
const events = [];
global.Event = class {{ constructor(type) {{ this.type = type; }} }};
global.window = {{ dispatchEvent: event => events.push(event.type) }};
global.localStorage = {{ setItem: () => {{}} }};
function closeLanguageDropdown() {{}}
function populateDobDropdowns() {{}}
function applyLanguage() {{ applied++; }}
function updateAuthUI() {{}}
function switchEhrSubTab() {{}}
function translateStaticDom() {{}}
let currentEhrSubTab = 'ai';
{snippet}
setLanguage('en');
assert.strictEqual(currentLang, 'en');
assert.strictEqual(applied, 1);
assert.deepStrictEqual(events, ['medimind:langchange']);
"""
    run_node(script)


def test_saving_language_setting_uses_available_switcher():
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("async function handleSaveAllSettings() {")
    end = source.index("\n// ==========================================", start)
    snippet = source[start:end]
    script = f"""
const assert = require('assert');
let currentLang = 'vi';
let currentUser = null;
let selectedLanguage = null;
const values = {{ 'set-language': 'en', 'set-timezone': 'UTC+7', 'set-date-format': 'DD/MM/YYYY', 'set-theme-select': 'dark' }};
global.document = {{
  getElementById: id => values[id] ? {{ value: values[id], checked: false }} : null,
  body: {{ classList: {{ contains: () => true }} }}
}};
global.localStorage = {{ setItem: () => {{}} }};
function setLanguage(lang) {{ selectedLanguage = lang; currentLang = lang; }}
function applyThemeMode() {{}}
function toggleGlassThemeMode() {{}}
function showMedicalToast() {{}}
function broadcastTabEvent() {{}}
function applyUserPreferencesToUI(prefs) {{
  if (prefs.lang && prefs.lang !== currentLang) setLanguage(prefs.lang);
  return prefs;
}}
{snippet}
Promise.resolve(handleSaveAllSettings()).then(() => {{
  assert.strictEqual(selectedLanguage, 'en');
}}).catch(err => {{ console.error(err); process.exit(1); }});
"""
    run_node(script)


def test_previsit_and_ocr_i18n_sync_hooks():
    app_src = APP_JS.read_text(encoding="utf-8")
    previsit_src = (APP_JS.parent / "previsit-intake.js").read_text(encoding="utf-8")
    assert "medimind:langchange" in previsit_src
    assert '"PHÂN LOẠI: ĐƠN THUỐC BẢN GỐC": "CLASSIFICATION: ORIGINAL PRESCRIPTION"' in app_src
    assert '"Lịch hẹn khám của tôi": "My Medical Appointments"' in app_src


def test_nutrition_catalog_and_survey_static_copy_has_english():
    """Every Vietnamese label on the recipe catalog and meal survey must have an EN mapping."""
    import re
    from html.parser import HTMLParser

    app_src = APP_JS.read_text(encoding="utf-8")
    index = (APP_JS.parents[2] / "templates" / "index.html").read_text(encoding="utf-8")
    start = app_src.index("const STATIC_VI_EN_TEXT = {")
    block = app_src[start:app_src.index("\n};", start)]
    static_map = set(re.findall(r'^\s*"((?:[^"\\]|\\.)*)"\s*:', block, re.M))
    vi = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]", re.I)

    def section(begin, end):
        s = index.index(begin)
        return index[s:index.index(end, s)]

    html = section('<div id="doctor-tab"', '<div id="nf-recipe-drawer"') + section('<form id="nf-survey-form"', "</form>")
    missing = []

    class Walker(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name in ("placeholder", "aria-label", "label") and value and vi.search(value):
                    if " ".join(value.split()) not in static_map:
                        missing.append(value)

        def handle_data(self, data):
            text = " ".join(data.split())
            if text and vi.search(text) and text not in static_map and "Món Ngon Mỗi Ngày" not in text:
                missing.append(text)

    Walker(convert_charrefs=True).feed(html)
    assert not missing, f"Missing EN translations: {missing}"


def test_nutrition_scripts_rerender_on_language_change():
    catalog_src = (APP_JS.parent / "nutrition-catalog.js").read_text(encoding="utf-8")
    flow_src = (APP_JS.parent / "nutrition-flow.js").read_text(encoding="utf-8")
    assert "medimind:langchange" in catalog_src
    assert "_t('Xem công thức &amp; Dinh dưỡng', 'View recipe &amp; nutrition')" in catalog_src
    assert "_renderMealPlanView(savedPlan.mealPlanData" in flow_src
    assert "_t('Chỉ số năng lượng:', 'Energy metrics:')" in flow_src
