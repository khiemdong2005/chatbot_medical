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
    start = source.index("function handleSaveAllSettings() {")
    end = source.index("\n// ==========================================", start)
    snippet = source[start:end]
    script = f"""
const assert = require('assert');
let currentLang = 'vi';
let selectedLanguage = null;
const values = {{ 'set-language': 'en', 'set-timezone': 'UTC+7', 'set-date-format': 'DD/MM/YYYY', 'set-theme-select': 'light' }};
global.document = {{
  getElementById: id => values[id] ? {{ value: values[id] }} : null,
  body: {{ classList: {{ contains: () => true }} }}
}};
global.localStorage = {{ setItem: () => {{}} }};
function setLanguage(lang) {{ selectedLanguage = lang; currentLang = lang; }}
function toggleGlassThemeMode() {{}}
function showMedicalToast() {{}}
{snippet}
handleSaveAllSettings();
assert.strictEqual(selectedLanguage, 'en');
"""
    run_node(script)
