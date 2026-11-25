"""Clinical chat and structured pre-visit intake routes."""

import logging
import uuid

from flask import jsonify, request, session

from core.chat.chat_service import execute_chat_workflow, process_clinical_chat
from core.chat.health_context import validate_chat_request
from core.chat.intake_service import StaleIntakeVersionError, intake_service
from core.shared.models import ClinicalConsultation, db
from core.shared.storage_service import decode_and_validate_base64_image
from routes.shared_helpers import commit_or_rollback, get_request_client_ip, resolve_app_attr

logger = logging.getLogger("MediMindApp")


def register_chat_routes(app, gemini_service):

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
        try:
            data = validate_chat_request(request.get_json(silent=True))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        user_message = data["message"]
        history = data["history"]
        image_str = data["image"]
        lang = data["lang"]
        conversation_id = data["conversation_id"]
        user_id = session.get("user_id")
        if "guest_token" not in session:
            session["guest_token"] = f"gst_{uuid.uuid4().hex[:12]}"
        guest_token = session.get("guest_token")

        if not user_message and not image_str:
            return jsonify({"error": "Vui lòng nhập nội dung tin nhắn hoặc tải ảnh."}), 400

        client_ip = get_request_client_ip()
        from core.auth.security_patch import get_rate_limit_identity, check_chat_rate_limit
        rate_id = get_rate_limit_identity(user_id=user_id, guest_token=guest_token, client_ip=client_ip)
        if not check_chat_rate_limit(rate_id, max_requests=25, window_seconds=60, enforce=not app.config.get("TESTING")):
            return jsonify({"error": "Bạn đang gửi tin nhắn quá nhanh. Vui lòng đợi ít phút rồi thử lại."}), 429

        image_bytes = None
        image_mime_type = "image/jpeg"
        if image_str:
            img_bytes, mime, err = decode_and_validate_base64_image(image_str)
            if err:
                return jsonify({"error": f"Tệp ảnh không hợp lệ: {err}"}), 400
            image_bytes = img_bytes
            image_mime_type = mime

        try:
            res = execute_chat_workflow(
                message=user_message,
                history=history,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                lang=lang,
                conversation_id=conversation_id,
                health_context=data["health_context"],
                gemini_service=gemini_service,
                user_id=user_id,
                guest_token=guest_token,
                chat_processor=resolve_app_attr("process_clinical_chat", process_clinical_chat)
            )
            return jsonify(res)
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403
        except KeyError:
            return jsonify({"error": "Cuộc trò chuyện đã được xóa trong lúc xử lý. Hãy bắt đầu cuộc trò chuyện mới."}), 409

        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception:
            logger.error("Không thể xử lý yêu cầu chatbot (chi tiết nội dung không được ghi log).")
            return jsonify({"error": "Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế."}), 500

    # ==============================================================
    # HỆ THỐNG HỎI BỆNH CÓ CẤU TRÚC & TÓM TẮT TRƯỚC KHÁM (MỤC 8 & 9)
    # ==============================================================


    def _get_request_identity():
        user_id = session.get("user_id")
        if "guest_token" not in session:
            session["guest_token"] = f"gst_{uuid.uuid4().hex[:12]}"
        return user_id, session.get("guest_token")


    @app.route("/api/intake/session", methods=["POST"])
    def intake_get_or_create_session():
        """Khởi tạo hoặc tải lại phiên hỏi bệnh lâm sàng có cấu trúc."""
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Nội dung yêu cầu phải là đối tượng JSON."}), 400
        conversation_id = data.get("conversation_id")

        user_id, guest_token = _get_request_identity()
        try:
            if data.get("flow") == "previsit":
                validated = validate_chat_request(data)
                return jsonify({"success": True, **intake_service.open_previsit(
                    validated["conversation_id"], user_id=user_id, guest_token=guest_token, lang=validated["lang"]
                )})
            s = intake_service.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403
        except KeyError:
            return jsonify({"error": "Không tìm thấy phiên hỏi bệnh."}), 404
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        return jsonify({
            "success": True,
            "conversation_id": s["conversation_id"],
            "status": s["status"],
            "facts": s["facts"],
            "version": s["version"],
            "is_confirmed": s["is_confirmed"]
        })

    @app.route("/api/intake/session/<conversation_id>", methods=["DELETE"])
    def intake_delete_session(conversation_id):
        """Delete only the caller's draft, actual transcript and saved summary."""
        user_id, guest_token = _get_request_identity()
        try:
            removed = intake_service.delete_session(conversation_id, user_id=user_id,
                                                    guest_token=guest_token, commit=False)
            if not removed:
                return jsonify({"error": "Không tìm thấy cuộc trò chuyện."}), 404
            if user_id:
                ClinicalConsultation.query.filter_by(user_id=user_id, conversation_id=conversation_id).delete()
            commit_or_rollback()
        except PermissionError:
            db.session.rollback()
            return jsonify({"error": "Bạn không có quyền xóa cuộc trò chuyện này."}), 403
        except Exception:
            db.session.rollback()
            logger.error("Không thể xóa cuộc trò chuyện đã xác thực chủ sở hữu.")
            return jsonify({"error": "Chưa xóa được cuộc trò chuyện. Vui lòng thử lại."}), 500
        return jsonify({"success": True, "message": "Đã xóa cuộc trò chuyện và bản tóm tắt đã lưu."})

    @app.route("/api/intake/message", methods=["POST"])
    def intake_send_message():
        """
        Tiếp nhận tin nhắn trong phiên hỏi bệnh:
          - Trích xuất dữ kiện (triệu chứng có, triệu chứng ĐÃ PHỦ NHẬN, thời gian, thân nhiệt)
          - Chọn câu hỏi tiếp theo từ dữ kiện còn thiếu (không hỏi lặp)
          - Cập nhật Tóm tắt trước khám 2 phần (Phần A & Phần B)
        """
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Nội dung yêu cầu phải là đối tượng JSON."}), 400
        if data.get("flow") == "previsit":
            user_id, guest_token = _get_request_identity()
            try:
                validated = validate_chat_request(data)
                skip = data.get("skip") is True
                if not (validated["message"] or skip):
                    raise ValueError("Vui lòng nhập câu trả lời.")
                return jsonify(intake_service.process_message(
                    conversation_id=validated["conversation_id"],
                    message="" if skip else validated["message"],
                    user_id=user_id,
                    guest_token=guest_token,
                    lang=validated["lang"],
                    previsit=True,
                    skip=skip,
                    expected_version=data.get("expected_version"),
                ))
            except PermissionError as error:
                return jsonify({"error": str(error)}), 403
            except KeyError:
                return jsonify({"error": "Không tìm thấy phiên hỏi bệnh."}), 404
            except StaleIntakeVersionError as error:
                return jsonify({"error": str(error)}), 409
            except ValueError as error:
                return jsonify({"error": str(error)}), 400
            except RuntimeError:
                return jsonify({"error": "Chưa lưu được câu trả lời. Vui lòng thử lại."}), 503
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


        user_id, guest_token = _get_request_identity()
        try:
            result = intake_service.process_message(
                conversation_id=conversation_id,
                message=user_message,
                image_bytes=image_bytes,
                user_id=user_id,
                guest_token=guest_token
            )
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403


        return jsonify(result)

    @app.route("/api/intake/update-fact", methods=["POST"])
    def intake_update_fact():
        """Chỉnh sửa 1 dữ kiện lâm sàng (tăng version và yêu cầu xác nhận lại)."""
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "Nội dung yêu cầu phải là đối tượng JSON."}), 400
        conversation_id = data.get("conversation_id")
        field = data.get("field")
        value = data.get("value")

        if not conversation_id or not field:
            return jsonify({"error": "Thiếu conversation_id hoặc trường cần cập nhật."}), 400


        user_id, guest_token = _get_request_identity()
        try:
            previsit = data.get("flow") == "previsit"
            lang = validate_chat_request(data)["lang"] if previsit else "vi"
            res = intake_service.update_fact(
                conversation_id,
                field,
                value,
                user_id=user_id,
                guest_token=guest_token,
                previsit=previsit,
                lang=lang,
                expected_version=data.get("expected_version"),
            )
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403
        except KeyError:
            return jsonify({"error": "Không tìm thấy phiên hỏi bệnh."}), 404
        except StaleIntakeVersionError as error:
            return jsonify({"error": str(error)}), 409
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except RuntimeError:
            if not previsit:
                raise
            return jsonify({"error": "Chưa lưu được chỉnh sửa. Vui lòng thử lại."}), 503


        return jsonify(res)

    @app.route("/api/intake/confirm-summary", methods=["POST"])
    def intake_confirm_summary():
        """Bệnh nhân xác nhận: Bản tóm tắt phản ánh đúng lời khai thực tế."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return jsonify({"error": "Thiếu conversation_id."}), 400


        user_id, guest_token = _get_request_identity()
        try:
            draft = intake_service.get_summary(conversation_id, user_id=user_id, guest_token=guest_token)
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403
        except KeyError:
            return jsonify({"error": "Không tìm thấy phiên tư vấn để lưu."}), 404
        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập để lưu vào hồ sơ."}), 401
        if data.get("save_to_record") is not True:
            return jsonify({"error": "Cần xác nhận lưu bản tóm tắt vào hồ sơ."}), 400
        if (not draft or data.get("version") != draft.get("version")
                or data.get("reviewed_facts") != draft.get("part_a_patient_facts")):
            return jsonify({"error": "Bản nháp đã thay đổi. Hãy xem lại trước khi lưu."}), 409
        if draft.get("ready_to_finalize") is False:
            return jsonify({"error": "Bản tóm tắt còn thiếu dữ kiện cần thiết. Hãy bổ sung phần đã đánh dấu trước khi lưu."}), 422
        try:
            res = intake_service.confirm_summary(
                conversation_id, user_id=user_id, guest_token=guest_token,
                reviewed_version=data.get("version"), reviewed_facts=data.get("reviewed_facts"), save_to_record=True,
            )
        except KeyError:
            return jsonify({"error": "Không tìm thấy phiên tư vấn để lưu."}), 404
        except StaleIntakeVersionError as error:
            return jsonify({"error": str(error)}), 409
        except ValueError as error:
            return jsonify({"error": str(error)}), 422
        except PermissionError as error:
            return jsonify({"error": str(error)}), 403
        if not res.get("success"):
            return jsonify(res), 500
        return jsonify(res)

    @app.route("/api/intake/summary/<conversation_id>", methods=["GET"])
    def intake_get_summary(conversation_id):
        """Lấy bản tóm tắt trước khám 2 phần của phiên."""

        user_id, guest_token = _get_request_identity()
        try:
            summary = intake_service.get_summary(
                conversation_id,
                user_id=user_id,
                guest_token=guest_token
            )
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403
        except KeyError:
            archived = None
            if user_id:
                from core.chat.consultation_service import get_clinical_summary
                _, saved, _ = get_clinical_summary(user_id, conversation_id=conversation_id)
                archived = saved.get("summary")
            if isinstance(archived, dict) and archived.get("part_a_patient_facts"):
                return jsonify({"conversation_id": conversation_id, "summary": archived, "archived": True})
            return jsonify({"error": "Không tìm thấy bản tóm tắt của phiên này."}), 404
        return jsonify({
            "conversation_id": conversation_id,
            "summary": summary
        })


