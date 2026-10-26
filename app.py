import os
import sys

# Ensure UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify
from core.triage import analyze_symptoms, assess_emergency_risk

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return jsonify({"error": "Vui lòng nhập nội dung tin nhắn."}), 400

    # 1. Kiểm tra dấu hiệu cờ đỏ cấp cứu
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

    # 2. Phân tích triệu chứng & Phân tầng Triage
    triage_result = analyze_symptoms(user_message, history)

    return jsonify({
        "answer": triage_result["answer"],
        "risk_level": triage_result["risk_level"],
        "risk_score": triage_result["risk_score"],
        "symptoms": triage_result["symptoms"],
        "specialist": triage_result["specialist"],
        "medications": triage_result.get("medications", []),
        "is_emergency": False,
        "sources": triage_result["sources"]
    })

@app.route("/api/upload-lab", methods=["POST"])
def upload_lab():
    # Giả lập tiếp nhận và phân tích kết quả xét nghiệm / đơn thuốc
    # Trong giai đoạn tích hợp AWS, file này sẽ được đẩy lên Amazon S3 qua boto3
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
    # Tóm tắt bệnh án sơ bộ gửi Bác sĩ
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
    print("🩺 MediMind AI - Clinical Assistant Platform")
    print(f"🚀 Running locally at: http://127.0.0.1:{port}")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=True)
