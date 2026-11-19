"""
================================================================================
🧪 BỘ KIỂM THỬ LÂM SÀNG: INTAKE SERVICE & PRE-VISIT SUMMARY (MỤC 10)
================================================================================
Kiểm tra các tiêu chí nghiệm thu nghiêm ngặt:
  1. Trích xuất đúng triệu chứng có và triệu chứng ĐÃ PHỦ NHẬN (không bị đảo lộn).
  2. Bắt đúng thời gian diễn tiến và thân nhiệt tự đo.
  3. Chọn câu hỏi tiếp theo từ dữ kiện còn thiếu, không hỏi lặp.
  4. Tạo bản tóm tắt trước khám 2 phần (Phần A & B) không chứa điểm số 0-100 giả lập.
  5. Sửa đổi dữ kiện làm tăng số phiên bản và yêu cầu xác nhận lại.
  6. Xử lý cờ đỏ cấp cứu ưu tiên hàng đầu.
================================================================================
"""

import pytest
from core.intake_service import (
    extract_clinical_facts_from_text,
    identify_missing_information,
    select_next_question,
    generate_pre_visit_summary,
    IntakeSessionManager
)


def test_fact_extraction_with_negation():
    """Kiểm thử 1: Nhận diện chính xác triệu chứng khẳng định và triệu chứng đã phủ nhận."""
    text = "Tôi bị sốt nhẹ và đau rát họng hai hôm nay, nuốt đau nhưng không khó thở và không tức ngực."
    facts = extract_clinical_facts_from_text(text)

    # Có sốt và đau họng
    present = facts["present_symptoms"]
    assert any("Sốt" in s for s in present)
    assert any("Đau rát họng" in s for s in present)

    # Đã phủ nhận khó thở và tức ngực
    denied = facts["denied_symptoms"]
    assert any("Khó thở" in s for s in denied)
    assert any("Đau tức ngực" in s for s in denied)

    # Khó thở và tức ngực KHÔNG được xuất hiện trong present_symptoms
    assert not any("Khó thở" in s for s in present)
    assert not any("Đau tức ngực" in s for s in present)

    # Thời gian diễn tiến
    assert facts["duration"] is not None
    assert "hai hôm" in facts["duration"] or "hôm" in facts["duration"]


def test_vitals_temperature_extraction():
    """Kiểm thử 2: Bắt đúng thân nhiệt tự đo tại nhà."""
    text = "Bé sốt 38.5 độ C từ chiều qua, có ho khan."
    facts = extract_clinical_facts_from_text(text)

    assert facts["vitals"].get("temperature") == "38.5°C"
    assert any("Ho" in s for s in facts["present_symptoms"])


def test_missing_information_detection():
    """Kiểm thử 3: Nhận diện dữ kiện còn thiếu để hỏi tiếp."""
    # Chỉ khai bị đau họng, chưa nói thời gian, chưa đo thân nhiệt, chưa phủ nhận cờ đỏ
    facts = {
        "present_symptoms": ["Đau rát họng / Nuốt đau"],
        "denied_symptoms": [],
        "duration": None,
        "vitals": {}
    }

    missing = identify_missing_information(facts)
    assert len(missing) > 0
    # Cần hỏi thời gian
    assert any("Thời gian" in m for m in missing)
    # Cần hỏi về cờ đỏ khó thở
    assert any("khó thở" in m for m in missing)

    # Chọn câu hỏi tiếp theo
    next_q = select_next_question(missing, turn_count=1)
    assert next_q is not None
    assert "bệnh sử" in next_q or "khi nào" in next_q


