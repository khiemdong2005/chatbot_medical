# ==============================================================
# MEDIMIND CLINICAL AI - CỔNG DỊCH VỤ Y TẾ LÂM SÀNG
# Thiết kế theo tiêu chuẩn Bộ Y Tế & MedlinePlus (NIH Hoa Kỳ)
# ==============================================================

import os
import sys
import json
import base64
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

# Tải cấu hình môi trường (.env)
load_dotenv()

# Nạp cơ sở dữ liệu và xác thực danh tính
from core.models import db, User, init_db

# Nạp các phân hệ nghiệp vụ y khoa
from core.triage import analyze_symptoms, assess_emergency_risk, apply_safety_guardrails
from core.rag_service import medical_rag_service
from core.gemini_service import GeminiMedicalService

app = Flask(__name__)
# Secret key cho session bảo mật
app.secret_key = os.getenv("SECRET_KEY", "medimind-secret-key-super-safe-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///medimind.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

# Khởi tạo cơ sở dữ liệu SQLite an toàn
init_db(app)

# Khởi tạo dịch vụ trí tuệ nhân tạo Gemini
gemini_service = GeminiMedicalService()

# Thư mục lưu trữ dataset huấn luyện OCR / Scan
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf", "docx", "doc"}

def format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"

# ==============================================================
# HỆ THỐNG XÁC THỰC DANH TÍNH & PHÂN QUYỀN (RBAC)
# ==============================================================

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Đăng nhập hệ thống: Xác thực Email/Số điện thoại và Mật khẩu băm trong CSDL."""
    data = request.get_json(silent=True) or {}
    raw_identifier = data.get("email", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role")

    if not raw_identifier or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập định danh tài khoản và mật khẩu."}), 400

    # Tìm kiếm theo Email, Số điện thoại hoặc Phone Alias
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
    """Đăng ký tài khoản người dùng bằng Email hoặc Số điện thoại."""
    data = request.get_json(silent=True) or {}
    raw_identifier = data.get("email", "").strip()
    password = data.get("password", "").strip()
    full_name = data.get("full_name", "").strip() or data.get("name", "").strip()
    phone_number = data.get("phone_number", "").strip()
    dob = data.get("dob", "").strip()
    gender = data.get("gender", "").strip() or "Nam"
    role = data.get("role", "patient")

    if not raw_identifier or not password:
        return jsonify({"success": False, "error": "Vui lòng điền đầy đủ Email/SĐT và mật khẩu."}), 400

    if not full_name:
        full_name = "Bệnh nhân mới"

    # Phân loại Email hoặc Số điện thoại
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

    # Kiểm tra trùng lặp Email hoặc Số điện thoại
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

    user = User.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({"authenticated": False, "user": None})

    return jsonify({"authenticated": True, "user": user.to_dict()})

@app.route("/api/auth/profile", methods=["POST", "PUT"])
def auth_update_profile():
    """Cập nhật thông tin cá nhân của người dùng."""
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}

    if not user_id:
        req_id = data.get("id")
        if req_id:
            user_id = req_id

    if not user_id:
        return jsonify({"success": False, "error": "Vui lòng đăng nhập để cập nhật thông tin."}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "error": "Không tìm thấy thông tin tài khoản."}), 404

    full_name = data.get("name", "").strip()
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
# HỆ THỐNG PHÂN TẦNG LÂM SÀNG & TƯ VẤN Y TẾ 6 THÀNH PHẦN
# ==============================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Endpoint chính xử lý trò chuyện y tế:
      1. Tiền kiểm Cờ đỏ cấp cứu (xử lý phủ định)
      2. Truy vấn tri thức y khoa RAG từ ChromaDB
      3. Gọi AI Gemini Flash suy luận (kèm hỗ trợ Multimodal đọc ảnh Vision & Fallback offline)
      4. Hậu kiểm màng lọc chặn kê đơn kháng sinh bừa bãi
    """
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    history = data.get("history", [])
    image_str = data.get("image")
    lang = data.get("lang", "vi")

    if not user_message and not image_str:
        return jsonify({"error": "Vui lòng nhập nội dung tin nhắn hoặc tải ảnh."}), 400

    # Giải mã ảnh nếu có
    image_bytes = None
    image_mime_type = "image/jpeg"
    if image_str:
        try:
            if "," in image_str:
                header, b64_data = image_str.split(",", 1)
                if "image/png" in header:
                    image_mime_type = "image/png"
                elif "image/webp" in header:
                    image_mime_type = "image/webp"
            else:
                b64_data = image_str
            image_bytes = base64.b64decode(b64_data)
        except Exception as e:
            print(f"⚠️ Lỗi giải mã Base64 image: {e}")

    # -------------------------------------------------------------
    # BƯỚC 1: TIỀN KIỂM AN TOÀN (Pre-check Guardrail)
    # Phát hiện sớm cờ đỏ nguy kịch, có xử lý bẫy phủ định ("không khó thở")
    # -------------------------------------------------------------
    emergency = assess_emergency_risk(user_message, lang=lang)
    if emergency["is_emergency"]:
        return jsonify({
            "answer": emergency["message"],
            "risk_level": "Nguy cơ cao (Cần thăm khám khẩn)" if lang == "vi" else "High Risk (Immediate Care Needed)",
            "risk_score": 90,
            "symptoms": emergency["symptoms"],
            "specialist": "Cấp cứu 115 / Khoa Cấp cứu" if lang == "vi" else "Emergency 115 / ER Department",
            "is_emergency": True,
            "sources": [
                {
                    "title": "Quy trình Cấp cứu Ban đầu - Bộ Y Tế",
                    "source": "Cục Quản lý Khám chữa bệnh",
                    "url": "https://kcb.vn"
                }
            ],
        })

    # -------------------------------------------------------------
    # BƯỚC 2: TRUY VẤN TRI THỨC Y KHOA RAG TỪ CHROMADB (Top 2 đoạn khớp nhất)
    # -------------------------------------------------------------
    rag_docs = medical_rag_service.retrieve_context(user_message, top_k=2)

    # -------------------------------------------------------------
    # BƯỚC 3: BỘ NÃO SUY LUẬN AI (Gemini Flash) + FALLBACK DỰ PHÒNG NỘI BỘ
    # -------------------------------------------------------------
    gemini_result = gemini_service.generate_clinical_response(
        user_message,
        history,
        rag_docs=rag_docs,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        lang=lang
    )
    if gemini_result and "answer" in gemini_result:
        triage_result = gemini_result
    else:
        # Tự động kích hoạt bộ máy phác đồ nội bộ khi chưa có API key hoặc mất mạng
        triage_result = analyze_symptoms(user_message, history, lang=lang)
        if rag_docs:
            triage_result["sources"] = [
                {
                    "title": d.get("title", "MedlinePlus"),
                    "source": d.get("source", "MedlinePlus"),
                    "url": d.get("source_url", "https://medlineplus.gov")
                }
                for d in rag_docs
            ]

    # -------------------------------------------------------------
    # BƯỚC 4: HẬU KIỂM AN TOÀN (Post-check Guardrail)
    # Rà soát câu trả lời, chặn đứng việc tự ý kê đơn thuốc kháng sinh
    # -------------------------------------------------------------
    cleaned_answer = apply_safety_guardrails(triage_result.get("answer", ""), lang=lang)

    diff_diag = triage_result.get("differential_diagnosis", [])

    default_risk = "Thấp (Tự chăm sóc & Theo dõi)" if lang == "vi" else "Low (Self-care & Monitor)"
    default_spec = "Nội tổng quát" if lang == "vi" else "General Internal Medicine"

    return jsonify({
        "answer": cleaned_answer,
        "risk_level": triage_result.get("risk_level", default_risk),
        "risk_score": triage_result.get("risk_score", 30),
        "symptoms": triage_result.get("symptoms", []),
        "specialist": triage_result.get("specialist", default_spec),
        "visual_findings": triage_result.get("visual_findings", []),
        "differential_diagnosis": diff_diag,
        "is_emergency": False,
        "sources": triage_result.get("sources", [
            {
                "title": "Hướng dẫn Chăm sóc Ban đầu",
                "source": "MedlinePlus (NIH)",
                "url": "https://medlineplus.gov"
            }
        ])
    })

# ==============================================================
# HỆ THỐNG ĐỌC KẾT QUẢ XÉT NGHIỆM & DATASET HUẤN LUYỆN SCAN
# ==============================================================

@app.route("/api/upload-lab", methods=["POST"])
def upload_lab():
    """Tiếp nhận tệp ảnh / PDF / Word phục vụ huấn luyện model scan & phân tích chỉ số."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Không tìm thấy tệp đính kèm."}), 400
    
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"status": "error", "message": "Chưa chọn tệp hợp lệ."}), 400
    
    filename = secure_filename(file.filename)
    if not filename:
        import time
        filename = f"upload_{int(time.time())}.png"
    
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"status": "error", "message": "Định dạng không được hỗ trợ. Vui lòng chọn JPG, PNG, PDF hoặc Word (.docx)."}), 400
    
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)
    
    file_size_bytes = os.path.getsize(save_path)
    file_size_str = format_size(file_size_bytes)
    
    upload_time = datetime.now().strftime("%H:%M %d/%m/%Y")

    return jsonify({
        "status": "success",
        "file_name": file.filename,
        "saved_as": filename,
        "file_size": file_size_str,
        "file_type": ext.upper(),
        "uploaded_at": upload_time,
        "saved_path": f"uploads/{filename}",
        "message": "Đã lưu tệp vào thư mục huấn luyện model thành công."
    })

@app.route("/api/scan-files", methods=["GET"])
def get_scan_files():
    """Danh sách các tệp trong thư mục dataset huấn luyện scan."""
    files = []
    if os.path.exists(UPLOAD_FOLDER):
        for fname in os.listdir(UPLOAD_FOLDER):
            fpath = os.path.join(UPLOAD_FOLDER, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                files.append({
                    "name": fname,
                    "size": format_size(stat.st_size),
                    "type": ext.upper(),
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M %d/%m/%Y")
                })
    return jsonify({"status": "success", "files": files})

@app.route("/api/scan-files/<filename>", methods=["DELETE"])
def delete_scan_file(filename):
    """Xóa tệp khỏi thư mục dataset huấn luyện scan."""
    safe_name = secure_filename(filename)
    fpath = os.path.join(UPLOAD_FOLDER, safe_name)
    if os.path.exists(fpath):
        os.remove(fpath)
        return jsonify({"status": "success", "message": f"Đã xóa {safe_name}"})
    return jsonify({"status": "error", "message": "Tệp không tồn tại."}), 404

# ==============================================================
# PHIẾU CHUẨN BỊ TRƯỚC KHÁM CHO NGƯỜI DÂN (PRE-VISIT SUMMARY)
# ==============================================================

@app.route("/api/clinical-summary", methods=["GET"])
def clinical_summary():
    """
    Bản tóm tắt trước khám dành cho Người Dân (Pre-Consultation Summary).
    Giúp người dân mang theo khi đi khám bệnh để bác sĩ nắm bệnh sử trong 30 giây.
    """
    # Cho phép xem nếu đã đăng nhập trong session, hoặc tạm thời bỏ qua nếu đang test
    if not session.get("user_id"):
        return jsonify({
            "error": "Vui lòng đăng nhập để xem bản tóm tắt hồ sơ sức khỏe này."
        }), 401

    return jsonify({
        "status": "success",
        "chief_complaint": "Đau rát họng kèm sốt nhẹ về chiều (Nghiêm trọng: 6/10)",
        "hpi": "Triệu chứng xuất hiện 2 ngày nay, kèm nuốt đau và mệt mỏi toàn thân. Không khó thở, không phát ban ngoài da.",
        "red_flags": "ÂM TÍNH (Không khó thở, không tím tái, không đau tức ngực)",
        "provisional_diagnosis": "Viêm họng cấp thể xuất tiết (Khả năng do Rhinovirus)",
        "triage_recommendation": "Theo dõi tại nhà hoặc khám chuyên khoa Tai Mũi Họng nếu sốt cao > 38.5°C quá 48h.",
        "prep_for_patient": [
            "Ghi lại nhật ký nhiệt độ cơ thể sáng - chiều",
            "Mang theo danh sách các thuốc đang uống hằng ngày (nếu có)",
            "Nhịn ăn sáng nếu bác sĩ chỉ định lấy máu xét nghiệm"
        ]
    })

# ==============================================================
# GIAO DIỆN NGƯỜI DÙNG WEB (UI)
# ==============================================================

@app.route("/")
def index():
    """Trang chủ ứng dụng y tế MediMind."""
    return render_template("index.html")

if __name__ == "__main__":
    print("==================================================")
    print("  MEDIMIND CLINICAL AI - HỆ THỐNG Y TẾ SỐ ĐANG CHẠY")
    print("  Giao diện Web: http://127.0.0.1:8000")
    print("  Chuẩn kiến trúc: Phân tầng lâm sàng 6 cấp độ")
    print("==================================================")
    app.run(host="0.0.0.0", port=8000, debug=True)
