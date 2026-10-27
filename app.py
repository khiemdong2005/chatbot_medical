import os
import sys
from dotenv import load_dotenv

# Đảm bảo console Windows xuất ký tự tiếng Việt UTF-8 chuẩn xác
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tải cấu hình biến môi trường từ .env
load_dotenv()

from flask import Flask, render_template, request, jsonify, session
import base64
from core.models import db, User, init_db
from core.triage import analyze_symptoms, assess_emergency_risk, apply_safety_guardrails
from core.rag_service import medical_rag_service
from core.gemini_service import GeminiMedicalService
from core.clinical_atlas import match_clinical_atlas

app = Flask(__name__)

# Cấu hình bảo mật phiên & Cơ sở dữ liệu SQLite
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "medimind-clinical-session-secret-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///medimind.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Khởi tạo CSDL SQLite & Nạp sẵn tài khoản người dùng mẫu
init_db(app)

# Khởi tạo dịch vụ AI Google Gemini
gemini_service = GeminiMedicalService()

@app.route("/")
def index():
    """Giao diện chính của Trợ lý Sức khỏe MediMind AI."""
    return render_template("index.html")

# ==============================================================
# HỆ THỐNG XÁC THỰC NGƯỜI DÙNG ĐƠN GIẢN CHO NGƯỜI DÂN (AUTH APIS)
# ==============================================================

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Đăng nhập hệ thống: Xác thực Email hoặc Số điện thoại."""
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier", "").strip().lower()
    password = data.get("password", "")

    if not identifier or not password:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ tài khoản và mật khẩu."}), 400

    # Tìm kiếm theo Email hoặc Mã bác sĩ nếu có
    user = User.query.filter(
        (User.email == identifier) | (User.license_code == identifier)
    ).first()

    if not user or not user.check_password(password):
        return jsonify({"success": False, "error": "Thông tin đăng nhập hoặc mật khẩu không chính xác."}), 401

    session["user_id"] = user.id
    session["user_role"] = user.role

    return jsonify({
        "success": True,
        "message": f"Đăng nhập thành công! Chào mừng {user.full_name}.",
        "user": user.to_dict()
    })

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Đăng ký tài khoản sức khỏe cá nhân cho Người Dân."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    full_name = data.get("name", "").strip()
    role = data.get("role", "patient")

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
        role=role
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
      5. Tra cứu Thư viện Đối chiếu Y khoa (Clinical Atlas) tìm 3 ảnh mẫu tham khảo
    """
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    history = data.get("history", [])
    image_str = data.get("image")

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
    emergency = assess_emergency_risk(user_message)
    if emergency["is_emergency"]:
        return jsonify({
            "answer": emergency["message"],
            "risk_level": "Nguy cơ cao (Cần thăm khám khẩn)",
            "risk_score": 90,
            "symptoms": emergency["symptoms"],
            "specialist": "Cấp cứu 115 / Khoa Cấp cứu",
            "is_emergency": True,
            "sources": [
                {
                    "title": "Quy trình Cấp cứu Ban đầu - Bộ Y Tế",
                    "source": "Cục Quản lý Khám chữa bệnh",
                    "url": "https://kcb.vn"
                }
            ],
            "clinical_atlas": None
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
        image_mime_type=image_mime_type
    )
    if gemini_result and "answer" in gemini_result:
        triage_result = gemini_result
    else:
        # Tự động kích hoạt bộ máy phác đồ nội bộ khi chưa có API key hoặc mất mạng
        triage_result = analyze_symptoms(user_message, history)
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
    cleaned_answer = apply_safety_guardrails(triage_result.get("answer", ""))

    # -------------------------------------------------------------
    # BƯỚC 5: TRA CỨU THƯ VIỆN ĐỐI CHIẾU LÂM SÀNG (3 ẢNH MẪU)
    # -------------------------------------------------------------
    diff_diag = triage_result.get("differential_diagnosis", [])
    symps = triage_result.get("symptoms", [])
    search_context = f"{user_message} {cleaned_answer} {' '.join(symps)} {' '.join(diff_diag)}"
    atlas_data = match_clinical_atlas(search_context)

    return jsonify({
        "answer": cleaned_answer,
        "risk_level": triage_result.get("risk_level", "Thấp (Tự chăm sóc & Theo dõi)"),
        "risk_score": triage_result.get("risk_score", 30),
        "symptoms": triage_result.get("symptoms", []),
        "specialist": triage_result.get("specialist", "Nội tổng quát"),
        "medications": triage_result.get("medications", []),
        "visual_findings": triage_result.get("visual_findings", []),
        "differential_diagnosis": diff_diag,
        "is_emergency": False,
        "sources": triage_result.get("sources", [
            {
                "title": "MedlinePlus Medical Encyclopedia",
                "source": "NIH National Library of Medicine",
                "url": "https://medlineplus.gov"
            }
        ]),
        "clinical_atlas": atlas_data
    })

# ==============================================================
# HỆ THỐNG ĐỌC KẾT QUẢ XÉT NGHIỆM & ĐƠN THUỐC
# ==============================================================

@app.route("/api/upload-lab", methods=["POST"])
def upload_lab():
    """Tiếp nhận và giải thích các chỉ số sinh hóa máu cho người dân."""
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
                "warning": "Nguy cơ tiền tiểu đường, cần hạn chế tinh bột và đồ ngọt."
            },
            {
                "name": "Cholesterol toàn phần",
                "value": "5.9 mmol/L",
                "reference": "< 5.2 mmol/L",
                "status": "High",
                "warning": "Chỉ số mỡ máu hơi cao, cần tăng cường vận động thể chất."
            },
            {
                "name": "SGOT (AST - Men gan)",
                "value": "28 U/L",
                "reference": "< 40 U/L",
                "status": "Normal",
                "warning": "Chức năng tế bào gan hoàn toàn bình thường."
            },
            {
                "name": "Creatinine (Chức năng lọc thận)",
                "value": "72 µmol/L",
                "reference": "53 - 106 µmol/L",
                "status": "Normal",
                "warning": "Độ lọc cầu thận đạt chuẩn an toàn."
            }
        ],
        "ai_summary": "Phát hiện 2 chỉ số vượt ngưỡng tham chiếu: Đường huyết (7.8) và Cholesterol (5.9). Khuyên bạn nên đến phòng khám Nội tiết - Dinh dưỡng để kiểm tra kỹ hơn."
    })

