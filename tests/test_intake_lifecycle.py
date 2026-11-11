"""Synthetic ownership, deletion and actual-reply regressions; no patient DB."""
import json
import unittest
from flask import Flask

from core.intake_service import IntakeSessionManager, extract_clinical_facts_from_text
from core.models import db, IntakeSessionRecord, User


class IntakeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", TESTING=True)
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.manager = IntakeSessionManager()
        self.owner = User(email="synthetic-owner@example.test", full_name="Synthetic owner", password_hash="unused")
        self.other = User(email="synthetic-other@example.test", full_name="Synthetic other", password_hash="unused")
        db.session.add_all([self.owner, self.other])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_legacy_ownerless_session_cannot_be_read_or_claimed(self):
        orphan = {"user_id": None, "guest_token": None}
        for user, token in ((None, None), (None, "guest-a"), (self.owner.id, "guest-a")):
            self.assertFalse(self.manager.check_access(dict(orphan), user, token))
        db.session.add(IntakeSessionRecord(conversation_id="legacy", facts_json="{}", messages_json="[]"))
        db.session.commit()
        with self.assertRaises(PermissionError):
            self.manager.get_or_create_session("legacy", user_id=self.owner.id, guest_token="guest-a")
        self.assertIsNone(IntakeSessionRecord.query.filter_by(conversation_id="legacy").first().user_id)

    def test_matching_guest_token_can_claim_its_own_session_after_login(self):
        self.manager.get_or_create_session("guest-owned", guest_token="guest-a")
        with self.assertRaises(PermissionError):
            self.manager.get_or_create_session("guest-owned", user_id=self.other.id, guest_token="guest-b")
        claimed = self.manager.get_or_create_session("guest-owned", user_id=self.owner.id, guest_token="guest-a")
        self.assertEqual(claimed["user_id"], self.owner.id)
        self.assertEqual(IntakeSessionRecord.query.filter_by(conversation_id="guest-owned").first().user_id, self.owner.id)

    def test_delete_removes_owned_persistent_and_cached_session(self):
        self.manager.get_or_create_session("owned", user_id=self.owner.id, guest_token="guest-a")
        with self.assertRaises(PermissionError):
            self.manager.delete_session("owned", user_id=self.other.id, guest_token="guest-a")
        self.assertTrue(self.manager.delete_session("owned", user_id=self.owner.id))
        self.assertNotIn("owned", self.manager._sessions)
        self.assertIsNone(IntakeSessionRecord.query.filter_by(conversation_id="owned").first())
        self.assertFalse(self.manager.delete_session("owned", user_id=self.owner.id))

    def test_unknown_delete_does_not_create_new_session(self):
        self.assertFalse(self.manager.delete_session("not-created", guest_token="guest-a"))
        self.assertEqual(IntakeSessionRecord.query.count(), 0)
        self.assertEqual(self.manager._sessions, {})

    def test_delete_can_join_caller_transaction_and_rollback(self):
        self.manager.get_or_create_session("rollback", guest_token="guest-a")
        self.assertTrue(self.manager.delete_session("rollback", guest_token="guest-a", commit=False))
        db.session.rollback()
        self.assertIsNotNone(IntakeSessionRecord.query.filter_by(conversation_id="rollback").first())
        self.assertEqual(self.manager.get_or_create_session("rollback", guest_token="guest-a")["guest_token"], "guest-a")

    def test_stale_cached_guest_cannot_delete_session_claimed_by_another_worker(self):
        self.manager.get_or_create_session("stale", guest_token="guest-a")
        row = IntakeSessionRecord.query.filter_by(conversation_id="stale").first()
        row.user_id = self.other.id
        db.session.commit()
        with self.assertRaises(PermissionError):
            self.manager.delete_session("stale", guest_token="guest-a")
        self.assertIsNotNone(IntakeSessionRecord.query.filter_by(conversation_id="stale").first())

    def test_actual_assistant_reply_replaces_placeholder_and_persists(self):
        session = self.manager.get_or_create_session("actual", guest_token="guest-a")
        session["messages"] = [{"sender": "patient", "content": "Synthetic question"},
                               {"sender": "assistant", "content": "Old intake-only question"}]
        self.manager._save_to_db(session)
        with self.assertRaises(PermissionError):
            self.manager.record_assistant_reply("actual", "Wrong owner", guest_token="guest-b")
        updated = self.manager.record_assistant_reply("actual", "Actual displayed answer", guest_token="guest-a")
        self.assertEqual(len(updated["messages"]), 2)
        self.assertEqual(updated["messages"][-1]["content"], "Actual displayed answer")
        stored = IntakeSessionRecord.query.filter_by(conversation_id="actual").first()
        self.assertEqual(json.loads(stored.messages_json)[-1]["content"], "Actual displayed answer")
        self.assertEqual(stored.version, 1)

    def test_actual_emergency_reply_is_appended_when_no_placeholder_exists(self):
        session = self.manager.get_or_create_session("emergency", guest_token="guest-a")
        session["messages"] = [{"sender": "patient", "content": "Synthetic emergency"}]
        self.manager.record_assistant_reply("emergency", "Displayed emergency guidance", guest_token="guest-a")
        self.assertEqual(session["messages"][-1]["sender"], "assistant")
        self.assertEqual(session["messages"][-1]["content"], "Displayed emergency guidance")

    def test_stale_cached_reply_does_not_resurrect_deleted_draft(self):
        self.manager.get_or_create_session("deleted-during-reply", guest_token="guest-a")
        other_worker = IntakeSessionManager()
        other_worker.delete_session("deleted-during-reply", guest_token="guest-a")
        with self.assertRaises(KeyError):
            self.manager.record_assistant_reply("deleted-during-reply", "Delayed answer", guest_token="guest-a")
        self.assertIsNone(IntakeSessionRecord.query.filter_by(conversation_id="deleted-during-reply").first())

    def test_negated_allergies_or_medication_do_not_become_positive_facts(self):
        facts = extract_clinical_facts_from_text("Tôi không dị ứng thuốc và chưa đang dùng thuốc nào.")
        self.assertEqual(facts["allergies"], [])
        self.assertEqual(facts["medications"], [])
        facts = extract_clinical_facts_from_text("Tôi đang uống nước ấm.")
        self.assertEqual(facts["medications"], [])

    def test_positive_reports_retain_user_words_instead_of_generic_invented_names(self):
        facts = extract_clinical_facts_from_text("Tôi dị ứng penicillin; tôi đang uống metformin.")
        self.assertIn("penicillin", " ".join(facts["allergies"]))
        self.assertIn("metformin", " ".join(facts["medications"]))
        self.assertNotIn("penicillin", " ".join(facts["medications"]))
        mixed = extract_clinical_facts_from_text("Tôi không dị ứng thuốc và đang uống metformin.")
        self.assertEqual(mixed["allergies"], [])
        self.assertIn("metformin", " ".join(mixed["medications"]))


if __name__ == "__main__":
    unittest.main()
