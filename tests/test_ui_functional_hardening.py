"""
================================================================================
🩺 MEDIMIND CLINICAL AI - UI FUNCTIONAL HARDENING REGRESSION TEST SUITE (PHASE 4.1B)
================================================================================
Kiểm thử tự động cho toàn bộ các hạng mục Functional Hardening & Consistency P1:
  1. No duplicate function declarations in static/js/app.js
  2. Removal of confirmed dead nutrition code
  3. Specialist guidance rendering in chat turns
  4. History risk badge class mapping (Emergency vs High non-emergency vs Medium vs Low vs Slate)
  5. Multilingual safety and triage strings (VI vs EN)
  6. API error detail normalization (extractApiErrorMessage without [object Object])
  7. Safe null guards in modal and summary rendering
  8. Prevention of false-success in appointment booking
  9. Emergency direct-call CTA (tel:115)
  10. Degraded state consistency in triage panel
================================================================================
"""

import json
import re
import subprocess
from pathlib import Path
import pytest


APP_JS_PATH = Path("static/js/app.js")
NUTRITION_FLOW_PATH = Path("static/js/nutrition-flow.js")


@pytest.fixture(scope="module")
def app_js_content():
    assert APP_JS_PATH.exists(), "File static/js/app.js phải tồn tại"
    return APP_JS_PATH.read_text(encoding="utf-8")


def run_node_eval(test_script: str) -> str:
    """Helper chạy mã JavaScript qua Node.js stdin với mock browser environment."""
    setup = """
const crypto = require('crypto');
global.window = global;
global.window.addEventListener = () => null;
global.window.removeEventListener = () => null;
global.crypto = crypto;
global.localStorage = { getItem: () => null, setItem: () => null, removeItem: () => null };
global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => null,
  createElement: (tag) => ({
    set innerText(v) { this._text = v; },
    get innerText() { return this._text || ''; },
    set textContent(v) { this._text = v; },
    get textContent() { return this._text || ''; },
    get innerHTML() {
      return (this._text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },
    classList: { add: () => null, remove: () => null, toggle: () => null, contains: () => false },
    appendChild: () => null
  })
};
global.navigator = { clipboard: null };
global.location = { search: '', pathname: '', hash: '' };
"""
    full_script = f"{setup}\n{APP_JS_PATH.read_text(encoding='utf-8')}\n{test_script}\nprocess.exit(0);"
    result = subprocess.run(
        ["node"],
        input=full_script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"Node execution failed (code {result.returncode}):\n{result.stderr}")
    return result.stdout.strip()


# ==============================================================================
# 1. TEST DUPLICATE FUNCTION DECLARATIONS
# ==============================================================================

def test_no_duplicate_functions_in_app_js(app_js_content):
    """Bảo đảm không có hàm nào được khai báo nhiều lần trong app.js."""
    pattern = re.compile(r'^\s*(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(', re.M)
    funcs = {}
    for match in pattern.finditer(app_js_content):
        name = match.group(1)
        line = app_js_content[:match.start()].count('\n') + 1
        funcs.setdefault(name, []).append(line)

    duplicates = {name: lines for name, lines in funcs.items() if len(lines) > 1}
    assert not duplicates, f"Phát hiện các hàm bị trùng lặp trong app.js: {duplicates}"

    # Kiểm tra cụ thể 4 hàm từng bị duplicate
    for fn in ["expandFloatingChatToFull", "sendFloatingChatMessage", "sendQuickFloatingPrompt", "toggleFloatingChat"]:
        assert fn in funcs, f"Hàm canonical {fn} phải tồn tại"
        assert len(funcs[fn]) == 1, f"Hàm {fn} chỉ được khai báo đúng 1 lần duy nhất, hiện tại có: {funcs[fn]}"


# ==============================================================================
# 2. TEST DEAD NUTRITION CODE REMOVED
# ==============================================================================

