"""In-app notification bell: API, RBAC, deduplication, booking hooks and migration."""
from sqlalchemy import create_engine, inspect, text

from core.shared.migrations import run_migrations


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _med_payload(day="2026-11-26", slot="morning", time="08:00"):
    return {
        "type": "medication_reminder",
        "dedupe_key": f"med:{day}:{slot}:{time}",
        "data": {"slot": slot, "time": time, "meds": [{"name": "Paracetamol", "dose": "500mg"}]},
    }


def _book(client, **overrides):
    payload = {
        "facility_id": "fac_001",
        "facility_name": "Bệnh viện Nhân Dân 115",
        "specialty": "Nội tổng quát",
        "appointment_date": "2026-12-01",
        "appointment_time": "09:30",
        "patient_name": "Nguyễn Văn A",
        "patient_phone": "0911111111",
    }
    payload.update(overrides)
    return client.post("/api/appointments", json=payload)


def test_notifications_require_login(client):
    assert client.get("/api/notifications").status_code == 401
    assert client.post("/api/notifications", json=_med_payload()).status_code == 401
    assert client.post("/api/notifications/read", json={"all": True}).status_code == 401


def test_booking_and_cancel_create_bell_notifications(client, test_users):
    _login(client, test_users["user_a_id"])
    res = _book(client)
    assert res.status_code == 201, res.get_json()
    appt_id = res.get_json()["appointment"]["id"]

    data = client.get("/api/notifications").get_json()
    assert data["unread_count"] == 1
    first = data["notifications"][0]
    assert first["type"] == "appointment_created"
    assert first["link"] == "appointments"
    assert first["data"]["facility_name"] == "Bệnh viện Nhân Dân 115"
    assert first["data"]["appointment_time"] == "09:30"

    assert client.delete(f"/api/appointments/{appt_id}").status_code == 200
    data = client.get("/api/notifications").get_json()
    assert data["unread_count"] == 2
    assert data["notifications"][0]["type"] == "appointment_cancelled"


def test_medication_reminder_is_deduplicated_across_tabs(client, test_users):
    _login(client, test_users["user_a_id"])
    first = client.post("/api/notifications", json=_med_payload())
    second = client.post("/api/notifications", json=_med_payload())  # another tab / device
    assert first.status_code == 201 and first.get_json()["created"] is True
    assert second.status_code == 200 and second.get_json()["created"] is False
    assert first.get_json()["notification"]["id"] == second.get_json()["notification"]["id"]

    other_slot = client.post("/api/notifications", json=_med_payload(slot="evening", time="19:00"))
    assert other_slot.status_code == 201

    data = client.get("/api/notifications").get_json()
    assert data["unread_count"] == 2
    med = data["notifications"][-1]
    assert med["type"] == "medication_reminder"
    assert med["link"] == "medication"
    assert med["data"]["meds"] == [{"name": "Paracetamol", "dose": "500mg"}]


def test_client_cannot_forge_appointment_notifications_or_bad_keys(client, test_users):
    _login(client, test_users["user_a_id"])
    forged = dict(_med_payload(), type="appointment_created")
    assert client.post("/api/notifications", json=forged).status_code == 400
    bad_key = dict(_med_payload(), dedupe_key="appt_created:1")
    assert client.post("/api/notifications", json=bad_key).status_code == 400
    bad_time = _med_payload()
    bad_time["data"]["time"] = "<script>"
    assert client.post("/api/notifications", json=bad_time).status_code == 400


def test_users_cannot_see_or_mark_each_others_notifications(client, test_users):
    _login(client, test_users["user_a_id"])
    created = client.post("/api/notifications", json=_med_payload()).get_json()["notification"]

    _login(client, test_users["user_b_id"])
    data = client.get("/api/notifications").get_json()
    assert data["notifications"] == [] and data["unread_count"] == 0
    res = client.post("/api/notifications/read", json={"ids": [created["id"]]})
    assert res.get_json()["updated"] == 0

    _login(client, test_users["user_a_id"])
    assert client.get("/api/notifications").get_json()["unread_count"] == 1


def test_mark_single_and_all_as_read(client, test_users):
    _login(client, test_users["user_a_id"])
    a = client.post("/api/notifications", json=_med_payload(slot="morning", time="08:00")).get_json()["notification"]
    client.post("/api/notifications", json=_med_payload(slot="noon", time="12:00"))
    client.post("/api/notifications", json=_med_payload(slot="bedtime", time="22:00"))

    res = client.post("/api/notifications/read", json={"ids": [a["id"]]}).get_json()
    assert res["updated"] == 1 and res["unread_count"] == 2
    res = client.post("/api/notifications/read", json={"all": True}).get_json()
    assert res["updated"] == 2 and res["unread_count"] == 0
    assert client.post("/api/notifications/read", json={}).status_code == 400


def test_notifications_api_is_not_cached(client, test_users):
    _login(client, test_users["user_a_id"])
    res = client.get("/api/notifications")
    assert "no-store" in res.headers.get("Cache-Control", "")


