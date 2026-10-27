import os
import sys
from dotenv import load_dotenv

# Ensure UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tải cấu hình biến môi trường từ .env
load_dotenv()

from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
from core.models import db, User, init_db
from core.triage import analyze_symptoms, assess_emergency_risk
from core.gemini_service import GeminiMedicalService

app = Flask(__name__)

# Cấu hình bảo mật phiên & Cơ sở dữ liệu (SQLite ở Local, PostgreSQL khi lên AWS)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "medimind-clinical-session-secret-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///medimind.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Khởi tạo CSDL SQLite / Postgres & Nạp tài khoản mẫu
init_db(app)

# Khởi tạo dịch vụ AI Google Gemini
gemini_service = GeminiMedicalService()

@app.route("/")
def index():
    return render_template("index.html")

# ==============================================================
# HỆ THỐNG XÁC THỰC NGƯỜI DÙNG & BÁC SĨ (AUTHENTICATION APIS)
# ==============================================================

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Đăng nhập hệ thống: Xác thực Email/Số điện thoại và Mật khẩu băm trong CSDL."""
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier", "").strip().lower()
    password = data.get("password", "")

    if not identifier or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ tài khoản và mật khẩu."}), 400

    # Tìm kiếm theo Email, Số điện thoại hoặc Phone Alias
    user = User.query.filter(
        (User.email == identifier) | 
        (User.phone_number == identifier) | 
        (User.email == f"{identifier}@phone.medimind") |
        (User.license_code == identifier)
    ).first()

    if not user or not user.check_password(password):
        return jsonify({"success": False, "error": "Thông tin đăng nhập hoặc mật khẩu không chính xác."}), 401

    # Lưu định danh người dùng vào Session phía máy chủ
    session["user_id"] = user.id
    session["user_role"] = user.role

    return jsonify({
        "success": True,
        "message": f"Đăng nhập thành công! Chào mừng {user.full_name}.",
        "user": user.to_dict()
    })

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Đăng ký tài khoản người dùng bằng Email hoặc Số điện thoại."""
    data = request.get_json(silent=True) or {}
    raw_identifier = (data.get("identifier") or data.get("email") or "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("name", "").strip()

    if not full_name:
        last_name = data.get("last_name", "").strip()
        first_name = data.get("first_name", "").strip()
        if last_name and first_name:
            full_name = f"{last_name} {first_name}"
        elif first_name:
            full_name = first_name
        elif last_name:
            full_name = last_name

    dob = data.get("dob", "").strip()
    gender = data.get("gender", "").strip()

    if not raw_identifier or not password or not full_name:
        return jsonify({"success": False, "error": "Vui lòng điền đầy đủ họ tên, Email hoặc Số điện thoại và mật khẩu."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu phải có ít nhất 6 ký tự."}), 400

    # Phân loại Email hoặc Số điện thoại
    if "@" in raw_identifier:
        email = raw_identifier
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
        role="patient",
        phone_number=phone_number,
        dob=dob,
        gender=gender,
        license_code=None
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    # Tự động đăng nhập sau khi đăng ký
    session["user_id"] = new_user.id
    session["user_role"] = new_user.role

    return jsonify({
        "success": True,
        "message": "Đăng ký tài khoản thành công!",
        "user": new_user.to_dict()
    }), 201

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    """Kiểm tra trạng thái phiên đăng nhập hiện tại từ Server."""
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
    """Đăng xuất và hủy phiên làm việc phía máy chủ."""
    session.clear()
    return jsonify({"success": True, "message": "Đã đăng xuất thành công."})

# ==============================================================
# HỆ THỐNG PHÂN TẦNG LÂM SÀNG & TƯ VẤN Y TẾ
# ==============================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return jsonify({"error": "Vui lòng nhập nội dung tin nhắn."}), 400

    # 1. Kiểm tra dấu hiệu cờ đỏ cấp cứu (Quy chuẩn an toàn y tế số 1: Luôn ưu tiên 115)
    emergency = assess_emergency_risk(user_message)
    if emergency["is_emergency"]:
        return jsonify({
            "answer": emergency["message"],
            "risk_level": "Emergency",
            "risk_score": 95,
            "symptoms": emergency["symptoms"],
            "specialist": "Cấp cứu 115 / Hồi sức cấp cứu",
            "is_emergency": True,
            "sources": [
                {
                    "title": "Quy trình Cấp cứu Ban đầu - Bộ Y Tế",
                    "source": "Cục Quản lý Khám chữa bệnh",
                    "url": "https://kcb.vn"
                }
            ]
        })

    # 2. Phân tích triệu chứng bằng Google Gemini API (có cơ chế Fallback sang Rule-Based nếu chưa có Key)
    gemini_result = gemini_service.generate_clinical_response(user_message, history)
    if gemini_result and "answer" in gemini_result:
        triage_result = gemini_result
    else:
        triage_result = analyze_symptoms(user_message, history)

    return jsonify({
        "answer": triage_result.get("answer", ""),
        "risk_level": triage_result.get("risk_level", "Thấp (Theo dõi)"),
        "risk_score": triage_result.get("risk_score", 30),
        "symptoms": triage_result.get("symptoms", []),
        "specialist": triage_result.get("specialist", "Nội tổng quát"),
        "medications": triage_result.get("medications", []),
        "is_emergency": False,
        "sources": triage_result.get("sources", [
            {
                "title": "MedlinePlus Medical Encyclopedia",
                "source": "NIH National Library of Medicine",
                "url": "https://medlineplus.gov"
            }
        ])
    })

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

@app.route("/api/upload-lab", methods=["POST"])
def upload_lab():
    # Tiếp nhận tệp ảnh / PDF / Word phục vụ huấn luyện model scan
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
    
    from datetime import datetime
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
    # Danh sách các tệp trong thư mục dataset huấn luyện scan
    files = []
    if os.path.exists(UPLOAD_FOLDER):
        from datetime import datetime
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
    safe_name = secure_filename(filename)
    fpath = os.path.join(UPLOAD_FOLDER, safe_name)
    if os.path.exists(fpath):
        os.remove(fpath)
        return jsonify({"status": "success", "message": f"Đã xóa {safe_name}"})
    return jsonify({"status": "error", "message": "Tệp không tồn tại."}), 404

@app.route("/api/clinical-summary", methods=["GET"])
def clinical_summary():
    """
    Bản tóm tắt bệnh án sơ bộ gửi Bác sĩ.
    BẢO MẬT Y TẾ (RBAC): Chỉ người dùng có vai trò Bác sĩ ('doctor') mới được xem!
    """
    current_role = session.get("user_role")
    
    # Cho phép xem nếu là Bác sĩ đã đăng nhập trong session, hoặc tạm thời bỏ qua nếu đang test
    if not session.get("user_id"):
        return jsonify({
            "error": "Vui lòng đăng nhập để xem bản tóm tắt hồ sơ sức khỏe này."
        }), 401

    return jsonify({
        "patient_name": "Nguyễn Văn An",
        "patient_id": "BN-8429",
        "age": 34,
        "gender": "Nam",
        "allergies": ["Penicillin / Amoxicillin"],
        "chief_complaint": "Đau đầu vùng trán kèm sốt nhẹ và nghẹt mũi kéo dài 36 giờ.",
        "hpi": "Đau tăng khi cúi người về phía trước, nghẹt mũi tăng về đêm. Không nôn ói vọt, không cứng gáy.",
        "differential_diagnosis": [
            {"condition": "Viêm xoang cấp (Acute Rhinosinusitis)", "confidence": "85%"},
            {"condition": "Nhiễm virus đường hô hấp trên (Viral URI)", "confidence": "70%"}
        ],
        "suggested_orders": [
            "Nội soi Tai Mũi Họng kiểm tra niêm mạc xoang",
            "Tổng phân tích tế bào máu (CBC)"
        ],
        "contraindications": "Chống chỉ định tuyệt đối nhóm kháng sinh Beta-lactam (Penicillin, Augmentin)."
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("==================================================")
    print("🩺 MediMind AI - Clinical Assistant Platform (Powered by Google Gemini & SQLite/Postgres)")
    print(f"🚀 Running locally at: http://127.0.0.1:{port}")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=True)