def test_dead_nutrition_code_removed(app_js_content):
    """Xác nhận toàn bộ dead code của Nutrition Studio cũ đã được gỡ bỏ khỏi app.js."""
    dead_symbols = [
        "NUTRITION_PRESETS",
        "selectNutritionPreset",
        "searchCustomCondition",
        "clearNutritionSearch",
        "loadNutritionCondition",
        "renderDishPlate",
        "showFoodDetailFromButton",
        "renderRecipe",
        "adjustServings",
        "setServings",
        "showFoodDetail",
        "copyRecipeToClipboard",
        "setNutritionType"
    ]
    for sym in dead_symbols:
        assert sym not in app_js_content, f"Dead nutrition symbol '{sym}' vẫn còn tồn tại trong static/js/app.js!"

    # Xác nhận nutrition-flow.js tồn tại và là modern single source of truth
    assert NUTRITION_FLOW_PATH.exists(), "File static/js/nutrition-flow.js phải tồn tại"
    flow_content = NUTRITION_FLOW_PATH.read_text(encoding="utf-8")
    assert len(flow_content) > 500, "nutrition-flow.js phải có nội dung hợp lệ"
    assert "window.initNutritionStudio" in flow_content, "nutrition-flow.js phải định nghĩa window.initNutritionStudio"


# ==============================================================================
# 3. TEST SPECIALIST GUIDANCE RENDERING
# ==============================================================================

def test_specialist_guidance_rendering():
    """Kiểm tra hàm renderSpecialistGuidance: hiển thị badge khi có chuyên khoa, ẩn hoàn toàn khi rỗng/null."""
    js_test = """
    const testCases = [
      { input: "Tai Mũi Họng", isEn: false, expectContains: "Tai Mũi Họng", expectLabel: "Chuyên khoa khuyến nghị:" },
      { input: "Cardiology", isEn: true, expectContains: "Cardiology", expectLabel: "Recommended Specialist:" },
      { input: null, isEn: false, expectEmpty: true },
      { input: "", isEn: false, expectEmpty: true },
      { input: "   ", isEn: true, expectEmpty: true },
      { input: undefined, isEn: false, expectEmpty: true }
    ];

    for (const tc of testCases) {
      const html = renderSpecialistGuidance(tc.input, tc.isEn);
      if (tc.expectEmpty) {
        if (html !== '') throw new Error('Expected empty string for input: ' + tc.input);
      } else {
        if (!html.includes(tc.expectContains)) throw new Error('Missing specialist in HTML: ' + tc.expectContains);
        if (!html.includes(tc.expectLabel)) throw new Error('Missing label in HTML: ' + tc.expectLabel);
      }
    }
    console.log('SUCCESS');
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"


# ==============================================================================
# 4. TEST HISTORY RISK BADGE CLASS MAPPING
# ==============================================================================

def test_history_risk_badge_class_mapping():
    """Kiểm tra hàm getRiskBadgeClass: Emergency -> rose, High non-emergency -> amber, Medium -> amber, Low -> emerald, Unknown -> slate."""
    js_test = """
    const emergency = getRiskBadgeClass({ isEmergency: true, riskScore: 85, riskLevel: 'Nguy cơ cao' });
    if (!emergency.includes('text-rose-300') || !emergency.includes('bg-rose-500/20')) {
      throw new Error('Emergency must map to rose badge, got: ' + emergency);
    }

    const highNonEmergency = getRiskBadgeClass({ isEmergency: false, riskScore: 75, riskLevel: 'Nguy cơ cao' });
    if (!highNonEmergency.includes('text-amber-300') || highNonEmergency.includes('rose')) {
      throw new Error('High non-emergency must map to amber badge without rose, got: ' + highNonEmergency);
    }

    const medium = getRiskBadgeClass({ isEmergency: false, riskScore: 40, riskLevel: 'Trung bình' });
    if (!medium.includes('text-amber-300')) {
      throw new Error('Medium risk must map to amber badge, got: ' + medium);
    }

    const low = getRiskBadgeClass({ isEmergency: false, riskScore: 10, riskLevel: 'Theo dõi' });
    if (!low.includes('text-emerald-300')) {
      throw new Error('Low risk must map to emerald badge, got: ' + low);
    }

    const unknown = getRiskBadgeClass({ isEmergency: false, riskScore: null, riskLevel: 'Chưa đủ thông tin' });
    if (!unknown.includes('text-slate-600') && !unknown.includes('dark:text-slate-300')) {
      throw new Error('Unknown/null risk must map to slate badge, got: ' + unknown);
    }

    console.log('SUCCESS');
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"


# ==============================================================================
# 5. TEST MULTILINGUAL SAFETY & TRIAGE STRINGS
# ==============================================================================