def test_complete_intake_workflow_and_summary():
    """Kiểm thử 4: Vận hành toàn bộ quy trình: Khai báo -> Hỏi bổ sung -> Sửa đổi -> Xác nhận -> Tóm tắt 2 phần."""
    manager = IntakeSessionManager()
    cid = "test_conv_respiratory_01"

    # Lượt 1: Người bệnh khai ban đầu
    res1 = manager.process_message(cid, "Tôi bị đau rát họng nuốt đau từ 2 ngày nay", guest_token="test-clinical-guest")
    assert res1["status"] == "collecting"
    assert res1["next_question"] is not None
    facts1 = res1["facts"]
    assert facts1["duration"] == "2 ngày nay"

    # Lượt 2: Người bệnh trả lời bổ sung (phủ nhận khó thở, báo có sốt 38.2C)
    res2 = manager.process_message(cid, "Tôi có cặp nhiệt độ thấy sốt 38.2 độ, không khó thở và không tức ngực gì cả", guest_token="test-clinical-guest")
    facts2 = res2["facts"]
    assert facts2["vitals"]["temperature"] == "38.2°C"
    assert any("Khó thở" in s for s in facts2["denied_symptoms"])

    # Kiểm tra bản tóm tắt sơ bộ
    summary = res2["summary"]
    part_a = summary["part_a_patient_facts"]
    part_b = summary["part_b_system_assessment"]

    # Phần A: Thông tin người bệnh
    assert part_a["duration"] == "2 ngày nay"
    assert "38.2°C" in part_a["vitals"]
    assert any("Khó thở" in s for s in part_a["symptoms_denied"])

    # Phần B: Đánh giá hệ thống
    assert part_b["triage_badge"] == "collecting"
    assert part_b["recommended_specialist"] == "Chưa xác định"
    assert part_b["sources"] == []
    # TUYỆT ĐỐI KHÔNG có trường risk_score kiểu 0-100% giả mạo
    assert "risk_score" not in part_b
    assert "score" not in part_b

    # Sửa đổi một dữ kiện (vd: sửa thời gian diễn tiến từ 2 ngày thành 4 ngày)
    up_res = manager.update_fact(cid, "duration", "4 ngày", guest_token="test-clinical-guest")
    assert up_res["facts"]["duration"] == "4 ngày"
    assert up_res["summary"]["version"] == 2  # Tăng phiên bản
    assert up_res["summary"]["is_confirmed"] is False  # Cần xác nhận lại

    # Bệnh nhân xác nhận lời khai
    confirm_res = manager.confirm_summary(cid, guest_token="test-clinical-guest")
    assert confirm_res["status"] == "confirmed"
    assert confirm_res["is_confirmed"] is True
    assert "Đã được người bệnh xác nhận lời khai" in confirm_res["summary"]["part_b_system_assessment"]["confirmation_status"]


def test_emergency_bypass_in_intake():
    """Kiểm thử 5: Khi xuất hiện dấu hiệu nguy kịch, lập tức chuyển chế độ cấp cứu."""
    manager = IntakeSessionManager()
    cid = "test_conv_emergency_01"

    res = manager.process_message(cid, "Tôi bị đau thắt ngực dữ dội, khó thở và vã mồ hôi", guest_token="test-clinical-guest")
    assert res["status"] == "emergency"
    assert res["next_question"] is None
    assert "đánh giá trực tiếp khẩn" in res["answer"].lower()
    assert "115" not in res["answer"]
    assert "cấp cứu" in res["summary"]["part_b_system_assessment"]["triage_status"].lower()


def test_summary_uses_only_verified_final_assessment_and_invalidates_on_edit(test_app):
    manager = IntakeSessionManager()
    cid = "test_verified_intake_snapshot"
    guest = "test-clinical-guest"
    initial = manager.process_message(cid, "Tôi mệt từ hôm qua", guest_token=guest)
    assert initial["summary_available"] is True
    assert initial["summary"]["part_a_patient_facts"]["allergies"] == "Chưa rõ tiền sử dị ứng"
    assessment = {
        "consultation_mode": "final", "degraded": False, "risk_level": "Đánh giá tham khảo",
        "specialist": "Y học gia đình", "grounding_status": "insufficient",
        "sources": [{"title": "Nguồn kiểm tra", "url": "https://medlineplus.gov/"}],
    }
    manager.record_assistant_reply(cid, "Đánh giá trong cuộc hội thoại.", guest_token=guest, assessment=assessment)
    assert manager.get_summary(cid, guest_token=guest)["part_b_system_assessment"]["sources"] == []

    manager.process_message(cid, "Vậy tôi nên làm gì?", guest_token=guest)
    assessment["grounding_status"] = "verified"
    manager.record_assistant_reply(cid, "Đánh giá trong cuộc hội thoại.", guest_token=guest, assessment=assessment)
    reopened = IntakeSessionManager().get_summary(cid, guest_token=guest)["part_b_system_assessment"]
    assert reopened["recommended_specialist"] == "Y học gia đình"
    assert reopened["sources"] == assessment["sources"]

    updated = manager.update_fact(cid, "duration", "Hôm nay", guest_token=guest)
    assert updated["summary"]["part_b_system_assessment"]["triage_badge"] == "collecting"
    assert updated["summary"]["part_b_system_assessment"]["sources"] == []