def test_notification_migration_creates_table_with_dedupe_constraint():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email VARCHAR(120))"))
    run_migrations(engine)
    run_migrations(engine)  # idempotent
    inspector = inspect(engine)
    assert "user_notifications" in inspector.get_table_names()
    cols = {c["name"] for c in inspector.get_columns("user_notifications")}
    assert {"user_id", "type", "title", "message", "link", "data_json", "dedupe_key", "is_read", "created_at"} <= cols
    uniques = inspector.get_unique_constraints("user_notifications")
    assert any(set(u["column_names"]) == {"user_id", "dedupe_key"} for u in uniques)


def test_bell_renders_server_notifications_in_both_languages():
    """The bell must render real cards (escaped), unread badge, and switch VI/EN."""
    import subprocess
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = src.index("const NOTIF_POLL_MS")
    end = src.index("if (typeof document !== 'undefined') {\n  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initNotificationBell);")
    snippet = src[start:end]
    script = f"""
const assert = require('assert');
let currentLang = 'vi';
let currentUser = {{ id: 1 }};
const els = {{}};
const mk = id => (els[id] = {{ id, innerText: '', textContent: '', innerHTML: '', hidden: true,
  classList: {{ _s: new Set(['hidden']), toggle(c, on) {{ on ? this._s.add(c) : this._s.delete(c); }}, add(c) {{ this._s.add(c); }}, remove(c) {{ this._s.delete(c); }}, contains(c) {{ return this._s.has(c); }} }} }});
['notif-badge', 'notif-unread-count', 'notif-mark-read-btn', 'notif-items-list'].forEach(mk);
global.document = {{ getElementById: id => els[id] || null }};
function escapeHtml(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
function _slotDisplayName(id) {{ return currentLang === 'en' ? 'Morning' : 'Buổi sáng'; }}
function closeUserDropdown() {{}} function closeLanguageDropdown() {{}}
{snippet}
const items = [
  {{ id: 2, type: 'appointment_created', link: 'appointments', is_read: false, created_at: new Date().toISOString(),
     data: {{ facility_name: 'BV <b>115</b>', appointment_date: '2026-12-01', appointment_time: '09:30', specialty: 'Nội' }} }},
  {{ id: 1, type: 'medication_reminder', link: 'medication', is_read: true, created_at: new Date().toISOString(),
     data: {{ slot: 'morning', time: '08:00', meds: [{{ name: 'Paracetamol', dose: '500mg' }}] }} }},
];
renderNotifications(items);
const html = els['notif-items-list'].innerHTML;
assert.ok(html.includes('Đặt lịch thành công: BV &lt;b&gt;115&lt;/b&gt;'), html);
assert.ok(html.includes('09:30 ngày 01/12/2026'), html);
assert.ok(html.includes('Đến giờ uống thuốc — Buổi sáng (08:00)'), html);
assert.ok(!html.includes('<b>115</b>'), 'must escape facility names');
assert.strictEqual(els['notif-badge'].innerText, '1');
assert.ok(!els['notif-badge'].classList.contains('hidden'));
currentLang = 'en';
renderNotifications(items);
const htmlEn = els['notif-items-list'].innerHTML;
assert.ok(htmlEn.includes('Appointment booked: BV &lt;b&gt;115&lt;/b&gt;'), htmlEn);
assert.ok(htmlEn.includes('Time for Medication — Morning (08:00)'), htmlEn);
assert.strictEqual(els['notif-unread-count'].innerText, '1 new');
renderNotifications([]);
assert.ok(els['notif-badge'].classList.contains('hidden'));
assert.ok(els['notif-items-list'].innerHTML.includes('No new notifications'));
"""
    result = subprocess.run(["node"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr


def test_fastapi_gateway_serves_notifications_natively(test_users):
    """Production runs FastAPI (uvicorn): the bell API must work there with the same session cookie."""
    from fastapi.testclient import TestClient
    from tests.test_fastapi_migration import get_cookie_name, make_signed_auth_cookie
    from core.main_fastapi import app as fastapi_app

    api = TestClient(fastapi_app)
    api.headers.update({"Origin": "http://localhost:8000"})
    assert api.get("/api/notifications").status_code == 401

    user_id = 9101
    api.cookies.set(get_cookie_name(), make_signed_auth_cookie(user_id))
    created = api.post("/api/notifications", json=_med_payload(slot="noon", time="12:00"))
    assert created.status_code == 201, created.text
    again = api.post("/api/notifications", json=_med_payload(slot="noon", time="12:00"))
    assert again.status_code == 200 and again.json()["created"] is False

    listing = api.get("/api/notifications").json()
    assert listing["unread_count"] >= 1
    nid = created.json()["notification"]["id"]
    marked = api.post("/api/notifications/read", json={"ids": [nid]}).json()
    assert marked["updated"] == 1
    assert api.post("/api/notifications", json=dict(_med_payload(), type="appointment_created")).status_code == 400
