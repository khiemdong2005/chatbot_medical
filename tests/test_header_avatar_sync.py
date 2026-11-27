"""Tests for header navbar avatar synchronization (SSR context, upload persistence, and JS helpers)."""

import io
import os
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

os.environ.setdefault("SECRET_KEY", "test-secret-key-32bytes-long-for-testing")
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")
os.environ.setdefault("DEV_SEED_USERS", "false")
os.environ.setdefault("FLASK_DEBUG", "0")

from app import create_app
from core.models import User, db


class HeaderAvatarSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.tmpdir.name) / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "SECRET_KEY": "test-secret-key-for-unit-testing",
                "SESSION_COOKIE_SECURE": False,
                "UPLOAD_FOLDER": str(self.upload_dir),
            }
        )
        self.client = self.app.test_client()
        self.client.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.tmpdir.cleanup()

    def _create_user(self, full_name="Nguyễn Văn Long", email="long@test.medimind", avatar_url=None) -> int:
        with self.app.app_context():
            user = User(
                email=email,
                full_name=full_name,
                role="patient",
                avatar_url=avatar_url,
            )
            user.set_password("MatKhau123@")
            db.session.add(user)
            db.session.commit()
            return user.id

    def _make_png_bytes(self) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), "teal").save(buf, format="PNG")
        return buf.getvalue()

    def test_logged_out_renders_initial_and_hides_avatar_img(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        img_tag = re.search(r'<img\s+id="user-avatar-img"[^>]*>', html)
        init_tag = re.search(r'<div\s+id="user-avatar-initial"[^>]*>([^<]*)</div>', html)
        self.assertIsNotNone(img_tag)
        self.assertIsNotNone(init_tag)
        self.assertIn("hidden", img_tag.group(0))
        self.assertNotIn("hidden", init_tag.group(0))
        self.assertEqual(init_tag.group(1).strip(), "K")

    def test_logged_in_without_avatar_renders_user_initial_fallback(self):
        user_id = self._create_user(full_name="Nguyễn Văn Long", avatar_url=None)
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = "patient"

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        img_tag = re.search(r'<img\s+id="user-avatar-img"[^>]*>', html)
        init_tag = re.search(r'<div\s+id="user-avatar-initial"[^>]*>([^<]*)</div>', html)
        self.assertIsNotNone(img_tag)
        self.assertIsNotNone(init_tag)
        self.assertIn("hidden", img_tag.group(0))
        self.assertNotIn("hidden", init_tag.group(0))
        self.assertEqual(init_tag.group(1).strip(), "L")

    def test_upload_avatar_persists_serves_and_renders_in_header(self):
        user_id = self._create_user(full_name="Nguyễn Văn Long", avatar_url=None)
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = "patient"

        upload_res = self.client.post(
            "/api/auth/avatar",
            data={"file": (io.BytesIO(self._make_png_bytes()), "avatar.png")},
            content_type="multipart/form-data",
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(upload_res.status_code, 200)
        payload = upload_res.get_json()
        self.assertTrue(payload["success"])
        avatar_path = payload["avatar_url"]
        self.assertTrue(avatar_path.startswith("/uploads/"))
        self.assertEqual(payload["avatar"], avatar_path)
        self.assertEqual(payload["user"]["avatar"], avatar_path)
        self.assertEqual(payload["user"]["avatar_url"], avatar_path)

        # Verify uploaded file exists in temp UPLOAD_FOLDER and is served cleanly
        saved_name = avatar_path.split("/uploads/", 1)[1]
        self.assertTrue((self.upload_dir / saved_name).exists())
        serve_res = self.client.get(avatar_path)
        self.assertEqual(serve_res.status_code, 200)
        serve_res.close()

        # Verify /api/auth/me exposes both avatar and avatar_url
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.get_json()
        self.assertTrue(me_data["authenticated"])
        self.assertEqual(me_data["user"]["avatar"], avatar_path)
        self.assertEqual(me_data["user"]["avatar_url"], avatar_path)

        # Verify SSR index page now renders <img> visible and hides initial fallback
        page_res = self.client.get("/")
        self.assertEqual(page_res.status_code, 200)
        html = page_res.get_data(as_text=True)

        img_tag = re.search(r'<img\s+id="user-avatar-img"[^>]*>', html, re.S)
        init_tag = re.search(r'<div\s+id="user-avatar-initial"[^>]*>([^<]*)</div>', html)
        self.assertIsNotNone(img_tag)
        self.assertIsNotNone(init_tag)
        self.assertIn(f'src="{avatar_path}"', img_tag.group(0))
        self.assertIn("border-radius: 50%", img_tag.group(0))
        self.assertIn("object-fit: cover", img_tag.group(0))
        self.assertNotIn("hidden", img_tag.group(0))
        self.assertIn("hidden", init_tag.group(0))

    def test_upload_avatar_requires_auth_and_valid_image(self):
        unauth_res = self.client.post(
            "/api/auth/avatar",
            data={"file": (io.BytesIO(self._make_png_bytes()), "avatar.png")},
            content_type="multipart/form-data",
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(unauth_res.status_code, 401)

        user_id = self._create_user(email="badfile@test.medimind")
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_role"] = "patient"

        bad_ext_res = self.client.post(
            "/api/auth/avatar",
            data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "doc.pdf")},
            content_type="multipart/form-data",
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(bad_ext_res.status_code, 400)

        txt_res = self.client.post(
            "/api/auth/avatar",
            data={"file": (io.BytesIO(b"hello text"), "note.txt")},
            content_type="multipart/form-data",
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(txt_res.status_code, 400)

    def test_frontend_js_contains_header_avatar_sync_and_upload_call(self):
        app_js = (Path(__file__).resolve().parent.parent / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        for symbol in (
            "function syncHeaderAvatar",
            "function getUserRealAvatarUrl",
            "function handleHeaderAvatarError",
            "/api/auth/avatar",
        ):
            self.assertIn(symbol, app_js)


if __name__ == "__main__":
    unittest.main()
