"""Prescription OCR, Lab Upload, Scan History & Secure Upload Serving routes."""

import json
import logging
import os
import uuid
from pathlib import Path
from flask import jsonify, request, session

from core.db_utils import commit_or_rollback
from core.models import MedicalDocument, User, db
from core.pipeline_orchestrator import (
    HEADER_FIELDS,
    REVIEW_FIELDS,
    build_reviewed_prescription_timeline,
    finalize_reviewed_document,
    process_medical_document_pipeline,
    process_prescription_transcription,
)
from core.prescription_service import get_preset_data
from core.reconciliation_service import is_plausible_medication_name
from core.storage_service import is_safe_path, process_secure_upload

logger = logging.getLogger("MediMindApp")


def register_ocr_routes(app, *, default_upload_folder):
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
            logger.error("Lỗi lưu thông tin tài liệu upload: %s", e)
            if os.path.exists(meta["absolute_path"]):
                try:
                    os.remove(meta["absolute_path"])
                except Exception:
                    pass
            return jsonify({"status": "error", "message": "Không thể lưu thông tin tài liệu. Vui lòng thử lại sau."}), 500


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
    @app.route("/api/ocr/analyze", methods=["POST"])
    def scan_prescription():
        """
        Chép nội dung đơn thuốc từ ảnh để người dùng đối chiếu.
        Luồng phân tích phiếu xét nghiệm yêu cầu doc_type=lab_test.
        BẢO MẬT & TRUNG THỰC:
          - Bắt buộc đăng nhập khi tải file lên; lưu bản ghi MedicalDocument liên kết owner_id.
          - Khi không đọc được, trả trạng thái lỗi hoặc yêu cầu đối chiếu.
          - Presets chỉ hoạt động khi có tham số 'preset' cụ thể và luôn trả kèm is_demo=True.
          - Nếu không có file và không có preset, trả mã lỗi 400.
        """
        preset = request.args.get("preset") or request.form.get("preset")
        if not preset and request.is_json:
            data = request.get_json(silent=True) or {}
            preset = data.get("preset")

        # 1. Trường hợp người dùng tải tệp lên
        if "file" in request.files:
            source_only = request.form.get("doc_type") != "lab_test"
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
            success, meta, err = process_secure_upload(file, upload_folder)
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
                    owner_id=user_id,
                    parsed_data=json.dumps({
                        "source_only": True, "type": "prescription", "scan_pending": True
                    }) if source_only else None,
                )
                db.session.add(doc)
                commit_or_rollback()
                doc_id = doc.id
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Lỗi lưu MedicalDocument cho scan: {e}")
                if source_only:
                    return jsonify({"status": "failed", "message": "Không thể tạo bản nháp đơn thuốc."}), 500

            if source_only:
                res = process_prescription_transcription(
                    file_path=meta["absolute_path"],
                    original_filename=meta["original_filename"],
                    enable_fallback=True,
                )
            else:
                mask_pii = request.form.get("mask_pii", "false").lower() in ("true", "1")
                user_obj = db.session.get(User, user_id)
                profile_allergies = (user_obj.to_dict().get("allergies") or "") if user_obj else ""
                user_allergies = [s.strip() for s in profile_allergies.split(",") if s.strip()] if isinstance(profile_allergies, str) else list(profile_allergies)
                req_allergies = request.form.get("allergies")
                if req_allergies:
                    user_allergies.extend([a.strip() for a in req_allergies.split(",") if a.strip()])

                res = process_medical_document_pipeline(
                    file_path=meta["absolute_path"], original_filename=meta["original_filename"],
                    doc_type_hint="lab_test", mask_pii=mask_pii, user_allergies=user_allergies,
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
                            if source_only:
                                draft_payload["source_only"] = True
                            doc.parsed_data = json.dumps(draft_payload, ensure_ascii=False)
                            db.session.commit()
                    except Exception as commit_err:
                        logger.warning(f"Lỗi cập nhật parsed_data cho MedicalDocument {doc_id}: {commit_err}")
                        db.session.rollback()
                        if source_only:
                            return jsonify({"status": "failed", "message": "Không thể lưu bản nháp đơn thuốc."}), 500
            else:
                if meta and meta.get("storage_filename"):
                    res["preview_image_url"] = f"/uploads/{meta['storage_filename']}"
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
        if draft.get("scan_pending"):
            return jsonify({"message": "Bản nháp đơn thuốc chưa sẵn sàng để xác nhận."}), 409
        source_only = draft.get("source_only") is True
        override_kind = payload.get("doc_type")
        kind = draft["type"]
        if source_only and override_kind not in (None, "prescription"):
            return jsonify({"message": "Bản nháp này là đơn thuốc."}), 400
        if not source_only and override_kind in ("prescription", "lab_test"):
            kind = override_kind
        key = "medications" if kind == "prescription" else "metrics"
        fields = REVIEW_FIELDS[key]
        raw_rows = payload.get(key)
        rows = raw_rows if isinstance(raw_rows, list) else []
        if not source_only:
            rows = [r for r in rows if isinstance(r, dict) and any(str(r.get(k, "")).strip() for k in fields)]
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
        if source_only:
            result = finalize_reviewed_document(reviewed, kind, doc.original_filename, [], source_only=True)
        else:
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
        commit_or_rollback()
        return jsonify(result)

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
        history = [d.to_dict() for d in docs]
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
                if doc.doc_type == "prescription" and parsed_json.get("source_only") and "timeline" not in parsed_json:
                    parsed_json["timeline"] = build_reviewed_prescription_timeline(parsed_json.get("medications", []))
                parsed_json["document_id"] = doc.id
                parsed_json["uploaded_filename"] = doc.original_filename
                parsed_json["uploaded_at"] = doc.created_at.strftime("%H:%M %d/%m/%Y") if doc.created_at else ""
                if doc.storage_filename:
                    parsed_json["preview_image_url"] = f"/uploads/{doc.storage_filename}"
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
        Lưu dữ liệu đơn thuốc/xét nghiệm sau khi người dùng đã dò lại và xác nhận chính xác.
        Bắt buộc đăng nhập, kiểm tra quyền sở hữu owner_id, chuẩn hóa schema trước khi lưu DB.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xác nhận tài liệu y tế."}), 401

        raw_data = request.get_json(silent=True)
        if not isinstance(raw_data, dict):
            return jsonify({"status": "error", "message": "Dữ liệu xác nhận không hợp lệ."}), 400

        doc_id = raw_data.get("document_id")
        try:
            doc_id_int = int(doc_id) if doc_id is not None and not isinstance(doc_id, bool) else None
        except (TypeError, ValueError):
            doc_id_int = None

        if not doc_id_int or doc_id_int <= 0:
            return jsonify({"status": "error", "message": "Thiếu mã tài liệu (document_id) hợp lệ."}), 400

        doc = MedicalDocument.query.filter_by(id=doc_id_int, owner_id=user_id).first()
        if not doc:
            return jsonify({"status": "error", "message": "Không tìm thấy tài liệu hoặc bạn không có quyền cập nhật."}), 404

        def _clean_str(val, max_len: int = 250) -> str:
            if not isinstance(val, str):
                return ""
            return val.strip()[:max_len]

        def _clean_item_dict(item, max_keys: int = 20, max_val_len: int = 500) -> dict:
            cleaned = {}
            for idx, (k, v) in enumerate(item.items()):
                if idx >= max_keys or not isinstance(k, str):
                    continue
                key_name = k.strip()[:64]
                if not key_name:
                    continue
                if isinstance(v, str):
                    cleaned[key_name] = v.strip()[:max_val_len]
                elif isinstance(v, (int, float, bool)) or v is None:
                    cleaned[key_name] = v
            return cleaned

        existing_parsed = {}
        if doc.parsed_data:
            try:
                loaded = json.loads(doc.parsed_data)
                if isinstance(loaded, dict):
                    existing_parsed = loaded
            except (TypeError, ValueError):
                existing_parsed = {}

        if existing_parsed.get("source_only") is True:
            return jsonify({"message": "Hãy xác nhận qua màn hình đối chiếu đơn thuốc."}), 409

        sanitized = dict(existing_parsed)
        sanitized["document_id"] = doc.id

        scalar_limits = {
            "patient_name": 150,
            "diagnosis": 500,
            "facility": 250,
            "doctor": 150,
            "date": 64,
            "dob": 64,
            "age": 32,
            "gender": 32,
            "duration": 120,
            "icd10_code": 32,
            "icd10": 32,
            "icd_code": 32,
            "doc_title": 250,
            "interpretation": 4000,
            "uploaded_filename": 255,
        }
        for field, max_len in scalar_limits.items():
            if field in raw_data and isinstance(raw_data[field], str):
                sanitized[field] = _clean_str(raw_data[field], max_len)

        raw_doc_type = _clean_str(raw_data.get("doc_type") or raw_data.get("type") or "", 32).lower()
        existing_doc_type = _clean_str(existing_parsed.get("doc_type") or existing_parsed.get("type") or "", 32).lower()
        if raw_doc_type in ("prescription", "lab_test"):
            sanitized["doc_type"] = raw_doc_type
            sanitized["type"] = raw_doc_type

        if "medications" in raw_data and isinstance(raw_data["medications"], list):
            sanitized["medications"] = [
                _clean_item_dict(m) for m in raw_data["medications"][:50] if isinstance(m, dict)
            ]

        for lab_key in ("labs", "metrics"):
            if lab_key in raw_data and isinstance(raw_data[lab_key], list):
                sanitized[lab_key] = [
                    _clean_item_dict(item) for item in raw_data[lab_key][:100] if isinstance(item, dict)
                ]

        if "warnings" in raw_data and isinstance(raw_data["warnings"], list):
            clean_warnings = []
            for w in raw_data["warnings"][:30]:
                if isinstance(w, str):
                    clean_warnings.append(w.strip()[:500])
                elif isinstance(w, dict):
                    clean_warnings.append(_clean_item_dict(w))
            sanitized["warnings"] = clean_warnings

        if "timeline" in raw_data and isinstance(raw_data["timeline"], dict):
            clean_tl = {}
            for slot in ("morning", "noon", "evening", "bedtime"):
                slot_items = raw_data["timeline"].get(slot)
                if isinstance(slot_items, list):
                    clean_tl[slot] = [
                        _clean_item_dict(item) if isinstance(item, dict) else _clean_str(item, 300)
                        for item in slot_items[:30]
                        if isinstance(item, (dict, str))
                    ]
            sanitized["timeline"] = clean_tl

        preview_url = _clean_str(raw_data.get("preview_image_url"), 255)
        if preview_url.startswith("/uploads/") and ".." not in preview_url:
            sanitized["preview_image_url"] = preview_url

        is_lab_doc = (
            raw_doc_type == "lab_test"
            or existing_doc_type == "lab_test"
            or doc.doc_type == "lab_test"
            or (bool(sanitized.get("labs") or sanitized.get("metrics")) and not sanitized.get("medications"))
        )

        try:
            if is_lab_doc:
                doc.doc_type = "lab_test"
                sanitized["doc_type"] = "lab_test"
            elif doc.doc_type == "ocr_draft":
                doc.doc_type = "prescription"
                sanitized.setdefault("doc_type", "prescription")

            if sanitized.get("patient_name"):
                doc.patient_name = sanitized["patient_name"]
            if sanitized.get("diagnosis"):
                doc.diagnosis = sanitized["diagnosis"]
            if sanitized.get("facility"):
                doc.facility = sanitized["facility"]
            if sanitized.get("doctor"):
                doc.doctor = sanitized["doctor"]

            if is_lab_doc:
                lab_items = sanitized.get("labs") or sanitized.get("metrics") or []
                doc.summary = f"{len(lab_items)} chỉ số xét nghiệm"
            else:
                meds = sanitized.get("medications") or []
                med_names = [
                    m.get("standard_name") or m.get("name")
                    for m in meds[:3]
                    if isinstance(m, dict) and (m.get("standard_name") or m.get("name"))
                ]
                sum_text = f"{len(meds)} loại thuốc"
                if med_names:
                    sum_text += f": {', '.join(med_names)}"
                    if len(meds) > 3:
                        sum_text += f" và {len(meds) - 3} thuốc khác"
                doc.summary = sum_text

            doc.parsed_data = json.dumps(sanitized, ensure_ascii=False)
            commit_or_rollback()
        except Exception as e:
            db.session.rollback()
            logger.warning("Lỗi cập nhật xác nhận đơn thuốc: %s", e)
            return jsonify({"status": "error", "message": "Không thể lưu xác nhận tài liệu. Vui lòng thử lại."}), 500

        return jsonify({"status": "success", "message": "Đã xác nhận đơn thuốc thành công.", "data": sanitized})


    @app.route("/uploads/<filename>")
    def serve_uploaded_file(filename):
        """Phục vụ file ảnh đơn thuốc an toàn cho người dùng xem và đối soát.

        VULN-05 FIX: Require authenticated session + verify MedicalDocument ownership
        before serving any uploaded file. Unauthenticated or unauthorised requests
        receive 401/403 respectively, preventing insecure direct object reference.
        """
        from flask import send_from_directory
        from werkzeug.utils import secure_filename

        # --- VULN-05: Authentication gate ---
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem file."}), 401

        clean_name = secure_filename(filename)
        if not clean_name:
            return jsonify({"status": "error", "message": "Tên file không hợp lệ."}), 400

        # --- VULN-05: Ownership verification via MedicalDocument.owner_id ---
        doc = MedicalDocument.query.filter_by(
            storage_filename=clean_name, owner_id=user_id
        ).first()
        if not doc:
            return jsonify({"status": "error", "message": "Không tìm thấy tài liệu hoặc bạn không có quyền truy cập."}), 403

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

        db.session.delete(doc)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"status": "error", "message": "Không thể xóa tài liệu khỏi cơ sở dữ liệu."}), 500
        return jsonify({"status": "success", "message": f"Đã xóa thành công '{doc.original_filename}' khỏi lịch sử."})