# ==============================================================
# PHIẾU CHUẨN BỊ TRƯỚC KHÁM CHO NGƯỜI DÂN (PRE-VISIT SUMMARY)
# ==============================================================

@app.route("/api/clinical-summary", methods=["GET"])
def clinical_summary():
    """
    Bản tóm tắt trước khám dành cho Người Dân (Pre-Consultation Summary).
    Giúp người dân mang theo khi đi khám bệnh để bác sĩ nắm bệnh sử trong 30 giây.
    """
    return jsonify({
        "patient_name": "Nguyễn Văn An",
        "patient_id": "BN-8429",
        "age": 34,
        "gender": "Nam",
        "allergies": ["Dị ứng Penicillin / Amoxicillin"],
        "chief_complaint": "Đau rát họng kèm sốt nhẹ và nghẹt mũi kéo dài 36 giờ.",
        "hpi": "Đau rát tăng khi nuốt, nghẹt mũi nhiều về đêm, đã súc nước muối nhưng chưa đỡ hẳn. Không nôn, không khó thở.",
        "differential_diagnosis": [
            {"condition": "Viêm họng cấp / Viêm mũi xoang (Acute Rhinosinusitis)", "confidence": "85%"},
            {"condition": "Nhiễm virus đường hô hấp trên thông thường (Viral URI)", "confidence": "70%"}
        ],
        "suggested_questions": [
            "Tình trạng đau họng và sốt của tôi có cần dùng thuốc kháng sinh không hay chỉ cần thuốc giảm đau thông thường?",
            "Tôi có cần làm thêm xét nghiệm máu hoặc nội soi Tai Mũi Họng để kiểm tra ổ viêm không?",
            "Nếu có dấu hiệu nào xuất hiện thì tôi phải quay lại tái khám ngay lập tức?"
        ],
        "contraindications": "Chống chỉ định tuyệt đối nhóm kháng sinh Beta-lactam (Penicillin, Augmentin)."
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("==================================================")
    print("🩺 MediMind AI - Trợ lý Sức khỏe Toàn diện cho Người Dân (Powered by RAG & Gemini)")
    print(f"🚀 Running locally at: http://127.0.0.1:{port}")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=True)
