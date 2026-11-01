import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

# Đảm bảo đường dẫn thư mục gốc dự án luôn nằm trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Đảm bảo môi trường kiểm thử an toàn
os.environ["SECRET_KEY"] = "test-secret-key-32bytes-long-for-testing"
os.environ["SEED_DEMO_ACCOUNTS"] = "false"
os.environ["FLASK_DEBUG"] = "0"
os.environ["RAG_ACCEPTANCE_THRESHOLD"] = "1.35"

from app import create_app
from core.models import db, User, MedicalDocument, ClinicalConsultation


@pytest.fixture
def temp_dirs(tmp_path):
    """Tạo các thư mục tạm cho CSDL, uploads và vector db để không chạm vào dữ liệu thật."""
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    vectordb_dir = tmp_path / "medical_vectordb"
    vectordb_dir.mkdir(parents=True, exist_ok=True)
    
    return {
        "uploads": uploads_dir,
        "vectordb": vectordb_dir
    }


@pytest.fixture
def test_app(temp_dirs):
    """Cấu hình Flask app bằng Factory Pattern cho môi trường kiểm thử với SQLite in-memory."""
    flask_app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SECRET_KEY": "test-secret-key-for-unit-testing",
        "SESSION_COOKIE_SECURE": False,
        "UPLOAD_FOLDER": str(temp_dirs["uploads"])
    })

    with flask_app.app_context():
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    """Flask test client."""
    return test_app.test_client()


@pytest.fixture
def test_users(test_app):
    """Tạo sẵn 2 người dùng User A và User B độc lập để kiểm thử RBAC."""
    with test_app.app_context():
        user_a = User(
            email="usera@test.medimind",
            full_name="Nguyễn Văn A",
            role="patient",
            phone_number="0911111111"
        )
        user_a.set_password("MatKhauUserA123@")
        
        user_b = User(
            email="userb@test.medimind",
            full_name="Trần Thị B",
            role="patient",
            phone_number="0922222222"
        )
        user_b.set_password("MatKhauUserB123@")
        
        db.session.add(user_a)
        db.session.add(user_b)
        db.session.commit()
        
        return {
            "user_a_id": user_a.id,
            "user_b_id": user_b.id,
            "user_a_email": user_a.email,
            "user_b_email": user_b.email
        }
