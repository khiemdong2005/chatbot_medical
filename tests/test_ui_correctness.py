"""
================================================================================
🩺 MEDIMIND CLINICAL AI - UI CORRECTNESS & CONTRACT REGRESSION TEST SUITE
================================================================================
Kiểm thử tự động cho 4 vấn đề UI/Contract nghiêm trọng:
  1. Fix False Emergency Mapping (Phân biệt rõ ràng Emergency vs High Risk)
  2. Remove Fabricated Prescription Data (Loại bỏ triệt để dữ liệu bịa đặt trong đơn thuốc)
  3. Fix System Dashboard 0% -> 100% Bug (Hiển thị chính xác 0.0% khi tỷ lệ thành công là 0)
  4. Restore FastAPI Chat <-> Intake Contract (Bảo đảm contract đầy đủ giữa FastAPI và Live Intake)
================================================================================
"""

import json
import re
from pathlib import Path
import pytest
from unittest.mock import Mock
from starlette.testclient import TestClient

from core.main_fastapi import app as fastapi_app
from core.chat_service import execute_chat_workflow
from core.intake_service import intake_service
import app as flask_module


# ==============================================================================
# 1. TEST FALSE EMERGENCY MAPPING (Tách biệt Emergency vs High Risk)
# ==============================================================================

def test_triage_panel_emergency_vs_high_risk_logic():
    """Xác nhận logic triage panel trong static/js/app.js không suy diễn emergency chỉ từ risk_score >= 70."""
    app_js_path = Path("static/js/app.js")
    assert app_js_path.exists(), "File static/js/app.js phải tồn tại"
    content = app_js_path.read_text(encoding="utf-8")

    # Kiểm tra hàm updateTriagePanel
    match = re.search(r"function updateTriagePanel\(data\)\s*\{([\s\S]*?)\n\}", content)
    assert match, "Hàm updateTriagePanel phải tồn tại trong app.js"
    fn_body = match.group(1)

    # Không được chứa điều kiện gộp: (data.is_emergency || score >= 70)
    assert "data.is_emergency || score >= 70" not in fn_body, (
        "LỖI: updateTriagePanel vẫn đang gộp is_emergency với score >= 70!"
    )

    # Phải có nhánh riêng cho isEmergency và isHighRisk
    assert "isEmergency" in fn_body or "data.is_emergency" in fn_body
    assert "Cảnh báo cấp cứu khẩn cấp" in fn_body
    assert "Nguy cơ cao" in fn_body or "Khám chuyên khoa sớm" in fn_body


def test_session_badge_emergency_vs_high_risk_badge():
    """Xác nhận lưu session trong app.js chỉ gắn badge rose khi isEmergency=True, amber khi High Risk."""
    app_js_path = Path("static/js/app.js")
    content = app_js_path.read_text(encoding="utf-8")

    match = re.search(r"function saveOrUpdateCurrentSession\b[\s\S]*?\{([\s\S]*?)\n\}", content)
    assert match, "Hàm saveOrUpdateCurrentSession phải tồn tại"
    fn_body = match.group(1)

    # Không được gộp isEmergency || riskScore >= 70 vào badge rose
    assert "isEmergency || riskScore >= 70" not in fn_body, (
        "LỖI: saveOrUpdateCurrentSession vẫn gộp isEmergency || riskScore >= 70 vào rose badge!"
    )


# ==============================================================================
# 2. TEST REMOVE FABRICATED PRESCRIPTION DATA (Loại bỏ dữ liệu đơn thuốc bịa đặt)
# ==============================================================================

def test_no_fabricated_prescription_data_in_app_js():
    """Xác nhận static/js/app.js không còn chứa các giá trị fallback lâm sàng bịa đặt."""
    app_js_path = Path("static/js/app.js")
    content = app_js_path.read_text(encoding="utf-8")

    # 1. Không còn hardcoded 98.5% confidence
    assert "98.5" not in content, "LỖI: app.js vẫn còn chứa hardcoded 98.5% confidence!"

    # 2. Không còn hardcoded K29.1
    assert "K29.1" not in content, "LỖI: app.js vẫn còn chứa hardcoded mã chẩn đoán K29.1!"

    # 3. Không còn hardcoded '3 lần / ngày' làm default cho mọi thuốc
    assert "3 lần / ngày" not in content, "LỖI: app.js vẫn còn chứa hardcoded '3 lần / ngày'!"

    # 4. Không còn hardcoded '60 viên (Đủ 30 ngày)'
    assert "60 viên (Đủ 30 ngày)" not in content, "LỖI: app.js vẫn còn chứa hardcoded '60 viên (Đủ 30 ngày)'!"

    # 5. Khớp chuẩn ICD-10 chỉ xuất hiện có điều kiện (kèm biến icdCode)
    match_icd = re.search(r"✓ Khớp chuẩn ICD-10", content)
    if match_icd:
        # Nếu có chuỗi này thì phải nằm trong điều kiện template ${icdCode ? ...}
        assert "${icdCode ?" in content, "LỖI: Badge 'Khớp chuẩn ICD-10' không được bọc trong điều kiện tồn tại mã ICD-10!"


