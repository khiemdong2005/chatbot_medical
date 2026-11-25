"""Lab upload, prescription OCR pipeline, review and history routes."""

import json
import logging
import os
from pathlib import Path
import re
import time
import uuid

from flask import jsonify, request, session

from core.chat.grounding_service import parse_frequency_to_schedule
from core.ocr.gemini_schema_service import _sanitize_redacted_admin_field
from core.ocr.pipeline_orchestrator import (
    HEADER_FIELDS,
    REVIEW_FIELDS,
    build_ui_timeline,
    finalize_reviewed_document,
    process_medical_document_pipeline,
)
from core.ocr.prescription_service import get_preset_data
from core.ocr.reconciliation_service import is_plausible_medication_name
from core.shared.models import MedicalDocument, PrescriptionHistory, User, db
from core.shared.storage_service import is_safe_path, process_secure_upload
from routes.shared_helpers import DEFAULT_UPLOAD_FOLDER as default_upload_folder, commit_or_rollback

logger = logging.getLogger("MediMindApp")


def register_ocr_routes(app):
    # ==============================================================
    # HỆ THỐNG QUẢN LÝ TÀI LIỆU Y TẾ & SCAN DATASET (RBAC & SECURE STORAGE)
    # ==============================================================

    @app.route("/api/upload-lab", methods=["POST"])
    def upload_lab():
        """
        Tiếp nhận tệp ảnh / PDF / Word phục vụ scan:
        BẢO MẬT: Bắt buộc đăng nhập, kiểm tra kích thước, magic bytes, lưu UUID ngẫu nhiên và gắn owner_id.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để tải lên tài liệu y tế."}), 401

        if "file" not in request.files:
            return jsonify({"status": "error", "message": "Không tìm thấy tệp đính kèm."}), 400

        file = request.files["file"]
        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        success, meta, err_msg = process_secure_upload(file, upload_folder)
        if not success:
            return jsonify({"status": "error", "message": err_msg}), 400

        try:
            new_doc = MedicalDocument(
                storage_filename=meta["storage_filename"],
                original_filename=meta["original_filename"],
                file_path=meta["file_path"],
                file_size=meta["file_size"],
                file_type=meta["file_type"],
                mime_type=meta["mime_type"],
                owner_id=user_id
            )
            db.session.add(new_doc)
            commit_or_rollback()

            upload_time = new_doc.created_at.strftime("%H:%M %d/%m/%Y")
            return jsonify({
                "status": "success",
                "document_id": new_doc.id,
                "file_name": new_doc.original_filename,
                "saved_as": new_doc.storage_filename,
                "file_size": new_doc.to_dict()["size"],
                "file_type": new_doc.file_type,
                "uploaded_at": upload_time,
                "message": "Đã lưu tài liệu an toàn vào hồ sơ sức khỏe."
            })
        except Exception as e:
            db.session.rollback()
            if os.path.exists(meta["absolute_path"]):
                try:
                    os.remove(meta["absolute_path"])
                except Exception:
                    pass
            return jsonify({"status": "error", "message": f"Không thể lưu thông tin tài liệu: {e}"}), 500


    @app.route("/api/scan-files", methods=["GET"])
    def get_scan_files():
        """
        Danh sách tài liệu thuộc sở hữu của người dùng hiện tại (owner_id).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem danh sách tài liệu."}), 401

        docs = (
            MedicalDocument.query.filter_by(owner_id=user_id)
            .filter(MedicalDocument.doc_type != "ocr_draft")
            .order_by(MedicalDocument.created_at.desc())
            .all()
        )
        files = [d.to_dict() for d in docs]
        return jsonify({"status": "success", "files": files})


    @app.route("/api/scan-files/<doc_identifier>", methods=["DELETE"])
    def delete_scan_file(doc_identifier):
        """
        Xóa tệp khỏi danh sách tài liệu thuộc quyền sở hữu của người dùng.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để thực hiện thao tác."}), 401

        doc = None
        if doc_identifier.isdigit():
            doc = MedicalDocument.query.filter_by(id=int(doc_identifier), owner_id=user_id).first()

        if not doc:
            doc = MedicalDocument.query.filter_by(storage_filename=doc_identifier, owner_id=user_id).first()

        if not doc:
            doc = MedicalDocument.query.filter_by(original_filename=doc_identifier, owner_id=user_id).first()

        if not doc:
            return jsonify({"status": "error", "message": "Tài liệu không tồn tại hoặc bạn không có quyền xóa."}), 404

        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        file_disk_path = Path(upload_folder) / doc.storage_filename
        if is_safe_path(file_disk_path, Path(upload_folder)) and file_disk_path.exists():
            try:
                os.remove(file_disk_path)
            except Exception as e:
                logger.warning(f"Lỗi xóa file vật lý: {e}")

        PrescriptionHistory.query.filter_by(document_id=doc.id, user_id=user_id).delete()
        db.session.delete(doc)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"status": "error", "message": "Không thể xóa tài liệu khỏi cơ sở dữ liệu."}), 500

        return jsonify({"status": "success", "message": f"Đã xóa tài liệu '{doc.original_filename}' thành công."})


    # ==============================================================
    # QUÉT & PHÂN TÍCH ĐƠN THUỐC LÂM SÀNG AI
    # ==============================================================

    @app.route("/api/prescription/scan", methods=["POST"])
    def scan_prescription():
        """
        Quét và phân tích đơn thuốc lâm sàng:
        BẢO MẬT & TRUNG THỰC:
          - Bắt buộc đăng nhập khi tải file lên; lưu bản ghi MedicalDocument liên kết owner_id.
          - Khi OCR / AI thất bại, trả về status failed/needs_review; không bịa dữ liệu mẫu.
          - Presets chỉ hoạt động khi có tham số 'preset' cụ thể và luôn trả kèm is_demo=True.
          - Nếu không có file và không có preset, trả mã lỗi 400.
        """
        preset = request.args.get("preset") or request.form.get("preset")
        if not preset and request.is_json:
            data = request.get_json(silent=True) or {}
            preset = data.get("preset")

        # 1. Trường hợp người dùng tải tệp lên
        if "file" in request.files:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({
                    "status": "error",
                    "message": "Vui lòng đăng nhập để tải lên và phân tích tài liệu y tế."
                }), 401

            file = request.files["file"]
            if not file or file.filename == "":
                return jsonify({"status": "error", "message": "Chưa chọn tệp hợp lệ."}), 400

            upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
            success, meta, err = process_secure_upload(
                file, upload_folder, detect_image_format=True
            )
            if not success:
                return jsonify({"status": "failed", "needs_review": True, "message": err}), 400

            # Lưu liên kết chủ sở hữu vào CSDL
            doc_id = None
            try:
                doc = MedicalDocument(
                    storage_filename=meta["storage_filename"],
                    original_filename=meta["original_filename"],
                    file_path=meta["file_path"],
                    file_size=meta["file_size"],
                    file_type=meta["file_type"],
                    mime_type=meta["mime_type"],
                    doc_type="ocr_draft",
                    owner_id=user_id
                )
                db.session.add(doc)
                commit_or_rollback()
                doc_id = doc.id
            except Exception as e:
                logger.warning(f"Lỗi lưu MedicalDocument cho scan: {e}")

            mask_pii = request.form.get("mask_pii", "false").lower() in ("true", "1")
            profile_allergies = db.session.get(User, user_id).to_dict().get("allergies") or ""
            user_allergies = [s.strip() for s in profile_allergies.split(",") if s.strip()] if isinstance(profile_allergies, str) else list(profile_allergies)
            req_allergies = request.form.get("allergies")
            if req_allergies:
                user_allergies.extend([a.strip() for a in req_allergies.split(",") if a.strip()])

            client_scan_id = re.sub(r"[^A-Za-z0-9_-]", "", request.headers.get("X-Scan-ID", ""))[:64]
            scan_id = uuid.uuid4().hex
            scan_started = time.monotonic()
            logger.info(
                "prescription_scan_started scan_id=%s filename=%s",
                scan_id, os.path.basename(meta.get("original_filename", ""))[:160],
            )
            try:
                res = process_medical_document_pipeline(
                    file_path=meta["absolute_path"],
                    original_filename=meta["original_filename"],
                    mask_pii=mask_pii,
                    user_allergies=user_allergies
                )
            except Exception as scan_err:
                logger.exception(
                    "prescription_scan_failed scan_id=%s filename=%s duration_ms=%d error_type=%s",
                    scan_id, os.path.basename(meta.get("original_filename", ""))[:160],
                    int((time.monotonic() - scan_started) * 1000), type(scan_err).__name__,
                )
                raise
            logger.info(
                "prescription_scan_finished scan_id=%s filename=%s duration_ms=%d "
                "status=%s backend_medication_count=%d",
                scan_id, os.path.basename(meta.get("original_filename", ""))[:160],
                int((time.monotonic() - scan_started) * 1000),
                str(res.get("status", "unknown")) if isinstance(res, dict) else "invalid_response",
                len(res.get("medications", [])) if isinstance(res, dict) and isinstance(res.get("medications"), list) else 0,
            )

            if doc_id:
                res["document_id"] = doc_id
                res["preview_image_url"] = f"/uploads/{meta['storage_filename']}"

                # Cập nhật kết quả bóc tách lâm sàng vào bản ghi MedicalDocument làm data người dùng
                if res and res.get("status") in ("success", "review"):
                    try:
                        doc = db.session.get(MedicalDocument, doc_id)
                        if doc:
                            if res.get("status") == "success":
                                doc.doc_type = "prescription"
                            else:
                                doc.doc_type = "ocr_draft"
                            doc.diagnosis = res.get("diagnosis", "")
                            doc.facility = res.get("facility", "")
                            doc.doctor = res.get("doctor", "")
                            doc.patient_name = res.get("patient_name", "")

                            meds = res.get("medications", [])
                            med_names = [m.get("standard_name") or m.get("name") for m in meds[:3] if m.get("name")]
                            sum_text = f"{len(meds)} loại thuốc"
                            if med_names:
                                sum_text += f": {', '.join(med_names)}"
                                if len(meds) > 3:
                                    sum_text += f" và {len(meds) - 3} thuốc khác"

                            doc.summary = sum_text
                            draft_payload = dict(res.get("data") or res)
                            if "type" not in draft_payload:
                                draft_payload["type"] = res.get("doc_type") or "prescription"
                            doc.parsed_data = json.dumps(draft_payload, ensure_ascii=False)
                            db.session.commit()
                    except Exception as commit_err:
                        logger.warning(f"Lỗi cập nhật parsed_data cho MedicalDocument {doc_id}: {commit_err}")
                        db.session.rollback()
            else:
                if meta and meta.get("storage_filename"):
                    res["preview_image_url"] = f"/uploads/{meta['storage_filename']}"

            image_size = {"width": None, "height": None}
            try:
                from PIL import Image
                with Image.open(meta["absolute_path"]) as source_image:
                    image_size = {"width": int(source_image.width), "height": int(source_image.height)}
            except Exception:
                pass
            res["scan_id"] = scan_id
            res["client_scan_id"] = client_scan_id or None
            for field_name in ("boxes", "ocr_lines", "unclassified_ocr_regions"):
                for region in res.get(field_name, []) if isinstance(res.get(field_name), list) else []:
                    if isinstance(region, dict):
                        region["scan_id"] = scan_id
            for medicine in res.get("medications", []) if isinstance(res.get("medications"), list) else []:
                if isinstance(medicine, dict):
                    medicine["scan_id"] = scan_id
            if isinstance(res.get("data"), dict):
                for medicine in res["data"].get("medications", []) if isinstance(res["data"].get("medications"), list) else []:
                    if isinstance(medicine, dict):
                        medicine["scan_id"] = scan_id
            res["source_image"] = {
                "filename": meta.get("original_filename", ""),
                "url": res.get("preview_image_url", ""),
                "scan_id": scan_id,
                **image_size,
            }
            return jsonify(res)

        # 2. Trường hợp yêu cầu kịch bản mẫu thử nghiệm (Preset)
        if preset:
            return jsonify(get_preset_data(preset))

        # Không có file và không có preset -> Báo lỗi Bad Request
        return jsonify({
            "status": "error",
            "message": "Vui lòng đính kèm tệp đơn thuốc hợp lệ hoặc chọn đơn thuốc mẫu để thử nghiệm."
        }), 400


    # ==============================================================
    # QUẢN LÝ LỊCH SỬ ĐƠN THUỐC ĐÃ IMPORT
    # ==============================================================

    def _summarize_prescription_meds(meds):
        if not isinstance(meds, list):
            return ""
        med_names = [
            str(m.get("standard_name") or m.get("name") or "").strip()
            for m in meds[:3]
            if isinstance(m, dict) and (m.get("standard_name") or m.get("name"))
        ]
        summary_text = f"{len(meds)} loại thuốc"
        if med_names:
            summary_text += f": {', '.join(med_names)}"
            if len(meds) > 3:
                summary_text += f" và {len(meds) - 3} thuốc khác"
        return summary_text

    def _ensure_prescription_timeline(payload):
        meds = payload.get("medications")
        if not isinstance(meds, list) or not meds:
            return payload.get("timeline") if isinstance(payload.get("timeline"), dict) else {}

        existing = payload.get("timeline")
        slots = ("morning", "noon", "evening", "bedtime", "external")
        if isinstance(existing, dict) and any(isinstance(existing.get(slot), list) and existing.get(slot) for slot in slots):
            return existing

        built = {slot: [] for slot in slots}
        for med in meds:
            if not isinstance(med, dict):
                continue
            med_name = str(med.get("standard_name") or med.get("name") or "").strip()
            if not med_name:
                continue
            raw_dose = str(med.get("dose") or med.get("dosage") or "").strip()
            has_dose = bool(raw_dose)
            m_dose = raw_dose if has_dose else "Chưa rõ liều (Cần đối chiếu đơn)"
            needs_rev = bool(med.get("needs_review")) or not has_dose
            sched = med.get("schedule") if isinstance(med.get("schedule"), dict) else None
            if not sched or not any(isinstance(v, dict) and v.get("active") for v in sched.values()):
                sched = parse_frequency_to_schedule(
                    str(med.get("frequency") or med.get("cu") or ""),
                    str(med.get("usage") or med.get("instructions") or med.get("purpose") or ""),
                )
            for slot in slots:
                slot_info = sched.get(slot) if isinstance(sched, dict) else None
                if isinstance(slot_info, dict) and slot_info.get("active"):
                    built[slot].append({
                        "name": med_name,
                        "dose": m_dose,
                        "note": slot_info.get("note") or "Theo chỉ dẫn của bác sĩ/dược sĩ",
                        "needs_review": needs_rev,
                    })
        return built

    def _coerce_optional_int(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        s = str(value or "").strip()
        return int(s) if s.isdigit() else None

    def _upsert_prescription_history(user_id, raw_payload, doc=None, history_id=None):
        payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
        resolved_doc_id = doc.id if doc else _coerce_optional_int(payload.get("document_id"))
        resolved_hist_id = history_id if history_id is not None else _coerce_optional_int(payload.get("history_id"))

        if doc is None and resolved_doc_id is not None:
            doc = MedicalDocument.query.filter_by(id=resolved_doc_id, owner_id=user_id).first()
            resolved_doc_id = doc.id if doc else None

        payload["patient_name"] = _sanitize_redacted_admin_field(payload.get("patient_name"))
        payload["dob"] = _sanitize_redacted_admin_field(payload.get("dob") or payload.get("birth_date"))
        payload["age"] = _sanitize_redacted_admin_field(payload.get("age"))
        payload["gender"] = _sanitize_redacted_admin_field(payload.get("gender"), is_gender=True)

        diagnosis = str(payload.get("diagnosis") or "").strip()
        facility = str(payload.get("facility") or "").strip()
        doctor = str(payload.get("doctor") or "").strip()
        doc_type = str(payload.get("doc_type") or payload.get("type") or "prescription").strip() or "prescription"
        if doc_type not in ("prescription", "lab_test"):
            doc_type = "prescription"
        payload["doc_type"] = doc_type
        payload["type"] = doc_type

        raw_img = str(payload.get("image_url") or payload.get("preview_image_url") or "").strip()
        if raw_img.startswith("blob:") or raw_img.startswith("data:"):
            raw_img = ""
        if not raw_img and doc and doc.storage_filename:
            raw_img = f"/uploads/{doc.storage_filename}"

        meds = payload.get("medications") if isinstance(payload.get("medications"), list) else []
        payload["timeline"] = _ensure_prescription_timeline(payload)
        summary_text = _summarize_prescription_meds(meds)

        record = None
        if resolved_hist_id is not None:
            record = PrescriptionHistory.query.filter_by(id=resolved_hist_id, user_id=user_id).first()
        if record is None and resolved_doc_id is not None:
            record = PrescriptionHistory.query.filter_by(document_id=resolved_doc_id, user_id=user_id).order_by(PrescriptionHistory.id.desc()).first()
        if record is None:
            record = PrescriptionHistory(user_id=user_id)
            db.session.add(record)

        record.document_id = resolved_doc_id
        record.image_url = raw_img
        record.patient_name = payload["patient_name"]
        record.diagnosis = diagnosis
        record.facility = facility
        record.doctor = doctor
        record.summary = summary_text
        record.json_drugs = json.dumps(payload, ensure_ascii=False)
        db.session.flush()

        payload["history_id"] = record.id
        if resolved_doc_id is not None:
            payload["document_id"] = resolved_doc_id
        payload["image_url"] = raw_img
        payload["preview_image_url"] = raw_img
        record.json_drugs = json.dumps(payload, ensure_ascii=False)

        if doc is not None:
            if doc.doc_type == "ocr_draft":
                doc.doc_type = doc_type
            doc.patient_name = payload["patient_name"]
            if diagnosis:
                doc.diagnosis = diagnosis
            if facility:
                doc.facility = facility
            if doctor:
                doc.doctor = doctor
            doc.summary = summary_text
            doc.parsed_data = record.json_drugs

        return record, payload

    @app.post("/api/prescription/<int:doc_id>/confirm")
    def confirm_reviewed_document(doc_id):
        owner = session.get("user_id")
        if not owner:
            return jsonify({"message": "Vui lòng đăng nhập."}), 401
        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=owner).first_or_404()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            return jsonify({"message": "Cần xác nhận dữ liệu đã đối chiếu."}), 400
        if doc.doc_type != "ocr_draft" or not doc.parsed_data:
            return jsonify({"message": "Tài liệu không còn chờ xác nhận."}), 409
        draft = json.loads(doc.parsed_data)
        override_kind = payload.get("doc_type")
        kind = override_kind if override_kind in ("prescription", "lab_test") else draft["type"]
        key = "medications" if kind == "prescription" else "metrics"
        fields = REVIEW_FIELDS[key]
        raw_rows = payload.get(key)
        if isinstance(raw_rows, list):
            rows = [r for r in raw_rows if isinstance(r, dict) and any(str(r.get(k, "")).strip() for k in fields)]
        else:
            rows = []
        if not 1 <= len(rows) <= 200:
            return jsonify({"message": "Cần ít nhất một dòng dữ liệu đã kiểm tra."}), 400
        def clean(row, keys):
            if not isinstance(row, dict) or any(not isinstance(row.get(k, ""), str) or len(row.get(k, "")) > 2000 for k in keys):
                raise ValueError
            return {k: row.get(k, "").strip() for k in keys}
        try:
            reviewed = clean(payload, HEADER_FIELDS)
            reviewed[key] = [clean(row, fields) for row in rows]
            if any(not row[fields[0]] for row in reviewed[key]):
                raise ValueError
        except ValueError:
            return jsonify({"message": "Hãy kiểm tra tên và dữ liệu từng dòng."}), 400
        if kind == "prescription" and any(
            not is_plausible_medication_name(row["name"])
            for row in reviewed["medications"]
        ):
            return jsonify({"message": "Có dòng không phải tên thuốc (ví dụ ngày tháng hoặc nhãn trên phiếu). Vui lòng sửa hoặc xóa dòng đó."}), 400
        result = finalize_reviewed_document(reviewed, kind, doc.original_filename, draft.get("allergies", []))
        result["document_id"] = doc.id
        changed = MedicalDocument.query.filter_by(id=doc.id, owner_id=owner, doc_type="ocr_draft").update({
            "doc_type": kind, "diagnosis": reviewed["diagnosis"], "facility": reviewed["facility"],
            "doctor": reviewed["doctor"], "patient_name": reviewed["patient_name"],
            "summary": ", ".join(row[fields[0]] for row in reviewed[key][:3]),
            "parsed_data": json.dumps(result, ensure_ascii=False)})
        if not changed:
            db.session.rollback()
            return jsonify({"message": "Tài liệu đã được xác nhận."}), 409
        doc = db.session.get(MedicalDocument, doc.id)
        _, saved_payload = _upsert_prescription_history(owner, result, doc=doc)
        commit_or_rollback()
        return jsonify(saved_payload)

    @app.route("/api/ocr/save_history", methods=["POST"])
    def save_ocr_history():
        """Lưu toàn bộ kết quả OCR đã xác nhận/chỉnh sửa vào bảng PrescriptionHistory."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để lưu lịch sử đơn thuốc."}), 401

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Dữ liệu đơn thuốc không hợp lệ."}), 400

        doc_id = _coerce_optional_int(data.get("document_id"))
        history_id = _coerce_optional_int(data.get("history_id"))
        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=user_id).first() if doc_id is not None else None

        try:
            record, saved_payload = _upsert_prescription_history(user_id, data, doc=doc, history_id=history_id)
            commit_or_rollback()
        except Exception as err:
            logger.warning(f"Lỗi lưu PrescriptionHistory: {err}")
            return jsonify({"status": "error", "message": "Không thể lưu đơn thuốc vào cơ sở dữ liệu."}), 500

        return jsonify({
            "status": "success",
            "message": "Đã lưu đơn thuốc vào lịch sử thành công.",
            "id": record.id,
            "history_id": record.id,
            "document_id": record.document_id,
            "record": record.to_dict(include_payload=True),
            "data": saved_payload,
        })

    @app.route("/api/ocr/get_history", methods=["GET"])
    def get_ocr_history():
        """Lấy danh sách đơn thuốc đã lưu của người dùng hiện tại, sắp xếp mới nhất trước."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({
                "status": "error",
                "message": "Vui lòng đăng nhập để xem lịch sử đơn thuốc.",
                "history": [],
                "total": 0,
            }), 401

        rows = (
            PrescriptionHistory.query.filter_by(user_id=user_id)
            .order_by(PrescriptionHistory.created_at.desc(), PrescriptionHistory.id.desc())
            .all()
        )
        history = [row.to_dict(include_payload=True) for row in rows]
        return jsonify({"status": "success", "history": history, "total": len(history)})

    @app.route("/api/ocr/get_history/<int:history_id>", methods=["GET"])
    def get_ocr_history_detail(history_id):
        """Lấy chi tiết JSON đơn thuốc theo ID thuộc quyền sở hữu của user hiện tại."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem chi tiết đơn thuốc."}), 401

        record = PrescriptionHistory.query.filter_by(id=history_id, user_id=user_id).first()
        if not record:
            return jsonify({"status": "error", "message": "Không tìm thấy hồ sơ hoặc bạn không có quyền xem."}), 404

        record_dict = record.to_dict(include_payload=True)
        payload = dict(record_dict.get("JSON_drugs") or {})
        payload["history_id"] = record.id
        if record.document_id and not payload.get("document_id"):
            payload["document_id"] = record.document_id
        if record.image_url:
            payload["image_url"] = record.image_url
            payload["preview_image_url"] = record.image_url
        payload["uploaded_at"] = record_dict["uploaded_at"]
        return jsonify({"status": "success", "record": record_dict, "data": payload})

    @app.route("/api/ocr/history/<int:history_id>", methods=["DELETE"])
    def delete_ocr_history_item(history_id):
        """Xóa một bản ghi lịch sử OCR thuộc quyền sở hữu của user hiện tại."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để thực hiện thao tác."}), 401

        record = PrescriptionHistory.query.filter_by(id=history_id, user_id=user_id).first()
        if not record:
            return jsonify({"status": "error", "message": "Hồ sơ không tồn tại hoặc bạn không có quyền xóa."}), 404

        linked_doc_id = record.document_id
        db.session.delete(record)
        if linked_doc_id is not None:
            doc = MedicalDocument.query.filter_by(id=linked_doc_id, owner_id=user_id).first()
            if doc:
                upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
                file_disk_path = Path(upload_folder) / doc.storage_filename
                if is_safe_path(file_disk_path, Path(upload_folder)) and file_disk_path.exists():
                    try:
                        os.remove(file_disk_path)
                    except Exception as e:
                        logger.warning(f"Lỗi xóa file vật lý: {e}")
                PrescriptionHistory.query.filter_by(document_id=doc.id, user_id=user_id).delete()
                db.session.delete(doc)

        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"status": "error", "message": "Không thể xóa đơn thuốc khỏi cơ sở dữ liệu."}), 500
        return jsonify({"status": "success", "message": "Đã xóa đơn thuốc khỏi lịch sử thành công."})

    @app.route("/api/prescription/history", methods=["GET"])
    def get_prescription_history():
        """
        Lấy danh sách lịch sử các đơn thuốc mà user đã import:
        Bao gồm thời gian import, chẩn đoán bệnh, tóm tắt thuốc, cơ sở y tế.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem lịch sử hồ sơ."}), 401

        docs = MedicalDocument.query.filter_by(owner_id=user_id).filter(MedicalDocument.doc_type != "ocr_draft").order_by(MedicalDocument.created_at.desc()).all()
        history = []
        for d in docs:
            item = d.to_dict()
            if d.storage_filename:
                item["preview_image_url"] = f"/uploads/{d.storage_filename}"
            history.append(item)
        return jsonify({"status": "success", "history": history, "total": len(history)})


    @app.route("/api/prescription/history/<int:doc_id>", methods=["GET"])
    def get_prescription_history_detail(doc_id):
        """
        Xem lại chi tiết toàn bộ dữ liệu đơn thuốc đã được bóc tách trước đó.
        Cho phép người dùng xem lại ngay kết quả phân tích mà không cần chụp/quét lại ảnh.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem chi tiết."}), 401

        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=user_id).first()
        if not doc or doc.doc_type == "ocr_draft":
            return jsonify({"status": "error", "message": "Không tìm thấy hồ sơ hoặc bạn không có quyền xem."}), 404

        if doc.parsed_data:
            try:
                parsed_json = json.loads(doc.parsed_data)
                parsed_json["document_id"] = doc.id
                parsed_json["uploaded_filename"] = doc.original_filename
                parsed_json["uploaded_at"] = doc.created_at.strftime("%H:%M %d/%m/%Y") if doc.created_at else ""
                if doc.storage_filename:
                    parsed_json["preview_image_url"] = f"/uploads/{doc.storage_filename}"
                meds_saved = parsed_json.get("medications") or (parsed_json.get("data") or {}).get("medications") or []
                tl_saved = parsed_json.get("timeline")
                if meds_saved and (not isinstance(tl_saved, dict) or not any(tl_saved.get(k) for k in ("morning", "noon", "evening", "bedtime", "external"))):
                    parsed_json["timeline"] = build_ui_timeline(meds_saved)
                return jsonify({"status": "success", "data": parsed_json})
            except Exception as json_err:
                logger.warning(f"Lỗi parse JSON doc {doc_id}: {json_err}")

        return jsonify({
            "status": "partial",
            "message": "Đơn thuốc này chưa có dữ liệu bóc tách chi tiết.",
            "doc": doc.to_dict()
        })


    @app.route("/api/prescription/confirm", methods=["POST"])
    def confirm_prescription():
        """
        Lưu dữ liệu đơn thuốc sau khi người dùng đã dò lại và xác nhận chính xác.
        Đồng bộ vào bảng PrescriptionHistory và MedicalDocument (nếu có).
        """
        user_id = session.get("user_id")
        data = request.get_json(silent=True) or {}
        doc_id = _coerce_optional_int(data.get("document_id"))
        history_id = _coerce_optional_int(data.get("history_id"))

        meds_payload = data.get("medications", []) if isinstance(data, dict) else []
        if isinstance(meds_payload, list) and meds_payload:
            data["timeline"] = build_ui_timeline(meds_payload)

        if user_id and isinstance(data, dict):
            try:
                doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=user_id).first() if doc_id is not None else None
                _, saved_payload = _upsert_prescription_history(user_id, data, doc=doc, history_id=history_id)
                commit_or_rollback()
                data = saved_payload
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Lỗi cập nhật xác nhận đơn thuốc: {e}")

        return jsonify({"status": "success", "message": "Đã xác nhận đơn thuốc thành công.", "data": data})


    @app.route("/uploads/<filename>")
    def serve_uploaded_file(filename):
        """Phục vụ file ảnh đơn thuốc an toàn cho người dùng xem và đối soát."""
        from flask import send_from_directory
        from werkzeug.utils import secure_filename
        clean_name = secure_filename(filename)
        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        return send_from_directory(upload_folder, clean_name)


    @app.route("/api/prescription/history/<int:doc_id>", methods=["DELETE"])
    def delete_prescription_history_item(doc_id):
        """
        Xóa một đơn thuốc khỏi lịch sử hồ sơ của người dùng.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để thực hiện thao tác."}), 401

        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=user_id).first()
        if not doc:
            return jsonify({"status": "error", "message": "Tài liệu không tồn tại hoặc bạn không có quyền xóa."}), 404

        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        file_disk_path = Path(upload_folder) / doc.storage_filename
        if is_safe_path(file_disk_path, Path(upload_folder)) and file_disk_path.exists():
            try:
                os.remove(file_disk_path)
            except Exception as e:
                logger.warning(f"Lỗi xóa file vật lý: {e}")

        PrescriptionHistory.query.filter_by(document_id=doc.id, user_id=user_id).delete()
        db.session.delete(doc)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"status": "error", "message": "Không thể xóa tài liệu khỏi cơ sở dữ liệu."}), 500
        return jsonify({"status": "success", "message": f"Đã xóa thành công '{doc.original_filename}' khỏi lịch sử."})