def test_unowned_missing_summary_does_not_create_a_draft(test_app):
    manager = IntakeSessionManager()
    with pytest.raises(KeyError):
        manager.get_summary("missing_intake_draft", guest_token="test-clinical-guest")
    from core.models import IntakeSessionRecord
    with test_app.app_context():
        assert IntakeSessionRecord.query.filter_by(conversation_id="missing_intake_draft").first() is None


def test_attachment_summary_matches_after_reload(test_app):
    manager = IntakeSessionManager()
    cid = "test_intake_attachment_summary"
    guest = "test-clinical-guest"
    initial = manager.process_message(cid, "", image_bytes=b"photo fixture", guest_token=guest)
    reopened = IntakeSessionManager().get_summary(cid, guest_token=guest)
    assert reopened["part_a_patient_facts"] == initial["summary"]["part_a_patient_facts"]


def test_delayed_assessment_cannot_overwrite_a_new_turn(test_app):
    manager = IntakeSessionManager()
    cid = "test_delayed_intake_assessment"
    guest = "test-clinical-guest"
    first = manager.process_message(cid, "Tôi đau bụng", guest_token=guest)
    second = manager.process_message(cid, "Tôi đau quanh rốn", guest_token=guest)
    with pytest.raises(ValueError):
        manager.record_assistant_reply(cid, "Phản hồi bị chậm", guest_token=guest,
                                       expected_turn_count=first["turn_count"])
    updated = manager.record_assistant_reply(cid, "Phản hồi đúng lượt", guest_token=guest,
                                             expected_turn_count=second["turn_count"])
    assert updated["messages"][-1]["content"] == "Phản hồi đúng lượt"



def test_negation_removes_from_present_symptoms():
    """Kiểm thử 6: Lời phủ nhận sau đó phải gỡ bỏ triệu chứng khỏi present_symptoms."""
    manager = IntakeSessionManager()
    cid = "test_conv_negation_override"

    # Lượt 1: Báo có sốt
    res1 = manager.process_message(cid, "Tôi bị sốt cao từ tối qua", guest_token="test-clinical-guest")
    assert any("Sốt" in s for s in res1["facts"]["present_symptoms"])
    assert not any("Sốt" in s for s in res1["facts"]["denied_symptoms"])

    # Lượt 2: Báo đã hết sốt (phủ nhận triệu chứng đã có trước đó)
    res2 = manager.process_message(cid, "Tôi đã uống thuốc và nay đã hết sốt rồi, không còn sốt nữa, chỉ còn đau họng", guest_token="test-clinical-guest")
    facts2 = res2["facts"]

    # Sốt PHẢI bị xóa khỏi present_symptoms và chuyển sang denied_symptoms
    assert not any("Sốt" in s for s in facts2["present_symptoms"])
    assert any("Sốt" in s for s in facts2["denied_symptoms"])
    assert any("Đau rát họng" in s for s in facts2["present_symptoms"])


