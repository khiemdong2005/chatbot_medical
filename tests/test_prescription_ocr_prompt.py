"""Tests for handwritten-note priority in prescription OCR prompts and Vision payloads."""

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.gemini_schema_service import (
    _normalize_vietnamese_units,
    _sanitize_redacted_admin_field,
    extract_with_gemini_schema,
)
from core.llm_provider import LLMProvider, llm_provider
from core.pipeline_orchestrator import finalize_reviewed_document
from core.prescription_service import (
    normalize_and_analyze_with_gemini,
    scan_prescription_with_gemini_vision,
)
from core.prompts import (
    PRESCRIPTION_OCR_FEW_SHOT_RULES,
    PRESCRIPTION_OCR_HANDWRITTEN_RULE,
    PRESCRIPTION_OCR_REDACTED_RULE,
    PRESCRIPTION_OCR_SYSTEM_PROMPT,
)
from core.reconciliation_service import _parse_dosing_details, reconcile_parallel_results


class PrescriptionOcrPromptTests(unittest.TestCase):
    def _create_image(self, tmpdir: str, name: str = "rx.jpg") -> str:
        path = Path(tmpdir) / name
        Image.new("RGB", (400, 600), "white").save(path)
        return str(path)

    def test_extract_with_gemini_schema_passes_handwritten_rule_single_and_dual_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            full_path = self._create_image(tmpdir, "full.jpg")
            crop_path = self._create_image(tmpdir, "crop.jpg")

            with (
                patch.object(llm_provider, "resolve_api_key", return_value="test-key-123456"),
                patch.object(llm_provider, "is_configured", return_value=True),
                patch.object(llm_provider, "generate_json", return_value={"medications": []}) as generate,
            ):
                extract_with_gemini_schema(full_path, crop_image_path=crop_path)
                dual_kwargs = generate.call_args.kwargs
                self.assertEqual(len(dual_kwargs["contents"]), 3)
                self.assertEqual(dual_kwargs["system_instruction"], PRESCRIPTION_OCR_SYSTEM_PROMPT)
                self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, dual_kwargs["system_instruction"])
                self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, dual_kwargs["contents"][2])
                self.assertIn("BẠN ĐANG NHẬN ĐƯỢC 2 ẢNH CỦA CÙNG MỘT ĐƠN THUỐC", dual_kwargs["contents"][2])

                extract_with_gemini_schema(full_path, crop_image_path=None)
                single_kwargs = generate.call_args.kwargs
                self.assertEqual(len(single_kwargs["contents"]), 2)
                self.assertEqual(single_kwargs["system_instruction"], PRESCRIPTION_OCR_SYSTEM_PROMPT)
                self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, single_kwargs["contents"][1])
                self.assertIn("BẠN ĐANG NHẬN ĐƯỢC 1 ẢNH TOÀN BỘ TRANG ĐƠN THUỐC", single_kwargs["contents"][1])

    def test_prescription_service_prompts_include_handwritten_rule_and_clean_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rx_path = self._create_image(tmpdir)
            ocr_data = {"raw_text": "1. Paracetamol 500mg", "total_lines": 1, "avg_confidence": 0.9}

            with patch.object(llm_provider, "generate_json", return_value={"medications": []}) as generate:
                normalize_and_analyze_with_gemini(ocr_data, original_filename="rx.jpg", file_path=rx_path)
                hybrid_kwargs = generate.call_args.kwargs
                self.assertEqual(hybrid_kwargs["system_instruction"], PRESCRIPTION_OCR_SYSTEM_PROMPT)
                self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, hybrid_kwargs["contents"][-1])
                self.assertNotIn("{PRESCRIPTION_OCR_HANDWRITTEN_RULE}", hybrid_kwargs["contents"][-1])

                scan_prescription_with_gemini_vision(rx_path, original_filename="rx.jpg")
                fallback_kwargs = generate.call_args.kwargs
                self.assertEqual(fallback_kwargs["system_instruction"], PRESCRIPTION_OCR_SYSTEM_PROMPT)
                self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, fallback_kwargs["contents"][-1])
                self.assertIn('{"status": "success", "type": "prescription", ...}', fallback_kwargs["contents"][-1])
                self.assertNotIn("{PRESCRIPTION_OCR_HANDWRITTEN_RULE}", fallback_kwargs["contents"][-1])

    def test_end_to_end_vision_payload_serializes_system_and_image_parts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rx_path = self._create_image(tmpdir)
            lp = LLMProvider()
            client = lp.get_client("gsk_test_vision_key_123456", provider="groq", profile="ocr")
            captured_payloads = []

            def fake_post(payload):
                captured_payloads.append(payload)
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "doc_type": "prescription",
                                        "medications": [
                                            {
                                                "stt": 1,
                                                "brand_name_as_printed": "Nexium 40mg",
                                                "ingredients_as_printed": "Esomeprazole",
                                                "quantity_as_printed": "14 viên",
                                                "schedule_as_printed": "Sáng 1 viên",
                                                "usage_as_printed": "Uống trước ăn 30 phút (chữ viết tay)",
                                                "uncertain_fields": [],
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }

            with (
                patch.dict(os.environ, {"AI_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_vision_key_123456"}, clear=False),
                patch.object(lp, "get_client", return_value=client),
                patch.object(client.models, "_post_completion", side_effect=fake_post),
                patch("core.gemini_schema_service.llm_provider", lp, create=True),
                patch("core.llm_provider.llm_provider", lp),
            ):
                res = extract_with_gemini_schema(rx_path, doc_type="prescription")

            self.assertIsNotNone(res)
            self.assertEqual(len(captured_payloads), 1)
            payload = captured_payloads[0]
            messages = payload["messages"]
            self.assertEqual(messages[0]["role"], "system")
            self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, messages[0]["content"])
            self.assertIn(PRESCRIPTION_OCR_FEW_SHOT_RULES, messages[0]["content"])
            self.assertIn("YESOM 40 40mg (Esomeprazol 40mg)", messages[0]["content"])
            self.assertIn("Ngày uống 3 lần, mỗi lần 1 Viên (TRƯỚC ĂN)", messages[0]["content"])
            self.assertIn(
                "Chuẩn hóa bắt buộc chữ có dấu cho Đơn vị tính: Viên, Gói, Ống, Chai, Tuýp... Tuyệt đối không để không dấu (như ONG, GOI).",
                messages[0]["content"],
            )
            self.assertIn(
                "Các ghi chú uống thuốc (Trước ăn, Sau ăn) nếu trích xuất được từ chữ viết tay, phải nối IN HOA vào ngoặc đơn ở cuối chuỗi Liều dùng. Ví dụ: '...mỗi lần 1 Viên (TRƯỚC ĂN)'.",
                messages[0]["content"],
            )
            self.assertIn("1/3 Chai / lần", messages[0]["content"])
            self.assertIn("valid raw JSON object", messages[0]["content"])

            self.assertEqual(messages[1]["role"], "user")
            user_content = messages[1]["content"]
            self.assertIsInstance(user_content, list)
            self.assertEqual(user_content[0]["type"], "image_url")
            self.assertTrue(user_content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
            self.assertEqual(user_content[1]["type"], "text")
            self.assertIn(PRESCRIPTION_OCR_HANDWRITTEN_RULE, user_content[1]["text"])
            self.assertIn(PRESCRIPTION_OCR_FEW_SHOT_RULES, user_content[1]["text"])
            self.assertEqual(res["medications"][0]["usage"], "Uống trước ăn 30 phút (chữ viết tay)")

    def test_normalization_preserves_full_drug_name_and_fractional_dose(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rx_path = self._create_image(tmpdir)
            mock_response = {
                "doc_type": "prescription",
                "medications": [
                    {
                        "stt": 1,
                        "brand_name_as_printed": "YESOM 40 40mg",
                        "ingredients_as_printed": "Esomeprazol 40mg",
                        "quantity_as_printed": "14 Viên",
                        "schedule_as_printed": "Ngày uống 3 lần, mỗi lần 1 Viên (Trước ăn)",
                        "usage_as_printed": "Ngày uống 3 lần, mỗi lần 1 Viên (Trước ăn)",
                        "uncertain_fields": [],
                    },
                    {
                        "stt": 2,
                        "name": "Thuốc uống dạng lỏng 100ml (Hoạt chất mẫu)",
                        "brand_name_as_printed": "Thuốc uống dạng lỏng 100ml",
                        "ingredients_as_printed": "Hoạt chất mẫu",
                        "quantity_as_printed": "2 Chai",
                        "schedule_as_printed": "Ngày uống 3 lần, mỗi lần 1/3 Chai (Trước ăn)",
                        "usage_as_printed": "Ngày uống 3 lần, mỗi lần 1/3 Chai (Trước ăn)",
                        "uncertain_fields": [],
                    },
                    {
                        "stt": 3,
                        "name": "Siro mẫu 100ml (Hoạt chất B)",
                        "dose": "1/3 Chai / lần",
                        "quantity_as_printed": "1 Chai",
                        "schedule_as_printed": "Ngày uống 3 lần",
                        "usage_as_printed": "Ngày uống 3 lần, mỗi lần 1/3 Chai (Trước ăn)",
                        "purpose": "",
                        "uncertain_fields": [],
                    },
                ],
            }

            with (
                patch.object(llm_provider, "resolve_api_key", return_value="test-key-123456"),
                patch.object(llm_provider, "is_configured", return_value=True),
                patch.object(llm_provider, "generate_json", return_value=mock_response),
            ):
                res = extract_with_gemini_schema(rx_path, doc_type="prescription")

            meds = res["medications"]
            self.assertEqual(meds[0]["name"], "YESOM 40 40mg (Esomeprazol 40mg)")
            self.assertEqual(meds[0]["usage"], "Ngày uống 3 lần, mỗi lần 1 Viên (Trước ăn)")
            self.assertEqual(meds[1]["dose"], "1/3 Chai")
            self.assertEqual(meds[2]["dose"], "1/3 Chai / lần")
            self.assertEqual(meds[2]["purpose"], "")

    def test_reconciliation_dosing_parser_keeps_fractional_chai_and_before_meal(self):
        parsed = _parse_dosing_details("Ngày uống 3 lần, mỗi lần 1/3 Chai (Trước ăn)")
        self.assertEqual(parsed["dose"], "1/3 chai")
        self.assertEqual(parsed["frequency"], "3 lần / ngày")
        self.assertEqual(parsed["usage"], "Uống trước ăn")

    def test_normalize_vietnamese_units_adds_accents(self):
        self.assertEqual(_normalize_vietnamese_units("20 ONG"), "20 Ống")
        self.assertEqual(_normalize_vietnamese_units("63 GOI"), "63 Gói")
        self.assertEqual(_normalize_vietnamese_units("1 TUYP"), "1 Tuýp")
        self.assertEqual(_normalize_vietnamese_units("1/3 CHAI / lần"), "1/3 Chai / lần")

        with tempfile.TemporaryDirectory() as tmpdir:
            rx_path = self._create_image(tmpdir)
            mock_response = {
                "doc_type": "prescription",
                "medications": [
                    {
                        "stt": 1,
                        "name": "Thuốc ống 10ml (Hoạt chất A)",
                        "dose": "1 ONG / lần",
                        "quantity_as_printed": "20 ONG",
                        "schedule_as_printed": "Ngày uống 2 lần, mỗi lần 1 ONG (SAU ĂN)",
                        "usage_as_printed": "Ngày uống 2 lần, mỗi lần 1 ONG (SAU ĂN)",
                        "purpose": "",
                        "uncertain_fields": [],
                    },
                    {
                        "stt": 2,
                        "name": "Thuốc gói 1g (Hoạt chất B)",
                        "dose": "1/3 CHAI / lần",
                        "quantity_as_printed": "63 GOI",
                        "schedule_as_printed": "Ngày uống 3 lần, mỗi lần 1 GOI (TRƯỚC ĂN)",
                        "usage_as_printed": "Ngày uống 3 lần, mỗi lần 1 GOI (TRƯỚC ĂN)",
                        "purpose": "",
                        "uncertain_fields": [],
                    },
                    {
                        "stt": 3,
                        "name": "Kem bôi 15g (Hoạt chất C)",
                        "dose": "1 TUYP",
                        "quantity_as_printed": "1 TUYP",
                        "schedule_as_printed": "Bôi ngày 2 lần",
                        "usage_as_printed": "Bôi ngoài da 1 TUYP",
                        "purpose": "",
                        "uncertain_fields": [],
                    },
                ],
            }

            with (
                patch.object(llm_provider, "resolve_api_key", return_value="test-key-123456"),
                patch.object(llm_provider, "is_configured", return_value=True),
                patch.object(llm_provider, "generate_json", return_value=mock_response),
            ):
                res = extract_with_gemini_schema(rx_path, doc_type="prescription")

            meds = res["medications"]
            self.assertEqual(meds[0]["dose"], "1 Ống / lần")
            self.assertEqual(meds[0]["days"], "20 Ống")
            self.assertEqual(meds[0]["usage"], "Ngày uống 2 lần, mỗi lần 1 Ống (SAU ĂN)")
            self.assertEqual(meds[1]["dose"], "1/3 Chai / lần")
            self.assertEqual(meds[1]["days"], "63 Gói")
            self.assertEqual(meds[1]["usage"], "Ngày uống 3 lần, mỗi lần 1 Gói (TRƯỚC ĂN)")
            self.assertEqual(meds[2]["dose"], "1 Tuýp")
            self.assertEqual(meds[2]["days"], "1 Tuýp")

    def test_frontend_prescription_render_avoids_duplicate_lan_and_binds_gender(self):
        app_js = (Path(__file__).resolve().parent.parent / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("${escapeHtml(dose)} / lần", app_js)
        self.assertNotIn("${dose} / lần", app_js)
        self.assertIn("function normalizePrescriptionGender", app_js)
        self.assertIn("function sanitizePrescriptionAdminField", app_js)
        self.assertIn("verifyGenderSelect.value = normalizedGender;", app_js)

    def test_redacted_admin_rule_propagates_to_all_ocr_prompts(self):
        self.assertIn(PRESCRIPTION_OCR_REDACTED_RULE, PRESCRIPTION_OCR_SYSTEM_PROMPT)
        self.assertIn(PRESCRIPTION_OCR_REDACTED_RULE, PRESCRIPTION_OCR_FEW_SHOT_RULES)

        with tempfile.TemporaryDirectory() as tmpdir:
            rx_path = self._create_image(tmpdir)
            ocr_data = {"raw_text": "1. Paracetamol 500mg", "total_lines": 1, "avg_confidence": 0.9}

            with (
                patch.object(llm_provider, "resolve_api_key", return_value="test-key-123456"),
                patch.object(llm_provider, "is_configured", return_value=True),
                patch.object(llm_provider, "generate_json", return_value={"medications": []}) as generate,
            ):
                extract_with_gemini_schema(rx_path)
                self.assertIn(PRESCRIPTION_OCR_REDACTED_RULE, generate.call_args.kwargs["contents"][-1])

                normalize_and_analyze_with_gemini(ocr_data, original_filename="rx.jpg", file_path=rx_path)
                self.assertIn(PRESCRIPTION_OCR_REDACTED_RULE, generate.call_args.kwargs["contents"][-1])

                scan_prescription_with_gemini_vision(rx_path, original_filename="rx.jpg")
                self.assertIn(PRESCRIPTION_OCR_REDACTED_RULE, generate.call_args.kwargs["contents"][-1])

    def test_schema_and_reconciliation_do_not_invent_name_or_gender_for_redacted_rx(self):
        self.assertEqual(_sanitize_redacted_admin_field("Bệnh nhân"), "")
        self.assertEqual(_sanitize_redacted_admin_field(None), "")
        self.assertEqual(_sanitize_redacted_admin_field("Chưa xác định", is_gender=True), "")
        self.assertEqual(_sanitize_redacted_admin_field("Nữ", is_gender=True), "Nữ")

        with tempfile.TemporaryDirectory() as tmpdir:
            rx_path = self._create_image(tmpdir)
            redacted_llm = {
                "doc_type": "prescription",
                "patient_name": None,
                "dob": "Không rõ",
                "age": "",
                "gender": "Chưa xác định",
                "medications": [],
            }
            with (
                patch.object(llm_provider, "resolve_api_key", return_value="test-key-123456"),
                patch.object(llm_provider, "is_configured", return_value=True),
                patch.object(llm_provider, "generate_json", return_value=redacted_llm),
            ):
                extracted = extract_with_gemini_schema(rx_path, doc_type="prescription")
            self.assertEqual(extracted["patient_name"], "")
            self.assertEqual(extracted["dob"], "")
            self.assertEqual(extracted["age"], "")
            self.assertEqual(extracted["gender"], "")

        redacted_ocr_text = (
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
            "BỆNH VIỆN ĐA KHOA\n"
            "ĐƠN THUỐC\n"
            "Họ và tên:\n"
            "Năm sinh:        Giới tính:\n"
            "Địa chỉ: Quận Nam Từ Liêm, Hà Nội\n"
            "Chẩn đoán: Viêm họng cấp\n"
            "1. Paracetamol 500mg - Ngày uống 2 lần"
        )
        ocr_payload = {
            "success": True,
            "raw_text": redacted_ocr_text,
            "lines": [{"text": ln} for ln in redacted_ocr_text.splitlines()],
            "rows": [
                {"text": "Họ và tên: | Năm sinh: | Giới tính:", "items": [{"text": "Họ và tên:"}, {"text": "Năm sinh:"}, {"text": "Giới tính:"}]},
                {"text": "Địa chỉ: Quận Nam Từ Liêm, Hà Nội", "items": [{"text": "Địa chỉ: Quận Nam Từ Liêm, Hà Nội"}]},
            ],
        }
        reconciled = reconcile_parallel_results(
            ocr_payload,
            {"patient_name": "Bệnh nhân", "dob": None, "age": None, "gender": ""},
            doc_type="prescription",
        )
        self.assertEqual(reconciled.get("patient_name"), "")
        self.assertEqual(reconciled.get("dob"), "")
        self.assertEqual(reconciled.get("age"), "")
        self.assertEqual(reconciled.get("gender"), "")

        finalized = finalize_reviewed_document(
            {
                "patient_name": "",
                "dob": "",
                "age": "",
                "gender": "",
                "doctor": "",
                "facility": "",
                "diagnosis": "Viêm họng cấp",
                "date": "23/11/2026",
                "medications": [],
            },
            doc_type="prescription",
            filename_clean="rx_redacted.jpg",
            user_allergies=[],
        )
        self.assertEqual(finalized["patient_name"], "")
        self.assertEqual(finalized["gender"], "")

    def test_frontend_redacted_patient_ui_defaults_to_blank_and_chua_xac_dinh(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not available")

        app_js_path = Path(__file__).resolve().parent.parent / "frontend" / "static" / "js" / "app.js"
        js_src = app_js_path.read_text(encoding="utf-8")

        # Extract the exact frontend helpers under test cleanly
        start_norm = js_src.index("function sanitizePrescriptionAdminField")
        end_result = js_src.index("// ==============================================================================\n// NEXT-GEN MEDICAL DASHBOARD")
        # Include renderPrescriptionResult up to the lab/prescription branch after rawGender
        result_start = js_src.index("function renderPrescriptionResult(")
        result_branch = js_src.index("if (isLab) {", result_start)

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
                  classList: {{ add() {{}}, remove() {{}} }},
                  scrollIntoView() {{}},
                }};
              }}
              return elements[id];
            }}
            global.document = {{ getElementById: (id) => makeEl(id) }};
            global.fetch = () => Promise.resolve({{}});
            let currentPrescriptionData = null;
            let lastPrescriptionDataSnapshot = null;
            let currentUploadedFileUrl = '';
            let currentOcrSubView = 'input';
            function syncSubViewHistory() {{}}
            function loadPrescriptionHistory() {{}}
            function showMedicalToast() {{}}
            function escapeHtml(str) {{
              return String(str ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
            }}

            {js_src[start_norm:end_result]}

            assert.strictEqual(normalizePrescriptionGender(null), '');
            assert.strictEqual(normalizePrescriptionGender(''), '');
            assert.strictEqual(normalizePrescriptionGender('Chưa xác định'), '');
            assert.strictEqual(normalizePrescriptionGender('Không rõ'), '');
            assert.strictEqual(normalizePrescriptionGender('Nam'), 'Nam');
            assert.strictEqual(normalizePrescriptionGender('Nữ'), 'Nữ');

            assert.strictEqual(sanitizePrescriptionAdminField('Bệnh nhân', ['bệnh nhân']), '');
            assert.strictEqual(sanitizePrescriptionAdminField('Không rõ'), '');
            assert.strictEqual(sanitizePrescriptionAdminField('TRẦN VĂN B', ['bệnh nhân']), 'TRẦN VĂN B');

            // Case A: Redacted null / empty fields -> blank name & dob, Gender = Chưa xác định (value='')
            renderPrescriptionVerification({{
              patient_name: null,
              dob: '',
              age: null,
              gender: null,
              medications: [{{ name: 'Paracetamol 500mg' }}],
            }}, {{ pushHistory: false }});
            const verifyHtmlA = makeEl('prescription-verify-section').innerHTML;
            assert(verifyHtmlA.includes('id="verify-patient-name" type="text" value=""'), 'Expected blank name input');
            assert(verifyHtmlA.includes('id="verify-patient-dob" type="text" value=""'), 'Expected blank dob input');
            assert(verifyHtmlA.includes('<option value="" disabled selected>Chưa xác định</option>'), 'Expected Chưa xác định default selected');
            assert.strictEqual(makeEl('verify-patient-gender').value, '');

            // Case B: Hallucinated placeholders from backend -> still blank and Chưa xác định
            renderPrescriptionVerification({{
              patient_name: 'Bệnh nhân',
              dob: 'Không rõ',
              age: 'null',
              gender: 'Chưa xác định',
              medications: [{{ name: 'Paracetamol 500mg' }}],
            }}, {{ pushHistory: false }});
            const verifyHtmlB = makeEl('prescription-verify-section').innerHTML;
            assert(verifyHtmlB.includes('id="verify-patient-name" type="text" value=""'));
            assert(verifyHtmlB.includes('<option value="" disabled selected>Chưa xác định</option>'));
            assert.strictEqual(makeEl('verify-patient-gender').value, '');

            // Case C: Explicit patient data still binds properly
            renderPrescriptionVerification({{
              patient_name: 'NGUYỄN THỊ LAN',
              dob: '1992',
              gender: 'Nữ',
              medications: [{{ name: 'Paracetamol 500mg' }}],
            }}, {{ pushHistory: false }});
            const verifyHtmlC = makeEl('prescription-verify-section').innerHTML;
            assert(verifyHtmlC.includes('value="NGUYỄN THỊ LAN"'));
            assert(verifyHtmlC.includes('<option value="" disabled >Chưa xác định</option>'));
            assert(verifyHtmlC.includes('<option value="Nữ" selected>Nữ</option>'));
            assert.strictEqual(makeEl('verify-patient-gender').value, 'Nữ');
            """
        )
        proc = subprocess.run([node, "-e", script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=f"Node VM check failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
