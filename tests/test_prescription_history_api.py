"""Tests for PrescriptionHistory DB schema, /api/ocr/* endpoints, and OCR history UI flow."""

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

os.environ.setdefault("SECRET_KEY", "test-secret-key-32bytes-long-for-testing")
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")
os.environ.setdefault("DEV_SEED_USERS", "false")
os.environ.setdefault("FLASK_DEBUG", "0")

from app import create_app
from core.migrations import run_migrations
from core.models import MedicalDocument, PrescriptionHistory, User, db


class PrescriptionHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.tmpdir.name) / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "SECRET_KEY": "test-secret-key-for-unit-testing",
                "SESSION_COOKIE_SECURE": False,
                "UPLOAD_FOLDER": str(self.upload_dir),
            }
        )
        self.client = self.app.test_client()
        self.client.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.tmpdir.cleanup()

    def _create_user(self, email: str, full_name: str = "Nguyễn Văn A") -> int:
        with self.app.app_context():
            user = User(email=email, full_name=full_name, role="patient")
            user.set_password("MatKhau123@")
            db.session.add(user)
            db.session.commit()
            return user.id

    def _login_as(self, client, user_id: int) -> None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

    def test_prescription_history_table_and_migration_backfill(self):
        db_file = Path(self.tmpdir.name) / "legacy.db"
        engine = create_engine(f"sqlite:///{db_file}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email VARCHAR(120) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, full_name VARCHAR(120) NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'patient', account_status VARCHAR(20) NOT NULL DEFAULT 'active', google_sub VARCHAR(255), license_code VARCHAR(50), phone_number VARCHAR(20), dob VARCHAR(50), gender VARCHAR(20), address VARCHAR(255), bhyt VARCHAR(50), avatar_url VARCHAR(500), clinical_profile TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text("INSERT INTO users (id, email, password_hash, full_name) VALUES (1, 'a@test.local', 'h', 'User A')"))
            conn.execute(text("CREATE TABLE medical_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, storage_filename VARCHAR(255) UNIQUE NOT NULL, original_filename VARCHAR(255) NOT NULL, file_path VARCHAR(500) NOT NULL, file_size INTEGER NOT NULL, file_type VARCHAR(20) NOT NULL, mime_type VARCHAR(100), doc_type VARCHAR(50), diagnosis TEXT, facility VARCHAR(255), doctor VARCHAR(255), patient_name VARCHAR(255), summary TEXT, parsed_data TEXT, owner_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text("INSERT INTO medical_documents (id, storage_filename, original_filename, file_path, file_size, file_type, doc_type, diagnosis, facility, doctor, patient_name, summary, parsed_data, owner_id, created_at) VALUES (10, 'rx10.jpg', 'rx10.jpg', 'uploads/rx10.jpg', 1200, 'jpg', 'prescription', 'Viêm họng cấp', 'BV 175', 'BS. Minh', 'Bệnh nhân', '1 loại thuốc', :pdata, 1, '2026-11-20 08:30:00')"), {"pdata": json.dumps({"medications": [{"name": "Paracetamol 500mg"}], "diagnosis": "Viêm họng cấp"}, ensure_ascii=False)})
            conn.execute(text("INSERT INTO medical_documents (id, storage_filename, original_filename, file_path, file_size, file_type, doc_type, diagnosis, parsed_data, owner_id) VALUES (11, 'rx11.jpg', 'rx11.jpg', 'uploads/rx11.jpg', 900, 'jpg', 'ocr_draft', 'Draft only', '{\"medications\": []}', 1)"))

        run_migrations(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("prescription_history")}
        self.assertTrue({"id", "user_id", "image_url", "patient_name", "diagnosis", "created_at", "JSON_drugs"}.issubset(cols))

        with engine.connect() as conn:
            rows = conn.execute(text("SELECT document_id, user_id, image_url, patient_name, diagnosis, JSON_drugs FROM prescription_history")).fetchall()
        engine.dispose()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 10)
        self.assertEqual(rows[0][1], 1)
        self.assertEqual(rows[0][2], "/uploads/rx10.jpg")
        self.assertEqual(rows[0][3], "")
        self.assertEqual(rows[0][4], "Viêm họng cấp")
        self.assertIn("Paracetamol 500mg", rows[0][5])

    def test_save_and_get_history_endpoints_and_rbac_order(self):
        uid_a = self._create_user("user_a@test.medimind", "Nguyễn Văn A")
        uid_b = self._create_user("user_b@test.medimind", "Trần Thị B")

        # 1. Unauthenticated requests return 401
        res_unauth_save = self.client.post("/api/ocr/save_history", json={"diagnosis": "Test"})
        self.assertEqual(res_unauth_save.status_code, 401)
        res_unauth_get = self.client.get("/api/ocr/get_history")
        self.assertEqual(res_unauth_get.status_code, 401)

        # 2. Seed a linked ocr_draft MedicalDocument for User A
        with self.app.app_context():
            doc = MedicalDocument(
                storage_filename="rx_a1.jpg",
                original_filename="rx_a1.jpg",
                file_path=str(self.upload_dir / "rx_a1.jpg"),
                file_size=1024,
                file_type="jpg",
                mime_type="image/jpeg",
                doc_type="ocr_draft",
                owner_id=uid_a,
                created_at=datetime(2026, 11, 22, 9, 0, 0),
            )
            db.session.add(doc)
            db.session.commit()
            doc_id = doc.id

        self._login_as(self.client, uid_a)

        # Save edited OCR payload #1 (linked to MedicalDocument, redacted patient_name/gender + blob URL)
        payload_1 = {
            "document_id": doc_id,
            "patient_name": "",
            "gender": "",
            "facility": "BV Da liễu TP.HCM",
            "doctor": "BS. Trần Lan",
            "diagnosis": "Eczema phản ứng giai đoạn cấp",
            "image_url": "blob:http://127.0.0.1:8000/temp-local-blob",
            "medications": [
                {
                    "name": "Cetirizine 10mg",
                    "dose": "1 Viên / lần",
                    "frequency": "Ngày uống 2 lần (Sáng - Tối)",
                    "days": "14 Viên",
                    "usage": "Uống sau ăn",
                }
            ],
        }
        res_save_1 = self.client.post("/api/ocr/save_history", json=payload_1)
        self.assertEqual(res_save_1.status_code, 200)
        body_1 = res_save_1.get_json()
        self.assertEqual(body_1["status"], "success")
        hist_1_id = body_1["history_id"]
        self.assertEqual(body_1["record"]["image_url"], "/uploads/rx_a1.jpg")
        self.assertEqual(body_1["record"]["patient_name"], "")
        self.assertEqual(body_1["data"]["gender"], "")
        self.assertTrue(len(body_1["data"]["timeline"]["morning"]) == 1)
        self.assertTrue(len(body_1["data"]["timeline"]["evening"]) == 1)

        with self.app.app_context():
            refreshed_doc = db.session.get(MedicalDocument, doc_id)
            self.assertEqual(refreshed_doc.doc_type, "prescription")
            self.assertEqual(refreshed_doc.diagnosis, "Eczema phản ứng giai đoạn cấp")

        # Updating same document_id upserts instead of duplicating
        payload_1_edit = dict(payload_1, diagnosis="Eczema cấp (đã chỉnh sửa)")
        res_save_1b = self.client.post("/api/ocr/save_history", json=payload_1_edit)
        self.assertEqual(res_save_1b.status_code, 200)
        self.assertEqual(res_save_1b.get_json()["history_id"], hist_1_id)

        # Adjust timestamps so item 2 is newer cleanly
        with self.app.app_context():
            rec1 = db.session.get(PrescriptionHistory, hist_1_id)
            rec1.created_at = datetime(2026, 11, 22, 9, 0, 0)
            db.session.commit()

        # Save second prescription (without document_id)
        payload_2 = {
            "patient_name": "LÊ VĂN MINH",
            "gender": "Nam",
            "facility": "BV Quân y 175",
            "diagnosis": "Trào ngược dạ dày - thực quản",
            "medications": [
                {
                    "name": "YESOM 40 40mg (Esomeprazol 40mg)",
                    "dose": "1 Viên / lần",
                    "frequency": "Ngày uống 3 lần",
                    "days": "14 Viên",
                    "usage": "Trước ăn (TRƯỚC ĂN)",
                }
            ],
        }
        res_save_2 = self.client.post("/api/ocr/save_history", json=payload_2)
        self.assertEqual(res_save_2.status_code, 200)
        hist_2_id = res_save_2.get_json()["history_id"]

        with self.app.app_context():
            rec2 = db.session.get(PrescriptionHistory, hist_2_id)
            rec2.created_at = datetime(2026, 11, 23, 16, 0, 0)
            db.session.commit()

        # Retrieve sorted newest-first
        res_get_a = self.client.get("/api/ocr/get_history")
        self.assertEqual(res_get_a.status_code, 200)
        list_data = res_get_a.get_json()
        self.assertEqual(list_data["total"], 2)
        self.assertEqual([item["id"] for item in list_data["history"]], [hist_2_id, hist_1_id])
        self.assertEqual(list_data["history"][0]["diagnosis"], "Trào ngược dạ dày - thực quản")
        self.assertEqual(list_data["history"][0]["JSON_drugs"]["patient_name"], "LÊ VĂN MINH")
        self.assertEqual(list_data["history"][1]["diagnosis"], "Eczema cấp (đã chỉnh sửa)")

        # Fetch single detail
        res_detail = self.client.get(f"/api/ocr/get_history/{hist_1_id}")
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.get_json()["data"]["diagnosis"], "Eczema cấp (đã chỉnh sửa)")

        # RBAC check with User B
        client_b = self.app.test_client()
        client_b.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"
        self._login_as(client_b, uid_b)
        res_get_b = client_b.get("/api/ocr/get_history")
        self.assertEqual(res_get_b.status_code, 200)
        self.assertEqual(res_get_b.get_json()["total"], 0)
        self.assertEqual(client_b.get(f"/api/ocr/get_history/{hist_1_id}").status_code, 404)
        self.assertEqual(client_b.delete(f"/api/ocr/history/{hist_1_id}").status_code, 404)

        # User A deletes record #2 cleanly
        res_del = self.client.delete(f"/api/ocr/history/{hist_2_id}")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(self.client.get("/api/ocr/get_history").get_json()["total"], 1)

    def test_frontend_history_load_save_listener_and_card_reopen(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not available")

        app_js = (Path(__file__).resolve().parent.parent / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        hist_start = app_js.index("let cachedPrescriptionHistory = [];")
        hist_end = app_js.index("// Helper to determine the smart active slot")
        verify_start = app_js.index("function sanitizePrescriptionAdminField")
        verify_end = app_js.index("function reviewPrescriptionVerification()")

        script = textwrap.dedent(
            f"""
            const assert = require('assert');
            const elements = {{}};
            function makeEl(id) {{
              if (!elements[id]) {{
                elements[id] = {{
                  id,
                  value: '',
                  innerHTML: '',
                  innerText: '',
                  disabled: false,
                  dataset: {{}},
                  listeners: {{}},
                  addEventListener(evt, fn) {{ this.listeners[evt] = fn; }},
                  async click() {{ if (this.listeners.click) return await this.listeners.click(); }},
                  classList: {{ add() {{}}, remove() {{}} }},
                  scrollIntoView() {{}},
                }};
              }}
              return elements[id];
            }}
            global.document = {{ getElementById: (id) => makeEl(id) }};
            global.confirm = () => true;
            let currentUser = {{ id: 1, name: 'Vũ Lê', isDemo: false }};
            let currentLang = 'vi';
            let currentUploadedFileUrl = '';
            let currentPrescriptionData = null;
            let lastPrescriptionDataSnapshot = null;
            let currentOcrSubView = 'upload';
            const callLog = [];
            let renderedStep2 = null;
            let navigatedTo = null;

            const savedDb = [];

            function escapeHtml(str) {{
              return String(str ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
            }}
            function syncSubViewHistory() {{}}
            function showPrescriptionLoading() {{}}
            function showMedicalToast() {{}}
            function navigateTo(tab, sub, push) {{
              navigatedTo = {{ tab, sub, push }};
            }}
            function renderPrescriptionResult(data, opts) {{
              callLog.push('renderPrescriptionResult');
              renderedStep2 = {{ data, opts }};
            }}

            global.fetch = async (url, opts = {{}}) => {{
              if (url === '/api/ocr/save_history' && opts.method === 'POST') {{
                callLog.push('save_history');
                const body = JSON.parse(opts.body);
                const saved = {{
                  id: 101,
                  history_id: 101,
                  document_id: body.document_id || 25,
                  user_id: 1,
                  image_url: body.image_url || '/uploads/rx25.jpg',
                  preview_image_url: body.image_url || '/uploads/rx25.jpg',
                  patient_name: body.patient_name || '',
                  diagnosis: body.diagnosis || '',
                  facility: body.facility || 'Cơ sở Y tế',
                  doctor: body.doctor || '',
                  summary: '1 loại thuốc: Cetirizine 10mg',
                  doc_type: 'prescription',
                  created_at: '16:15 23/11/2026',
                  JSON_drugs: {{ ...body, history_id: 101 }},
                }};
                savedDb.unshift(saved);
                return {{
                  ok: true,
                  status: 200,
                  json: async () => ({{
                    status: 'success',
                    history_id: 101,
                    document_id: saved.document_id,
                    record: saved,
                    data: saved.JSON_drugs,
                  }}),
                }};
              }}
              if (url === '/api/ocr/get_history') {{
                callLog.push('get_history');
                return {{
                  ok: true,
                  status: 200,
                  json: async () => ({{ status: 'success', history: savedDb, total: savedDb.length }}),
                }};
              }}
              throw new Error('Unexpected fetch URL: ' + url);
            }};

            {app_js[hist_start:hist_end]}
            {app_js[verify_start:verify_end]}

            (async () => {{
              // 1. Render Step 1 verification with redacted fields + user edits
              renderPrescriptionVerification({{
                document_id: 25,
                patient_name: null,
                gender: null,
                facility: 'BV Da Liễu',
                diagnosis: 'Eczema',
                preview_image_url: '/uploads/rx25.jpg',
                medications: [{{ name: 'Cetirizine 10mg', dose: '1 Viên', frequency: '2 lần/ngày' }}],
              }}, {{ pushHistory: false }});

              const confirmBtn = makeEl('btn-confirm-and-proceed');
              assert.strictEqual(typeof confirmBtn.listeners.click, 'function', 'Confirm button must register click listener');

              makeEl('verify-patient-name').value = 'NGUYỄN VĂN C';
              makeEl('verify-patient-dob').value = '1990';
              makeEl('verify-patient-gender').value = 'Nam';
              makeEl('verify-diagnosis').value = 'Eczema đã chỉnh sửa';
              makeEl('verify-facility').value = 'BV Da Liễu';
              makeEl('verify-doctor').value = 'BS. Mai';

              // 2. Click Confirm -> must await save_history BEFORE renderPrescriptionResult, then load history
              await confirmBtn.click();
              assert.deepStrictEqual(callLog, ['save_history', 'renderPrescriptionResult', 'get_history']);
              assert.strictEqual(renderedStep2.data.history_id, 101);
              assert.strictEqual(renderedStep2.data.diagnosis, 'Eczema đã chỉnh sửa');
              assert.strictEqual(renderedStep2.data.patient_name, 'NGUYỄN VĂN C');

              // 3. History list & count badge updated without ReferenceError
              assert.strictEqual(makeEl('history-count-badge').innerText, '1 hồ sơ');
              const histHtml = makeEl('prescription-history-list').innerHTML;
              assert(histHtml.includes('Eczema đã chỉnh sửa'));
              assert(histHtml.includes('onclick="viewPrescriptionHistoryItem(101)"'));

              // 4. Click card to reopen historical prescription JSON
              await viewPrescriptionHistoryItem(101);
              assert.deepStrictEqual(navigatedTo, {{ tab: 'ocr-tab', sub: 'result', push: true }});
              assert.strictEqual(currentPrescriptionData.history_id, 101);
              assert.strictEqual(currentPrescriptionData.diagnosis, 'Eczema đã chỉnh sửa');
            }})().catch(err => {{
              console.error(err);
              process.exit(1);
            }});
            """
        )
        temp_js = Path(self.tmpdir.name) / "test_history_ui.js"
        temp_js.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(temp_js)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=f"Node VM check failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
