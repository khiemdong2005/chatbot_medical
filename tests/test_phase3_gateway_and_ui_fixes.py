"""
Phase 3 regression tests:
- FastAPI Gateway parity (/uploads, /metrics, google_maps_api_key, chat history window, IP rate limit, HTTP RED metrics)
- Legacy /api/prescription/confirm auth + ownership + doc_type preservation
- Frontend JS fixes (handlePrescriptionDrop, loadPrescriptionHistory isLab, restoreProfileDraftFromSession,
  extractApiErrorMessage error normalization, v3 OCR review routing)
"""

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app as flask_app
from core.main_fastapi import app as fastapi_app
from core.models import MedicalDocument, User, db
from core.observability import record_http_metrics
from core.rate_limit_service import rate_limit_service


APP_JS_PATH = Path("static/js/app.js")


def _make_signed_session(user_id: int) -> str:
    serializer = flask_app.session_interface.get_signing_serializer(flask_app)
    return serializer.dumps({"user_id": user_id})


def _run_node(script: str) -> str:
    setup = """
const storage = {};
global.window = global;
global.window.addEventListener = () => null;
global.window.removeEventListener = () => null;
global.localStorage = {
  getItem: (k) => (k in storage ? storage[k] : null),
  setItem: (k, v) => { storage[k] = String(v); },
  removeItem: (k) => { delete storage[k]; }
};
const sessStorage = {};
global.sessionStorage = {
  getItem: (k) => (k in sessStorage ? sessStorage[k] : null),
  setItem: (k, v) => { sessStorage[k] = String(v); },
  removeItem: (k) => { delete sessStorage[k]; }
};
const elements = {};
global.__setEl = (id, obj) => { elements[id] = obj; };
global.document = {
  getElementById: (id) => elements[id] || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => null,
  createElement: () => ({
    className: '',
    innerHTML: '',
    textContent: '',
    classList: { add: () => null, remove: () => null, toggle: () => null, contains: () => false },
    setAttribute: () => null,
    append: () => null,
    appendChild: () => null,
    replaceChildren: () => null
  })
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


def test_fastapi_gateway_mounts_metrics_and_uploads():
    client = TestClient(fastapi_app, headers={"origin": "http://localhost:8000"})

    # /uploads requires auth (401 from Flask handler via FastAPI gateway, not 404)
    upload_res = client.get("/uploads/does_not_exist.jpg")
    assert upload_res.status_code == 401

    # /metrics allowed for localhost and returns Prometheus format
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    assert "text/plain" in metrics_res.headers.get("content-type", "")
    assert "http_requests_total" in metrics_res.text

    # Index renders google_maps_api_key context variable matching Flask
    home_res = client.get("/")
    assert home_res.status_code == 200
    assert "window.MEDIMIND_GOOGLE_MAPS_KEY" in home_res.text


def test_fastapi_chat_history_window_and_ip_rate_limit():
    client = TestClient(fastapi_app, headers={"origin": "http://localhost:8000"})
    history_40 = [{"role": "user", "content": f"Tin nhắn {i}"} for i in range(40)]
    mock_result = {
        "reply": "Xin chào, hãy mô tả triệu chứng của bạn.",
        "is_emergency": False,
        "risk_score": 5,
        "urgency": "low",
        "risk_level": "Low",
        "specialist": "Nội tổng quát",
        "disclaimer": "Tham khảo bác sĩ.",
        "rag_status": {"ready": False},
        "intake_state": None,
    }
    with patch("core.main_fastapi.execute_chat_workflow", return_value=mock_result):
        res = client.post("/api/chat", json={"message": "Xin chào", "history": history_40})
        assert res.status_code == 200

    # History > 50 turns returns clean 400 (security bound preserved)
    over_res = client.post("/api/chat", json={"message": "Xin chào", "history": [{"role": "user", "content": "hi"}] * 55})
    assert over_res.status_code == 400

    # Invalid history turn must return clean 400 validation JSON (not crash on ValueError serialization)
    bad_res = client.post("/api/chat", json={"message": "Xin chào", "history": [{"role": "invalid", "content": "hi"}]})
    assert bad_res.status_code == 400
    assert bad_res.json().get("success") is False

    # Secondary IP rate limit in FastAPI matches Flask (60 req/min when TESTING disabled)
    rate_limit_service.clear_all()
    with patch.dict("os.environ", {"TESTING": "0"}):
        old_testing = flask_app.testing
        flask_app.testing = False
        try:
            with patch("core.rate_limit_service.rate_limit_service.check_chat_ip_rate_limit", return_value=False) as mock_ip:
                blocked = client.post("/api/chat", json={"message": "Xin chào"})
                assert blocked.status_code == 429
                assert mock_ip.called
        finally:
            flask_app.testing = old_testing
            rate_limit_service.clear_all()


def test_legacy_prescription_confirm_auth_ownership_and_doc_type():
    with flask_app.app_context():
        u1 = User(email="phase3_u1@example.com", full_name="User 1")
        u1.set_password("StrongPass123!")
        u2 = User(email="phase3_u2@example.com", full_name="User 2")
        u2.set_password("StrongPass123!")
        db.session.add_all([u1, u2])
        db.session.commit()
        u1_id, u2_id = u1.id, u2.id

        lab_doc = MedicalDocument(
            owner_id=u1_id,
            storage_filename="phase3_lab.jpg",
            original_filename="lab.jpg",
            file_path="uploads/phase3_lab.jpg",
            file_size=1234,
            file_type="image/jpeg",
            doc_type="ocr_draft",
            diagnosis="Theo dõi đường huyết",
            parsed_data=json.dumps({"doc_type": "lab_test", "labs": [{"test_name": "Glucose", "result": "6.0"}]}),
        )
        db.session.add(lab_doc)
        db.session.commit()
        doc_id = lab_doc.id

    try:
        client = flask_app.test_client()

        # Unauthenticated must return 401
        r_unauth = client.post("/api/prescription/confirm", json={"document_id": doc_id}, headers={"Origin": "http://localhost:8000"})
        assert r_unauth.status_code == 401

        # Other owner must return 404
        client.set_cookie(flask_app.config.get("SESSION_COOKIE_NAME", "session"), _make_signed_session(u2_id))
        r_other = client.post("/api/prescription/confirm", json={"document_id": doc_id}, headers={"Origin": "http://localhost:8000"})
        assert r_other.status_code == 404

        # Owner preserves lab_test doc_type instead of overwriting to prescription
        client.set_cookie(flask_app.config.get("SESSION_COOKIE_NAME", "session"), _make_signed_session(u1_id))
        r_ok = client.post(
            "/api/prescription/confirm",
            json={"document_id": doc_id, "labs": [{"test_name": "Glucose", "result": "6.0"}]},
            headers={"Origin": "http://localhost:8000"},
        )
        assert r_ok.status_code == 200

        with flask_app.app_context():
            refreshed = db.session.get(MedicalDocument, doc_id)
            assert refreshed.doc_type == "lab_test"
            assert "1 chỉ số xét nghiệm" in (refreshed.summary or "")
    finally:
        with flask_app.app_context():
            db.session.query(MedicalDocument).filter_by(id=doc_id).delete()
            db.session.query(User).filter(User.id.in_([u1_id, u2_id])).delete()
            db.session.commit()


def test_app_js_runtime_fixes():
    content = APP_JS_PATH.read_text(encoding="utf-8")

    # Ensure raw `data.error` / `data?.error` isn't left in alert/toast/Error messages
    raw_toast_err = re.findall(r"(?:showMedicalToast|new Error)\(\s*data\??\.error\b", content)
    assert not raw_toast_err, f"Found raw data.error interpolation: {raw_toast_err}"

    # Verify v3 review routing & blocked status handling exist
    assert "data.status === 'blocked'" in content
    assert "data.review_schema_version === 3" in content

    out = _run_node("""