def test_multilingual_safety_and_triage_strings():
    """Kiểm tra dictionary translations có đầy đủ key an toàn lâm sàng bằng tiếng Việt và tiếng Anh."""
    js_test = """
    const requiredKeys = [
      'safety_emergency_title',
      'safety_emergency_cta',
      'safety_high_risk_title',
      'safety_medium_risk_title',
      'safety_low_risk_title',
      'safety_insufficient_info',
      'safety_specialist_rec',
      'safety_sources',
      'safety_degraded_notice',
      'safety_degraded_triage'
    ];

    for (const key of requiredKeys) {
      if (!translations.vi[key]) throw new Error('Missing translations.vi.' + key);
      if (!translations.en[key]) throw new Error('Missing translations.en.' + key);
    }

    if (translations.vi.safety_emergency_cta !== 'Gọi 115') throw new Error('translations.vi.safety_emergency_cta mismatch');
    if (translations.en.safety_emergency_cta !== 'Call 115') throw new Error('translations.en.safety_emergency_cta mismatch');

    console.log('SUCCESS');
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"


# ==============================================================================
# 6. TEST API ERROR NORMALIZATION (extractApiErrorMessage)
# ==============================================================================

def test_api_error_normalization():
    """Kiểm tra hàm extractApiErrorMessage chuẩn hóa các định dạng lỗi từ backend / FastAPI mà không bao giờ sinh [object Object]."""
    js_test = """
    // 1. FastAPI validation errors array
    const fastApiErr = {
      detail: [
        { loc: ['body', 'message'], msg: 'Field required' },
        { loc: ['body', 'conversation_id'], msg: 'Invalid UUID format' }
      ]
    };
    const msg1 = extractApiErrorMessage(fastApiErr, 'Fallback');
    if (msg1.includes('[object Object]')) throw new Error('Found [object Object] in msg1: ' + msg1);
    if (!msg1.includes('message: Field required')) throw new Error('Missing message detail in msg1: ' + msg1);

    // 2. Detail object
    const dictDetail = { detail: { message: 'Invalid token' } };
    const msg2 = extractApiErrorMessage(dictDetail, 'Fallback');
    if (msg2 !== 'Invalid token') throw new Error('Expected Invalid token, got: ' + msg2);

    // 3. String detail
    const strDetail = { detail: 'Conversation closed' };
    const msg3 = extractApiErrorMessage(strDetail, 'Fallback');
    if (msg3 !== 'Conversation closed') throw new Error('Expected Conversation closed, got: ' + msg3);

    // 4. Custom error string
    const customErr = { error: 'Rate limit 429' };
    const msg4 = extractApiErrorMessage(customErr, 'Fallback');
    if (msg4 !== 'Rate limit 429') throw new Error('Expected Rate limit 429, got: ' + msg4);

    // 5. Fallback on empty/null
    const msg5 = extractApiErrorMessage(null, 'Custom Fallback');
    if (msg5 !== 'Custom Fallback') throw new Error('Expected Custom Fallback, got: ' + msg5);

    console.log('SUCCESS');
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"


# ==============================================================================
# 7. TEST SAFE NULL GUARDS IN MODAL & SUMMARY
# ==============================================================================

