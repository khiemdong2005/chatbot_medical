import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================
# MEDIMIND CLINICAL AI - CỔNG DỊCH VỤ Y TẾ LÂM SÀNG
# Thiết kế theo tiêu chuẩn Bộ Y Tế & MedlinePlus (NIH Hoa Kỳ)
# ==============================================================

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

# Tải cấu hình môi trường (.env)
load_dotenv()

# Nạp cơ sở dữ liệu và các mô hình
from core.models import db, User, MedicalDocument, ClinicalConsultation, init_db
from core.storage_service import (
    process_secure_upload,
    decode_and_validate_base64_image,
    is_safe_path
)
from core.chat_service import process_clinical_chat
from core.gemini_service import GeminiMedicalService
from core.prescription_service import get_preset_data, analyze_uploaded_document
from core.intake_service import intake_service

logger = logging.getLogger("MediMindApp")


def create_app(test_config=None):
    """
    Application Factory Pattern:
    Khởi tạo ứng dụng Flask với cấu hình tùy biến linh hoạt.
    Khi kiểm thử, nạp test_config (SQLite in-memory) TRƯỚC KHI kết nối CSDL,
    bảo vệ 100% dữ liệu thật khỏi nguy cơ bị ghi đè hoặc drop_all.
    """
    app = Flask(__name__)

    is_prod = os.getenv("FLASK_ENV") == "production" or os.getenv("ENV") == "production"
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if is_prod and not (test_config and test_config.get("TESTING")):
            raise RuntimeError("Yêu cầu cấu hình SECRET_KEY an toàn trong môi trường Production!")
        secret_key = "medimind-secret-key-super-safe-2026-dev"

    app.secret_key = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///medimind.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_AS_ASCII"] = False

    # Cấu hình Cookie an toàn bảo vệ Session
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_prod or (os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1"))

    # Thư mục lưu trữ tệp tin mặc định
    default_upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    app.config["UPLOAD_FOLDER"] = default_upload_folder

    # Ghi đè cấu hình kiểm thử nếu có TRƯỚC KHI init_db
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Khởi tạo cơ sở dữ liệu an toàn theo đúng URI đã cấu hình
    init_db(app)

    # Khởi tạo dịch vụ trí tuệ nhân tạo Gemini
    gemini_service = GeminiMedicalService()

    # ==============================================================
    # HỆ THỐNG XÁC THỰC DANH TÍNH & PHÂN QUYỀN (RBAC)
    # ==============================================================

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        """Đăng nhập hệ thống: Xác thực Email/Số điện thoại và Mật khẩu băm trong CSDL."""
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or "").strip()
        password = data.get("password", "").strip()
        role = data.get("role")

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng nhập định danh tài khoản và mật khẩu."}), 400

        clean_phone = "".join(filter(str.isdigit, raw_identifier))
        user = User.query.filter(
            (User.email == raw_identifier) | 
            (User.phone_number == raw_identifier) |
            (User.phone_number == clean_phone) |
            (User.email == f"{clean_phone}@phone.medimind")
        ).first()

        if not user:
            return jsonify({"success": False, "error": "Tài khoản không tồn tại trên hệ thống."}), 404

        # Kiểm tra phân quyền truy cập
        if role and user.role != role:
            return jsonify({
                "success": False, 
                "error": f"Tài khoản này không có quyền truy cập vai trò '{role}'."
            }), 403

        # Xác thực mật khẩu
        if not user.check_password(password):
            return jsonify({"success": False, "error": "Mật khẩu không chính xác. Vui lòng kiểm tra lại."}), 401

        # Khởi tạo phiên làm việc (Session)
        session["user_id"] = user.id
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": f"Chào mừng {user.full_name} đã quay trở lại!",
            "user": user.to_dict()
        })


    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        """
        Đăng ký tài khoản người dùng:
        BẢO MẬT: Luôn tạo tài khoản với vai trò 'patient' (bệnh nhân).
        Tuyệt đối không cho phép client tự cấp quyền doctor hay admin.
        """
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip() or data.get("name", "").strip()
        phone_number = data.get("phone_number", "").strip()
        dob = data.get("dob", "").strip()
        gender = data.get("gender", "").strip() or "Nam"

        # Bắt buộc vai trò là patient
        role = "patient"

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng điền đầy đủ Email/SĐT và mật khẩu."}), 400

        if not full_name:
            full_name = "Bệnh nhân mới"

        if "@" in raw_identifier:
            email = raw_identifier
            if not phone_number:
                phone_number = None
        else:
            clean_phone = "".join(filter(str.isdigit, raw_identifier))
            if len(clean_phone) < 9 or len(clean_phone) > 11:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            phone_number = clean_phone
            email = f"{clean_phone}@phone.medimind"

        existing_user = User.query.filter(
            (User.email == email) | 
            ((User.phone_number == phone_number) & (User.phone_number.isnot(None)))
        ).first()
        if existing_user:
            return jsonify({"success": False, "error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}), 409

        new_user = User(
            email=email,
            full_name=full_name,
            role=role,
            phone_number=phone_number,
            dob=dob,
            gender=gender,
            license_code=None
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        session["user_id"] = new_user.id
        session["user_role"] = new_user.role

        return jsonify({
            "success": True,
            "message": "Đăng ký tài khoản thành công!",
            "user": new_user.to_dict()
        }), 201


    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        """Kiểm tra trạng thái phiên đăng nhập của người dân."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"authenticated": False, "user": None})

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"authenticated": False, "user": None})

        return jsonify({"authenticated": True, "user": user.to_dict()})


    @app.route("/api/auth/profile", methods=["POST", "PUT"])
    def auth_update_profile():
        """
        Cập nhật thông tin cá nhân:
        BẢO MẬT: Bắt buộc session đăng nhập hợp lệ. Bỏ fallback lấy id từ JSON body.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để cập nhật thông tin."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy thông tin tài khoản."}), 404

        data = request.get_json(silent=True) or {}
        full_name = data.get("name", "").strip() or data.get("full_name", "").strip()
        gender = data.get("gender", "").strip()
        dob = data.get("dob", "").strip()
        phone_number = data.get("phone_number", "").strip()
        address = data.get("address", "").strip()
        bhyt = data.get("bhyt", "").strip()
        email = data.get("email", "").strip()

        if full_name:
            user.full_name = full_name
        if gender:
            user.gender = gender
        if dob:
            user.dob = dob
        if phone_number:
            clean_phone = "".join(filter(str.isdigit, phone_number))
            if clean_phone:
                user.phone_number = clean_phone
        if address:
            user.address = address
        if bhyt:
            user.bhyt = bhyt
        if email and "@" in email and not user.email.endswith("@phone.medimind"):
            user.email = email

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Cập nhật thông tin cá nhân thành công!",
            "user": user.to_dict()
        })


    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        """Đăng xuất và hủy phiên làm việc."""
        session.clear()
        return jsonify({"success": True, "message": "Đã đăng xuất thành công."})


    # ==============================================================
    # HỆ THỐNG PHÂN TẦNG LÂM SÀNG & TƯ VẤN Y TẾ 4 TẦNG
    # ==============================================================

    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        Endpoint xử lý trò chuyện y tế:
          1. Tiền kiểm Cờ đỏ cấp cứu
          2. Truy vấn tri thức RAG từ ChromaDB
          3. Suy luận Gemini Flash + Fallback nội bộ
          4. Hậu kiểm can thiệp kháng sinh
        """
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()
        history = data.get("history", [])
        image_str = data.get("image")
        lang = data.get("lang", "vi")

        if not user_message and not image_str:
            return jsonify({"error": "Vui lòng nhập nội dung tin nhắn hoặc tải ảnh."}), 400

        image_bytes = None
        image_mime_type = "image/jpeg"
        if image_str:
            img_bytes, mime, err = decode_and_validate_base64_image(image_str)
            if err:
                return jsonify({"error": f"Tệp ảnh không hợp lệ: {err}"}), 400
            image_bytes = img_bytes
            image_mime_type = mime

        try:
            res = process_clinical_chat(
                message=user_message,
                history=history,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                lang=lang,
                gemini_service=gemini_service
            )

            # Lưu lịch sử tư vấn nếu người dùng đã đăng nhập để phục vụ Pre-visit Summary
            user_id = session.get("user_id")
            if user_id:
                try:
                    consultation = ClinicalConsultation(
                        user_id=user_id,
                        message=user_message,
                        answer=res.get("answer", ""),
                        risk_level=res.get("risk_level", ""),
                        risk_score=res.get("risk_score", 30),
                        symptoms=json.dumps(res.get("symptoms", []), ensure_ascii=False),
                        specialist=res.get("specialist", ""),
                        is_emergency=res.get("is_emergency", False)
                    )
                    db.session.add(consultation)
                    db.session.commit()
                except Exception as db_err:
                    db.session.rollback()
                    logger.warning(f"Lỗi lưu lịch sử tư vấn: {db_err}")

            return jsonify(res)

        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            logger.error(f"Lỗi xử lý tư vấn y tế: {e}")
            return jsonify({"error": "Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế."}), 500

    # ==============================================================
    # HỆ THỐNG HỎI BỆNH CÓ CẤU TRÚC & TÓM TẮT TRƯỚC KHÁM (MỤC 8 & 9)
    # ==============================================================

    @app.route("/api/intake/session", methods=["POST"])
    def intake_get_or_create_session():
        """Khởi tạo hoặc tải lại phiên hỏi bệnh lâm sàng có cấu trúc."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        user_id = session.get("user_id")
        s = intake_service.get_or_create_session(conversation_id, user_id=user_id)
        return jsonify({
            "success": True,
            "conversation_id": s["conversation_id"],
            "status": s["status"],
            "facts": s["facts"],
            "version": s["version"],
            "is_confirmed": s["is_confirmed"]
        })

    @app.route("/api/intake/message", methods=["POST"])
    def intake_send_message():
        """
        Tiếp nhận tin nhắn trong phiên hỏi bệnh:
          - Trích xuất dữ kiện (triệu chứng có, triệu chứng ĐÃ PHỦ NHẬN, thời gian, thân nhiệt)
          - Chọn câu hỏi tiếp theo từ dữ kiện còn thiếu (không hỏi lặp)
          - Cập nhật Tóm tắt trước khám 2 phần (Phần A & Phần B)
        """
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        user_message = (data.get("message") or "").strip()
        image_str = data.get("image")

        if not user_message and not image_str:
            return jsonify({"error": "Vui lòng nhập nội dung mô tả hoặc đính kèm ảnh."}), 400

        image_bytes = None
        if image_str:
            img_bytes, mime, err = decode_and_validate_base64_image(image_str)
            if not err:
                image_bytes = img_bytes

        s = intake_service.get_or_create_session(conversation_id, user_id=session.get("user_id"))
        result = intake_service.process_message(
            conversation_id=s["conversation_id"],
            message=user_message,
            image_bytes=image_bytes
        )

        return jsonify(result)

    @app.route("/api/intake/update-fact", methods=["POST"])
    def intake_update_fact():
        """Chỉnh sửa 1 dữ kiện lâm sàng (tăng version và yêu cầu xác nhận lại)."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        field = data.get("field")
        value = data.get("value")

        if not conversation_id or not field:
            return jsonify({"error": "Thiếu conversation_id hoặc trường cần cập nhật."}), 400

        res = intake_service.update_fact(conversation_id, field, value)
        return jsonify(res)

    @app.route("/api/intake/confirm-summary", methods=["POST"])
    def intake_confirm_summary():
        """Bệnh nhân xác nhận: Bản tóm tắt phản ánh đúng lời khai thực tế."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return jsonify({"error": "Thiếu conversation_id."}), 400

        res = intake_service.confirm_summary(conversation_id)
        return jsonify(res)

    @app.route("/api/intake/summary/<conversation_id>", methods=["GET"])
    def intake_get_summary(conversation_id):
        """Lấy bản tóm tắt trước khám 2 phần của phiên."""
        summary = intake_service.get_summary(conversation_id)
        return jsonify({
            "conversation_id": conversation_id,
            "summary": summary
        })


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
            db.session.commit()

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

        docs = MedicalDocument.query.filter_by(owner_id=user_id).order_by(MedicalDocument.created_at.desc()).all()
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
            return jsonify({"status": "error", "message": "Tài liệu không tồn tại hoặc bạn không có quyền xóa."}), 404

        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        file_disk_path = Path(upload_folder) / doc.storage_filename
        if is_safe_path(file_disk_path, Path(upload_folder)) and file_disk_path.exists():
            try:
                os.remove(file_disk_path)
            except Exception as e:
                logger.warning(f"Lỗi xóa file vật lý: {e}")

        db.session.delete(doc)
        db.session.commit()

        return jsonify({"status": "success", "message": f"Đã xóa tài liệu '{doc.original_filename}' thành công."})


    # ==============================================================
    # QUÉT & PHÂN TÍCH ĐƠN THUỐC / KẾT QUẢ XÉT NGHIỆM AI
    # ==============================================================

    @app.route("/api/prescription/scan", methods=["POST"])
    def scan_prescription():
        """
        Quét và phân tích đơn thuốc hoặc kết quả xét nghiệm:
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
                    owner_id=user_id
                )
                db.session.add(doc)
                db.session.commit()
                doc_id = doc.id
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Lỗi lưu MedicalDocument cho scan: {e}")

            res = analyze_uploaded_document(meta["absolute_path"], meta["original_filename"])
            if doc_id:
                res["document_id"] = doc_id
            return jsonify(res)

        # 2. Trường hợp yêu cầu kịch bản mẫu thử nghiệm (Preset)
        if preset:
            return jsonify(get_preset_data(preset))

        # Không có file và không có preset -> Báo lỗi Bad Request
        return jsonify({
            "status": "error",
            "message": "Vui lòng đính kèm tệp đơn thuốc/xét nghiệm hoặc chỉ định kịch bản mẫu thử nghiệm hợp lệ."
        }), 400


    # ==============================================================
    # PHIẾU CHUẨN BỊ TRƯỚC KHÁM CHO NGƯỜI DÂN (PRE-VISIT SUMMARY)
    # ==============================================================

    @app.route("/api/clinical-summary", methods=["GET"])
    def clinical_summary():
        """
        Bản tóm tắt trước khám:
        - Bắt buộc đăng nhập.
        - Trích xuất từ ca tư vấn thực tế của tài khoản hiện tại.
        - Trả 'no_data' nếu người dùng chưa có lượt tư vấn nào.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({
                "error": "Vui lòng đăng nhập để xem bản tóm tắt hồ sơ sức khỏe."
            }), 401

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "Không tìm thấy thông tin tài khoản."}), 404

        latest_consultation = ClinicalConsultation.query.filter_by(user_id=user_id).order_by(ClinicalConsultation.created_at.desc()).first()

        if not latest_consultation:
            return jsonify({
                "status": "no_data",
                "message": "Chưa có dữ liệu tư vấn hoặc bệnh án gần đây cho tài khoản này. "
                           "Vui lòng thực hiện tư vấn triệu chứng với trợ lý AI trước khi xuất phiếu trước khám."
            }), 200

        symptoms_list = []
        try:
            symptoms_list = json.loads(latest_consultation.symptoms or "[]")
        except Exception:
            symptoms_list = []

        symptoms_text = ", ".join(symptoms_list) if symptoms_list else "Triệu chứng chung"

        return jsonify({
            "status": "success",
            "patient_name": user.full_name,
            "patient_id": f"BN-2026-{user.id:04d}",
            "chief_complaint": f"{latest_consultation.message[:120]} (Dấu hiệu: {symptoms_text})",
            "hpi": f"Người bệnh ghi nhận: '{latest_consultation.message}'. Mức độ rủi ro đánh giá: {latest_consultation.risk_level}.",
            "red_flags": "DƯƠNG TÍNH (Cần cấp cứu khẩn cấp)" if latest_consultation.is_emergency else "ÂM TÍNH (Không phát hiện dấu hiệu nguy kịch tức thời)",
            "provisional_diagnosis": f"Định hướng ban đầu: {latest_consultation.specialist}",
            "triage_recommendation": f"Khuyến nghị chuyên khoa: {latest_consultation.specialist}. "
                                     f"{'Cần thăm khám sớm tại cơ sở y tế.' if latest_consultation.risk_score >= 40 else 'Theo dõi sức khỏe và chăm sóc tại nhà an toàn.'}",
            "prep_for_patient": [
                "Ghi lại nhật ký nhiệt độ và diễn biến triệu chứng sáng - chiều",
                "Mang theo danh sách các thuốc đang uống hằng ngày hoặc tiền sử dị ứng (nếu có)",
                "Thông báo cho bác sĩ thời điểm chính xác triệu chứng bắt đầu xuất hiện"
            ]
        })


    @app.route("/api/consultations", methods=["GET"])
    def get_consultations():
        """Lấy danh sách các phiên tư vấn đã lưu của tài khoản hiện tại."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"consultations": []}), 200
        consultations = ClinicalConsultation.query.filter_by(user_id=user_id).order_by(ClinicalConsultation.created_at.desc()).limit(20).all()
        return jsonify({"consultations": [c.to_dict() for c in consultations]}), 200

    @app.route("/api/consultations/<int:cid>", methods=["DELETE"])
    def delete_consultation(cid):
        """Xóa một phiên tư vấn theo ID của người dùng."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập."}), 401
        c = ClinicalConsultation.query.filter_by(id=cid, user_id=user_id).first()
        if c:
            db.session.delete(c)
            db.session.commit()
            return jsonify({"message": "Đã xóa phiên tư vấn thành công."}), 200
        return jsonify({"error": "Không tìm thấy phiên tư vấn."}), 404

    # ==============================================================
    # GIAO DIỆN NGƯỜI DÙNG WEB (UI)
    # ==============================================================

    @app.route("/")
    def index():
        """Trang chủ ứng dụng y tế MediMind."""
        return render_template("index.html")

    return app


# Export singleton app instance for WSGI / CLI
app = create_app()

if __name__ == "__main__":
    flask_debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")
    port = int(os.getenv("PORT", 8000))
    print("==================================================")
    print("  MEDIMIND CLINICAL AI - HỆ THỐNG Y TẾ SỐ ĐANG CHẠY")
    print(f"  Giao diện Web: http://127.0.0.1:{port}")
    print(f"  Chế độ Debug: {flask_debug}")
    print("  Chuẩn kiến trúc: Phân tầng lâm sàng an toàn")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=flask_debug)