const listEl = { innerHTML: '' };
const ehrList = { innerHTML: '' };
const countBadge = { innerText: '' };
const emptyEl = { classList: { add: () => null, remove: () => null } };
__setEl('prescription-history-list', listEl);
__setEl('ehr-prescription-list', ehrList);
__setEl('history-count-badge', countBadge);
__setEl('prescription-history-empty', emptyEl);

currentUser = { id: 42, isDemo: false };
const nameEl = { value: '' };
const addressEl = { value: '' };
__setEl('p-name', nameEl);
__setEl('p-address', addressEl);
__setEl('profile-form-img1', { _hasDraftListener: true });

// Foreign draft must be ignored
sessionStorage.setItem('medimind_profile_draft', JSON.stringify({ userId: '999', 'p-name': 'Wrong User' }));
restoreProfileDraftFromSession();
if (nameEl.value !== '') throw new Error('Restored draft for wrong user');

// Own draft must restore
sessionStorage.setItem('medimind_profile_draft', JSON.stringify({ userId: '42', 'p-name': 'Nguyen Van A', 'p-address': 'Ha Noi' }));
restoreProfileDraftFromSession();
if (nameEl.value !== 'Nguyen Van A' || addressEl.value !== 'Ha Noi') throw new Error('Own draft not restored');

// handlePrescriptionDrop rejects disallowed file extensions safely and accepts .jpg
let toastMsgs = [];
showMedicalToast = (msg) => { toastMsgs.push(msg); };
let forwardedFile = null;
handlePrescriptionFileSelected = (ev) => { forwardedFile = ev.target.files[0]; };
const dz = { classList: { remove: () => null } };
__setEl('prescription-dropzone', dz);

handlePrescriptionDrop({
  preventDefault: () => null,
  stopPropagation: () => null,
  dataTransfer: { files: [{ name: 'malware.exe', type: 'application/octet-stream' }] }
});
if (forwardedFile !== null || toastMsgs.length === 0) throw new Error('Invalid drop extension should warn');

handlePrescriptionDrop({
  preventDefault: () => null,
  stopPropagation: () => null,
  dataTransfer: { files: [{ name: 'donthuoc.jpg', type: 'image/jpeg' }] }
});
if (!forwardedFile || forwardedFile.name !== 'donthuoc.jpg') throw new Error('Valid drop file not forwarded');

// loadPrescriptionHistory executes cleanly without ReferenceError: isLab is not defined
global.fetch = async () => ({
  ok: true,
  json: async () => ({
    history: [
      { id: 1, doc_type: 'lab_test', diagnosis: 'Xét nghiệm máu', uploaded_at: '2026-11-18' },
      { id: 2, doc_type: 'prescription', diagnosis: 'Viêm họng', uploaded_at: '2026-11-18' }
    ]
  })
});
const res = await loadPrescriptionHistory();
if (!listEl.innerHTML.includes('Phiếu Xét Nghiệm') || !listEl.innerHTML.includes('Đơn Thuốc Lâm Sàng')) {
  throw new Error('Missing expected doc_type badges');
}
if (!ehrList.innerHTML.includes('XÉT NGHIỆM') || !ehrList.innerHTML.includes('ĐƠN THUỐC')) {
  throw new Error('Missing expected EHR badges');
}
console.log('NODE_PHASE3_OK');
""")
    assert "NODE_PHASE3_OK" in out
