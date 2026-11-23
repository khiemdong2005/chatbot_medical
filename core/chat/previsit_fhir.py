"""Export confirmed patient-reported intake as a self-contained FHIR R4 Bundle."""

from datetime import datetime, timezone
from uuid import uuid4


QUESTIONNAIRE_URL = "urn:uuid:a37b89e7-6ea1-4d50-94ae-0dad5ff2438f"
QUESTIONNAIRE_VERSION = "1.0.0"
HISTORY_STATUSES = {
    "reported": "Có",
    "denied": "Không",
    "unknown": "Chưa rõ",
    "skipped": "Đã bỏ qua",
}


def build_previsit_fhir_bundle(patient_facts, confirmed_facts):
    questions = []
    responses = []

    def add(link_id, label, values, *, repeat=False, options=None):
        question = {"linkId": link_id, "text": label, "type": "text"}
        if repeat:
            question["repeats"] = True
        if options:
            question["type"] = "choice"
            question["answerOption"] = [{"valueString": value} for value in options]
        questions.append(question)
        answers = [{"valueString": value.strip()} for value in values
                   if isinstance(value, str) and value.strip()]
        if answers:
            responses.append({"linkId": link_id, "text": label, "answer": answers})

    add("reason", "Lý do khám", [patient_facts.get("chief_complaint")])
    add("duration", "Thời điểm khởi phát hoặc thời gian có triệu chứng", [patient_facts.get("duration")])
    add("symptoms", "Triệu chứng người bệnh ghi nhận", patient_facts.get("present_symptoms", []), repeat=True)
    add("denied-symptoms", "Triệu chứng người bệnh cho biết không có", patient_facts.get("denied_symptoms", []), repeat=True)
    add("pain-frequency", "Tần suất đau", [patient_facts.get("pain_frequency")])
    pain = patient_facts.get("pain") or {}
    for key, label in (
        ("location", "Vị trí đau"), ("severity", "Mức độ đau"), ("quality", "Tính chất đau"),
        ("radiation", "Hướng lan của cơn đau"), ("course", "Diễn tiến đau"),
    ):
        add(f"pain-{key}", label, [pain.get(key)])
    add("activity-impact", "Ảnh hưởng đến sinh hoạt", [patient_facts.get("activity_impact")])
    vitals = patient_facts.get("vitals") or {}
    add("vitals", "Chỉ số do người bệnh tự đo", [f"{key}: {value}" for key, value in vitals.items()], repeat=True)

    history = confirmed_facts.get("patient_reported_history", {})
    for key, label in (("conditions", "Tiền sử bệnh"), ("medications", "Thuốc đang dùng"), ("allergies", "Dị ứng")):
        item = history.get(key, {})
        details = [item.get("text")] if item else patient_facts.get(key, [])
        status = item.get("status") or ("reported" if details else None)
        if key == "medications" and not status:
            status = {"yes": "reported", "no": "denied"}.get(patient_facts.get("medication_use", {}).get("status"))
        add(f"{key}-status", f"{label} – trạng thái người bệnh khai",
            [HISTORY_STATUSES.get(status)], options=HISTORY_STATUSES.values())
        add(key, f"{label} – chi tiết", details if status != "skipped" else [], repeat=True)

    add("additional", "Thông tin bổ sung đã đối soát", [
        f"{item['question']} — {item['answer']}"
        for item in confirmed_facts.get("contextual_answers", [])
        if isinstance(item, dict) and item.get("question") and item.get("answer")
    ], repeat=True)
    questionnaire = {
        "resourceType": "Questionnaire",
        "url": QUESTIONNAIRE_URL,
        "version": QUESTIONNAIRE_VERSION,
        "title": "Phiếu khai báo trước khám MediMind",
        "status": "active",
        "language": "vi",
        "subjectType": ["Patient"],
        "item": questions,
    }
    response = {
        "resourceType": "QuestionnaireResponse",
        "questionnaire": f"{QUESTIONNAIRE_URL}|{QUESTIONNAIRE_VERSION}",
        "status": "completed",
        "authored": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "item": responses,
    }
    if not responses:
        del response["item"]
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": QUESTIONNAIRE_URL, "resource": questionnaire},
            {"fullUrl": f"urn:uuid:{uuid4()}", "resource": response},
        ],
    }
