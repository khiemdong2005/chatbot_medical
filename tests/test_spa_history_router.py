"""Tests for SPA Router & Browser History API integration."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-32bytes-long-for-testing")
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")
os.environ.setdefault("DEV_SEED_USERS", "false")
os.environ.setdefault("FLASK_DEBUG", "0")

from app import create_app
from core.models import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SpaHistoryRouterTests(unittest.TestCase):
    def test_app_js_implements_unified_router_and_popstate_handler(self):
        app_js = (PROJECT_ROOT / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")

        for expected in (
            "function navigateTo(tabName, subView = null, pushHistory = true)",
            "function syncSubViewHistory(tabId, subView, pushHistory = true)",
            "function applyOcrSubView(subView)",
            "window.navigateTo = navigateTo;",
            "window.history.pushState(",
            "window.history.replaceState(",
            "window.addEventListener('popstate'",
            "navigateTo(route.tab, route.subView, false);",
            "navigateTo(initialRoute.tab, initialRoute.subView, 'replace');",
            "navigateTo('ocr-tab', 'verify', true);",
            "navigateTo('ocr-tab', 'result', true);",
        ):
            self.assertIn(expected, app_js)

        self.assertIn("'booking-tab': 'facilities'", app_js)
        self.assertIn("'doctor-tab': 'nutrition'", app_js)

        for js_file in (PROJECT_ROOT / "frontend" / "static" / "js").glob("*.js"):
            js_text = js_file.read_text(encoding="utf-8")
            self.assertNotIn("history.back(", js_text, f"Found raw history.back() in {js_file.name}")

    def test_nutrition_flow_syncs_subview_history(self):
        nf_js = (PROJECT_ROOT / "frontend" / "static" / "js" / "nutrition-flow.js").read_text(encoding="utf-8")
        for expected in (
            "window.applyNutritionSubView",
            "window.syncSubViewHistory('doctor-tab', stage, true);",
            "window.navigateTo('doctor-tab', backStage, true)",
            "show(validStage, false);",
        ):
            self.assertIn(expected, nf_js)

    def test_template_uses_unified_navigate_to_and_renders(self):
        html_text = (PROJECT_ROOT / "frontend" / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("history.back(", html_text)
        for target in (
            "navigateTo('home-tab')",
            "navigateTo('chat-tab')",
            "navigateTo('ocr-tab')",
            "navigateTo('booking-tab')",
            "navigateTo('doctor-tab')",
            "navigateTo('profile-tab')",
            "navigateTo('settings-tab')",
        ):
            self.assertIn(target, html_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            flask_app = create_app(
                {
                    "TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                    "SECRET_KEY": "test-secret-key-for-unit-testing",
                    "SESSION_COOKIE_SECURE": False,
                    "UPLOAD_FOLDER": tmpdir,
                }
            )
            client = flask_app.test_client()
            res = client.get("/")
            self.assertEqual(res.status_code, 200)
            rendered = res.get_data(as_text=True)
            self.assertIn("navigateTo('chat-tab')", rendered)
            self.assertIn("navigateTo('ocr-tab')", rendered)
            with flask_app.app_context():
                db.session.remove()
                db.drop_all()


if __name__ == "__main__":
    unittest.main()
