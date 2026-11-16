import os
import sys
import socket
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

# Đảm bảo đường dẫn thư mục gốc dự án luôn nằm trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Đảm bảo thư mục instance luôn tồn tại cho các tiến trình SQLite cục bộ
(PROJECT_ROOT / "instance").mkdir(parents=True, exist_ok=True)

# ==============================================================================
# CẤU HÌNH MÔI TRƯỜNG KIỂM THỬ TẤT ĐỊNH & ZERO-SECRETS
# ==============================================================================
# Thiết lập các biến môi trường chuẩn cho môi trường kiểm thử offline an toàn,
# đảm bảo không bao giờ gọi ra ngoài internet và không đọc secrets từ máy developer.
os.environ["SECRET_KEY"] = "test-secret-key-32bytes-long-for-testing"
os.environ["SEED_DEMO_ACCOUNTS"] = "false"
os.environ["DEV_SEED_USERS"] = "false"
os.environ["FLASK_DEBUG"] = "0"
os.environ["RAG_ACCEPTANCE_THRESHOLD"] = "1.35"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
os.environ["GEMINI_NUTRITION_API_KEY"] = ""
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["SPEEDSMS_API_KEY"] = ""
os.environ["RAG_QUERY_EXPANSION_ENABLED"] = "false"
os.environ["RAG_VECTOR_SEARCH_ENABLED"] = "false"
os.environ["RAG_RERANK_ENABLED"] = "false"

from app import create_app
from core.models import db, User, MedicalDocument, ClinicalConsultation


@pytest.fixture(scope="session", autouse=True)
def guard_active_collection_manifest():
    """
    Bảo vệ bất biến active_collection.json:
    Đảm bảo tệp active_collection.json giữ nguyên vẹn 100% từng byte trước và sau toàn bộ phiên kiểm thử.
    Nếu bất kỳ test nào gây biến đổi mà không hoàn nguyên, fixture sẽ phát hiện và raise lỗi ngay lập tức.
    """
    manifest_path = PROJECT_ROOT / "medical_vectordb" / "active_collection.json"
    orig_bytes = manifest_path.read_bytes() if manifest_path.exists() else None
    yield
    if orig_bytes is not None and manifest_path.exists():
        current_bytes = manifest_path.read_bytes()
        if current_bytes != orig_bytes:
            manifest_path.write_bytes(orig_bytes)
            raise AssertionError(
                "CRITICAL: medical_vectordb/active_collection.json was mutated during test execution! "
                "Tests must never alter the production active collection pointer."
            )


@pytest.fixture(autouse=True)
def network_call_guard(request):
    """
    Cổng phòng hộ mạng tự động (Outbound Network Guard):
    Chặn đứng tất cả các kết nối socket ra ngoài internet (Gemini API, Google OAuth, external HTTP, SMS).
    Cho phép socket kết nối loopback/localhost (127.0.0.1, ::1) để phục vụ test client in-memory.
    Bỏ qua nếu test được đánh dấu rõ ràng với @pytest.mark.live.
    """
    if request.node.get_closest_marker("live"):
        yield
        return

    orig_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError(
                f"Blocked unexpected outbound network connect to {address} during offline test execution! "
                f"Test '{request.node.nodeid}' must run completely offline without external network calls. "
                f"If live network access is truly intended, mark the test explicitly with @pytest.mark.live."
            )
        return orig_connect(self, address)

    socket.socket.connect = guarded_connect
    try:
        yield
    finally:
        socket.socket.connect = orig_connect


@pytest.fixture(autouse=True)
def clean_intake_test_state():
    """Tự động dọn dẹp các bản ghi intake kiểm thử để đảm bảo tính độc lập giữa các test."""
    from core.intake_service import intake_service
    intake_service._sessions.clear()
    yield
    intake_service._sessions.clear()
    try:
        from core.intake_service import intake_db_context
        with intake_db_context():
            from core.models import db, IntakeSessionRecord
            IntakeSessionRecord.query.filter(
                IntakeSessionRecord.conversation_id.like("test_%") |
                IntakeSessionRecord.conversation_id.like("conv_%")
            ).delete(synchronize_session=False)
            db.session.commit()
    except Exception:
        pass


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
    """Flask test client với Origin mô phỏng trình duyệt cục bộ hợp lệ."""
    c = test_app.test_client()
    c.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"
    return c


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
