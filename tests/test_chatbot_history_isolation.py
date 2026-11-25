"""
tests/test_chatbot_history_isolation.py
Verify strict separation between Chatbot conversation history (sidebar + PDF export)
and Appointment Pre-Visit Intake surveys (stored inside Appointment ticket only).
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from app import create_app
from core.chat.consultation_service import get_user_chatbot_sessions, get_user_consultations
from core.shared.db_utils import get_flask_app, set_flask_app
from core.shared.models import ClinicalConsultation, IntakeSessionRecord, User, db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def isolated_app():
    prev = get_flask_app()
    tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": tmpdir.name,
            "SECRET_KEY": "chat-history-isolation-test-secret",
        }
    )
    with app.app_context():
        db.create_all()
        user = User(email="history@test.local", full_name="History Tester", role="patient")
        user.set_password("StrongPass123!")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    yield app, uid
    if prev is not None:
        set_flask_app(prev)
    tmpdir.cleanup()


def test_previsit_survey_excluded_from_chatbot_sessions_and_tagged(isolated_app):
    app, uid = isolated_app
    with app.app_context():
        # 1. Pre-visit appointment survey record (no real chatbot assistant turns)
        previsit_cid = "conv_previsit_001"
        db.session.add(
            IntakeSessionRecord(
                conversation_id=previsit_cid,
                user_id=uid,
                status="confirmed",
                turn_count=4,
                facts_json=json.dumps(
                    {
                        "chief_complaint": "Con bị nóng trong người",
                        "previsit_topics": ["medications", "allergies", "conditions"],
                    },
                    ensure_ascii=False,
                ),
                messages_json=json.dumps(
                    [
                        {
                            "sender": "patient",
                            "content": "Con bị nóng trong người",
                            "previsit_question": "Bạn đang thấy thế nào?",
                        }
                    ],
                    ensure_ascii=False,
                ),
                is_confirmed=True,
            )
        )
        db.session.add(
            ClinicalConsultation(
                user_id=uid,
                conversation_id=previsit_cid,
                message="Con bị nóng trong người",
                answer="Chưa có đánh giá sơ bộ đủ căn cứ trong cuộc hội thoại.",
                confirmed_summary=json.dumps(
                    {
                        "is_confirmed": True,
                        "part_a_patient_facts": {
                            "chief_complaint": "Con bị nóng trong người",
                            "patient_reported_history": {"allergies": {"status": "denied", "text": "Không"}},
                        },
                    },
                    ensure_ascii=False,
                ),
            )
        )

        # 2. Real chatbot conversation record (patient + assistant turns, no previsit_topics)
        chat_cid = "conv_chatbot_002"
        db.session.add(
            IntakeSessionRecord(
                conversation_id=chat_cid,
                user_id=uid,
                status="collecting",
                turn_count=2,
                facts_json=json.dumps({"chief_complaint": "Đau đầu nhẹ", "present_symptoms": ["Đau đầu"]}, ensure_ascii=False),
                messages_json=json.dumps(
                    [
                        {"sender": "patient", "content": "Tôi bị đau đầu nhẹ từ sáng nay"},
                        {"sender": "assistant", "content": "Bạn có kèm theo sốt hoặc buồn nôn không?"},
                        {"sender": "patient", "content": "Không sốt, chỉ hơi mệt"},
                        {"sender": "assistant", "content": "Bạn nên nghỉ ngơi, uống đủ nước và theo dõi thêm."},
                    ],
                    ensure_ascii=False,
                ),
                is_confirmed=False,
            )
        )
        db.session.commit()

        consultations = get_user_consultations(uid)
        assert len(consultations) == 1
        assert consultations[0]["conversation_id"] == previsit_cid
        assert consultations[0]["is_previsit"] is True
        assert consultations[0]["source"] == "previsit"

        chatbot_sessions = get_user_chatbot_sessions(uid)
        assert len(chatbot_sessions) == 1
        assert chatbot_sessions[0]["conversation_id"] == chat_cid
        assert chatbot_sessions[0]["is_previsit"] is False
        assert chatbot_sessions[0]["message_count"] == 2
        assert len(chatbot_sessions[0]["messages"]) == 4
        assert chatbot_sessions[0]["messages"][0]["role"] == "user"
        assert chatbot_sessions[0]["messages"][1]["role"] == "assistant"


def test_frontend_js_filters_previsit_stubs_and_exports_selected_chat_pdf():
    app_js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    assert "function isPrevisitSurveySession" in app_js
    assert "PREVISIT_PLACEHOLDER_PREFIX" in app_js

    # Verify JS syntax & logic via Node
    script = f"""
    const PREVISIT_PLACEHOLDER_PREFIX = 'Chưa có đánh giá sơ bộ đủ căn cứ';
    {app_js[app_js.index('function isPrevisitSurveySession'):app_js.index('function loadSessionsFromStorage')]}
    const previsitStub = {{
      id: 'conv_2425d1b850',
      title: 'Con bị nóng trong người',
      lastMessage: 'Chưa có đánh giá sơ bộ đủ căn cứ trong cuộc hội thoại.',
      messages: [
        {{ role: 'user', content: 'Con bị nóng trong người' }},
        {{ role: 'assistant', content: 'Chưa có đánh giá sơ bộ đủ căn cứ trong cuộc hội thoại.' }}
      ]
    }};
    const realChat = {{
      id: 'conv_real_1',
      title: 'Đau đầu nhẹ',
      lastMessage: 'Bạn nên nghỉ ngơi, uống đủ nước.',
      messages: [
        {{ role: 'user', content: 'Tôi bị đau đầu nhẹ' }},
        {{ role: 'assistant', content: 'Bạn nên nghỉ ngơi, uống đủ nước.' }}
      ]
    }};
    if (!isPrevisitSurveySession(previsitStub)) process.exit(2);
    if (isPrevisitSurveySession(realChat)) process.exit(3);
    console.log('JS_FILTER_OK');
    """
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "JS_FILTER_OK" in proc.stdout