# ==============================================================================
# 3. TEST SYSTEM DASHBOARD 0% BUG (Hiển thị chuẩn 0.0% thay vì 100.0%)
# ==============================================================================

def test_system_dashboard_zero_percent_handling():
    """Xác nhận template system_dashboard.html dùng nullish check cho success_rate_pct thay vì falsy || 100."""
    tpl_path = Path("templates/system_dashboard.html")
    assert tpl_path.exists(), "Template templates/system_dashboard.html phải tồn tại"
    content = tpl_path.read_text(encoding="utf-8")

    # Không được chứa falsy fallback (ai.success_rate_pct || 100)
    assert "ai.success_rate_pct || 100" not in content, (
        "LỖI: Dashboard vẫn dùng (ai.success_rate_pct || 100) khiến 0% biến thành 100%!"
    )
    assert "rag.success_rate_pct || 100" not in content, (
        "LỖI: Dashboard vẫn dùng (rag.success_rate_pct || 100) khiến 0% biến thành 100%!"
    )

    # Kiểm tra logic xử lý JavaScript mô phỏng
    def format_rate(rate):
        val = rate if rate is not None else 100
        return f"{val:.1f}%"

    assert format_rate(0.0) == "0.0%", "0.0 phải được format thành '0.0%'"
    assert format_rate(100.0) == "100.0%", "100.0 phải được format thành '100.0%'"
    assert format_rate(None) == "100.0%", "None phải được fallback thành '100.0%'"


# ==============================================================================
# 4. TEST FASTAPI CHAT <-> INTAKE CONTRACT (Khôi phục contract đầy đủ cho Live Intake)
# ==============================================================================

def test_fastapi_chat_returns_intake_contract(monkeypatch):
    """Xác nhận FastAPI /api/chat trả về đầy đủ conversation_id, intake, intake_facts, intake_summary, history_saved."""
    test_conv_id = "conv_test_intake_12345"

    fastapi_client = TestClient(fastapi_app)
    req_body = {
        "message": "Tôi bị đau dạ dày dữ dội từ sáng nay",
        "conversation_id": test_conv_id,
        "history": [],
        "lang": "vi"
    }

    res = fastapi_client.post("/api/chat", json=req_body)
    assert res.status_code == 200, f"FastAPI chat endpoint trả mã {res.status_code}: {res.text}"
    data = res.json()

    # Kiểm tra contract bắt buộc cho Live Intake
    assert data.get("conversation_id") == test_conv_id, "FastAPI phải trả về đúng conversation_id"
    assert "intake" in data, "FastAPI phải trả về trường 'intake'"
    assert isinstance(data["intake"], dict), "'intake' phải là một dictionary"
    assert "facts" in data["intake"], "'intake' phải chứa 'facts'"
    assert "intake_facts" in data, "FastAPI phải trả về trường 'intake_facts'"
    assert "intake_summary" in data, "FastAPI phải trả về trường 'intake_summary'"
    assert data.get("history_saved") is True, "FastAPI phải trả về history_saved=True"

    # Kiểm tra các trường lâm sàng cơ bản
    assert "answer" in data
    assert "is_emergency" in data
    assert "risk_score" in data
    assert "sources" in data


def test_flask_and_fastapi_intake_contract_parity(client):
    """Xác nhận cả Flask và FastAPI đều trả về contract đồng nhất khi gửi kèm conversation_id."""
    test_conv_id_flask = "conv_parity_flask_998877"
    test_conv_id_fastapi = "conv_parity_fastapi_998877"
    payload_flask = {
        "message": "Tôi bị sốt 38.5 độ và ho có đờm",
        "conversation_id": test_conv_id_flask,
        "history": [],
        "lang": "vi"
    }
    payload_fastapi = {
        "message": "Tôi bị sốt 38.5 độ và ho có đờm",
        "conversation_id": test_conv_id_fastapi,
        "history": [],
        "lang": "vi"
    }

    # 1. Gọi Flask
    flask_res = client.post("/api/chat", json=payload_flask)
    assert flask_res.status_code == 200
    flask_data = flask_res.get_json()

    # 2. Gọi FastAPI
    fastapi_client = TestClient(fastapi_app)
    fastapi_res = fastapi_client.post("/api/chat", json=payload_fastapi)
    assert fastapi_res.status_code == 200
    fastapi_data = fastapi_res.json()

    # 3. Đối chiếu Contract giữa cả 2 backend
    intake_keys = [
        "conversation_id",
        "intake",
        "intake_facts",
        "intake_summary",
        "intake_status",
        "history_saved",
        "answer",
        "risk_level",
        "is_emergency"
    ]

    for k in intake_keys:
        assert k in flask_data, f"Flask thiếu trường contract: {k}"
        assert k in fastapi_data, f"FastAPI thiếu trường contract: {k}"

    assert flask_data["conversation_id"] == test_conv_id_flask
    assert fastapi_data["conversation_id"] == test_conv_id_fastapi
    assert flask_data["history_saved"] is True
    assert fastapi_data["history_saved"] is True