def test_greeting_not_chief_complaint():
    """Kiểm thử 7: Lời chào mở đầu không bị gán nhầm thành lý do khám bệnh (chief_complaint)."""
    manager = IntakeSessionManager()
    cid = "test_conv_greeting"

    # Gửi lời chào đơn thuần
    res1 = manager.process_message(cid, "Xin chào bác sĩ ạ!", guest_token="test-clinical-guest")
    # Lý do khám KHÔNG được là "Xin chào bác sĩ ạ!"
    assert res1["facts"]["chief_complaint"] == "" or "chào" not in res1["facts"]["chief_complaint"].lower()

    # Tin nhắn thứ 2 mô tả bệnh thực sự
    res2 = manager.process_message(cid, "Tôi bị ho có đờm và nghẹt mũi 3 hôm nay", guest_token="test-clinical-guest")
    assert res2["facts"]["chief_complaint"] != ""
    assert "chào" not in res2["facts"]["chief_complaint"].lower()
    assert any(w in res2["facts"]["chief_complaint"].lower() for w in ["ho", "nghẹt", "mũi"])


def test_new_message_invalidates_old_confirmation():
    """Kiểm thử 8: Tin nhắn mới mang dữ kiện phải tự động hủy xác nhận cũ và tăng số phiên bản."""
    manager = IntakeSessionManager()
    cid = "test_conv_reconfirm"

    # Tạo phiên và xác nhận
    manager.process_message(cid, "Tôi bị đau họng từ 3 ngày nay", guest_token="test-clinical-guest")
    conf1 = manager.confirm_summary(cid, guest_token="test-clinical-guest")
    assert conf1["is_confirmed"] is True
    assert conf1["summary"]["version"] == 1

    # Người bệnh nhắn thêm triệu chứng mới sau khi đã xác nhận
    res2 = manager.process_message(cid, "Ngoài ra tôi có sốt 38 độ C nữa", guest_token="test-clinical-guest")
    assert res2["summary"]["is_confirmed"] is False  # ĐÃ TỰ ĐỘNG HỦY XÁC NHẬN CŨ
    assert res2["summary"]["version"] == 2  # ĐÃ TĂNG PHIÊN BẢN


def test_informational_query_does_not_pollute_complaint():
    """Kiểm thử: Câu hỏi tra cứu định nghĩa 'Đau đầu là gì?' không bị gán nhầm thành lý do khám của người dùng."""
    manager = IntakeSessionManager()
    cid = "test_info_query_001"

    # Người dùng hỏi câu hỏi tra cứu kiến thức
    res1 = manager.process_message(cid, "Đau đầu là gì?", guest_token="test-clinical-guest")
    assert "Đau đầu / Nặng đầu" not in res1["facts"]["present_symptoms"]
    assert res1["facts"]["chief_complaint"] == ""

    # Hỏi câu tra cứu khác
    res2 = manager.process_message(cid, "Sốt xuất huyết có lây không?", guest_token="test-clinical-guest")
    assert "Sốt / Thân nhiệt tăng" not in res2["facts"]["present_symptoms"]
    assert res2["facts"]["chief_complaint"] == ""

    # Chỉ khi người dùng khai báo triệu chứng bản thân
    res3 = manager.process_message(cid, "Tôi bị đau đầu 2 ngày nay", guest_token="test-clinical-guest")
    assert "Đau đầu / Nặng đầu" in res3["facts"]["present_symptoms"]
    assert "Đau đầu" in res3["facts"]["chief_complaint"]


def test_confirm_summary_failure_on_db_error():
    """Kiểm thử: Khi ghi DB thất bại, confirm_summary không được trả trạng thái thành công và phải rollback RAM state."""
    manager = IntakeSessionManager()
    cid = "test_db_fail_001"

    # Tạo phiên và chuẩn bị dữ kiện
    manager.process_message(cid, "Tôi bị ho và đau họng 3 ngày", guest_token="test-clinical-guest")

    # Giả lập lỗi ghi database
    def faulty_save(session_data, raise_on_error=False):
        return False

    manager._save_to_db = faulty_save

    res = manager.confirm_summary(cid, guest_token="test-clinical-guest")
    assert res["success"] is False
    assert res["status"] != "confirmed"
    assert res["is_confirmed"] is False
    assert manager._sessions[cid]["is_confirmed"] is False