def test_safe_null_guards_previsit_summary_modal():
    """Kiểm tra renderPreVisitSummaryInModal và updateSummarySaveButton an toàn khi các DOM element không tồn tại."""
    js_test = """
    global.currentConversationId = 'test_conv';

    try {
      renderPreVisitSummaryInModal({
        part_a_patient_facts: { chief_complaint: 'Đau đầu' },
        part_b_system_assessment: { triage_status: 'Theo dõi' },
        ready_to_finalize: true,
        is_confirmed: false
      }, 'test_conv');

      updateSummarySaveButton();
      console.log('SUCCESS');
    } catch (err) {
      console.error(err);
      process.exit(1);
    }
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"


# ==============================================================================
# 8. TEST APPOINTMENT BOOKING FALSE-SUCCESS PREVENTION
# ==============================================================================

def test_appointment_booking_error_handling(app_js_content):
    """Xác nhận handleFacilityBookingSubmit kiểm tra res.ok, sử dụng extractApiErrorMessage và không báo false-success trong catch."""
    fn_match = re.search(r"async function handleFacilityBookingSubmit\(e\)\s*\{([\s\S]*?)\n\}", app_js_content)
    assert fn_match, "Hàm handleFacilityBookingSubmit phải tồn tại"
    body = fn_match.group(1)

    # Phải kiểm tra !res.ok
    assert "!res.ok" in body or "res.ok === false" in body, "handleFacilityBookingSubmit phải kiểm tra !res.ok"

    # Phải gọi extractApiErrorMessage khi gặp lỗi
    assert "extractApiErrorMessage" in body, "handleFacilityBookingSubmit phải gọi extractApiErrorMessage khi lỗi"

    # Trong khối catch KHÔNG được báo thành công ("Đã lưu lịch nhắc")
    catch_block = body[body.rfind("catch"):]
    assert "Đã lưu lịch nhắc" not in catch_block, "Khối catch trong handleFacilityBookingSubmit tuyệt đối KHÔNG được báo thành công!"
    assert "Saved appointment reminder" not in catch_block, "Khối catch trong handleFacilityBookingSubmit không được báo false-success tiếng Anh!"
    assert "showMedicalToast" in catch_block and "error" in catch_block, "Khối catch phải hiển thị toast thông báo lỗi!"


# ==============================================================================
# 9. TEST EMERGENCY DIRECT-CALL CTA
# ==============================================================================

def test_emergency_direct_call_cta():
    """Kiểm tra renderEmergencyBanner tạo CTA <a href="tel:115"> khi isEmergency=true, ẩn hoàn toàn khi false."""
    js_test = """
    // 1. Emergency VI
    const viBanner = renderEmergencyBanner(true, false, false);
    if (!viBanner.includes('href="tel:115"')) throw new Error('Missing tel:115 link in VI banner: ' + viBanner);
    if (!viBanner.includes('Gọi 115')) throw new Error('Missing CTA text in VI banner: ' + viBanner);

    // 2. Emergency EN
    const enBanner = renderEmergencyBanner(true, true, false);
    if (!enBanner.includes('href="tel:115"')) throw new Error('Missing tel:115 link in EN banner: ' + enBanner);
    if (!enBanner.includes('Call 115')) throw new Error('Missing CTA text in EN banner: ' + enBanner);

    // 3. Compact banner
    const compactBanner = renderEmergencyBanner(true, false, true);
    if (!compactBanner.includes('href="tel:115"')) throw new Error('Missing tel:115 link in compact banner');

    // 4. Non-emergency
    const nonEmergency = renderEmergencyBanner(false, false, false);
    if (nonEmergency !== '') throw new Error('Non-emergency banner must be empty, got: ' + nonEmergency);

    console.log('SUCCESS');
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"


# ==============================================================================
# 10. TEST DEGRADED STATE TRIAGE CONSISTENCY
# ==============================================================================

def test_degraded_state_triage_consistency():
    """Kiểm tra updateTriagePanel hiển thị đúng thông tin chế độ dự phòng khi degraded=true và không gán nhãn 'Chưa đủ thông tin' / 'Khỏe mạnh'."""
    js_test = """
    let elementText = '';
    let elementClass = '';
    const origGetElementById = global.document.getElementById;
    global.document.getElementById = function(id) {
      if (id === 'floating-risk-score') {
        return {
          set innerText(val) { elementText = val; },
          get innerText() { return elementText; },
          set className(val) { elementClass = val; },
          get className() { return elementClass; }
        };
      }
      return origGetElementById(id);
    };

    // 1. Degraded non-emergency in VI
    currentLang = 'vi';
    updateTriagePanel({ degraded: true, is_emergency: false, risk_score: null, risk_level: null });
    if (elementText.includes('Chưa đủ thông tin') || elementText.includes('Khỏe mạnh')) {
      throw new Error('Degraded mode must not claim normal status, got: ' + elementText);
    }
    if (!elementText.includes('dự phòng') && !elementText.includes('Theo dõi')) {
      throw new Error('Degraded mode text must indicate backup/follow up, got: ' + elementText);
    }

    // 2. Degraded non-emergency in EN
    currentLang = 'en';
    updateTriagePanel({ degraded: true, is_emergency: false, risk_score: null, risk_level: null });
    if (!elementText.includes('Backup Mode')) {
      throw new Error('Degraded EN mode must indicate Backup Mode, got: ' + elementText);
    }

    // 3. Degraded emergency in VI (Emergency takes precedence)
    currentLang = 'vi';
    updateTriagePanel({ degraded: true, is_emergency: true, risk_score: null, risk_level: null });
    if (!elementText.includes('Cảnh báo cấp cứu khẩn cấp')) {
      throw new Error('Emergency must always take precedence over degraded mode, got: ' + elementText);
    }

    console.log('SUCCESS');
    """
    out = run_node_eval(js_test)
    assert out == "SUCCESS"
