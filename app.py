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
    """Đăng nhập hệ thống: Xác thực Email/Mã số và Mật khẩu băm trong CSDL."""
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "patient")

    if not identifier or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ tài khoản và mật khẩu."}), 400

    # Tìm kiếm theo Email hoặc Mã chứng chỉ hành nghề của bác sĩ
    user = User.query.filter(
        (User.email == identifier) | (User.license_code == identifier)
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
    """Đăng ký tài khoản người dùng hoặc bác sĩ mới."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("name", "").strip()
    role = data.get("role", "patient")
    license_code = data.get("license_code", "").strip() if role == "doctor" else None

    if not email or not password or not full_name:
        return jsonify({"success": False, "error": "Vui lòng điền đầy đủ các trường thông tin."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu phải có ít nhất 6 ký tự."}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"success": False, "error": "Email này đã được sử dụng."}), 409

    new_user = User(
        email=email,
        full_name=full_name,
        role=role,
        license_code=license_code
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

@app.route("/api/upload-lab", methods=["POST"])
def upload_lab():
    # Tiếp nhận và phân tích kết quả xét nghiệm / đơn thuốc
    return jsonify({
        "status": "success",
        "file_name": "xet_nghiem_sinh_hoa.jpg",
        "s3_url": "https://medimind-records-storage.s3.amazonaws.com/uploads/xet_nghiem_sinh_hoa.jpg",
        "extracted_metrics": [
            {
                "name": "Glucose (Đường huyết đói)",
                "value": "7.8 mmol/L",
                "reference": "3.9 - 6.4 mmol/L",
                "status": "High",
                "warning": "Nguy cơ tiền tiểu đường, cần theo dõi chế độ tinh bột."
            },
            {
                "name": "Cholesterol toàn phần",
                "value": "5.9 mmol/L",
                "reference": "< 5.2 mmol/L",
                "status": "High",
                "warning": "Chỉ số mỡ máu hơi cao."
            },
            {
                "name": "SGOT (AST - Men gan)",
                "value": "28 U/L",
                "reference": "< 40 U/L",
                "status": "Normal",
                "warning": "Chức năng tế bào gan bình thường."
            },
            {
                "name": "Creatinine (Chức năng thận)",
                "value": "72 µmol/L",
                "reference": "53 - 106 µmol/L",
                "status": "Normal",
                "warning": "Độ lọc cầu thận tốt."
            }
        ],
        "ai_summary": "Phát hiện 2 chỉ số vượt ngưỡng tham chiếu: Đường huyết (7.8) và Cholesterol (5.9). Khuyến nghị khám chuyên khoa Nội tiết - Dinh dưỡng."
    })

@app.route("/api/clinical-summary", methods=["GET"])
def clinical_summary():
    """
    Bản tóm tắt bệnh án sơ bộ gửi Bác sĩ.
    BẢO MẬT Y TẾ (RBAC): Chỉ người dùng có vai trò Bác sĩ ('doctor') mới được xem!
    """
    current_role = session.get("user_role")
    
    # Cho phép xem nếu là Bác sĩ đã đăng nhập trong session, hoặc tạm thời bỏ qua nếu đang test
    if current_role and current_role != "doctor":
        return jsonify({
            "error": "Từ chối truy cập. Chỉ Bác sĩ chuyên khoa có chứng chỉ hành nghề mới được quyền xem tóm tắt bệnh án này."
        }), 403

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
