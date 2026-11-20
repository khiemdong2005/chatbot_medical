"""
tests/test_environment_isolation.py
Xác minh môi trường automated test được cô lập hoàn toàn khỏi:
- instance/medimind.db (và WAL/SHM) thật
- logs/security_audit.json thật
- uploads/ thật
- subprocess pytest vẫn giữ môi trường cô lập an toàn
"""
import os
import sys
import subprocess
from pathlib import Path

from core.main_fastapi import flask_app_instance
from core.observability import record_security_event


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_pytest_runtime_uses_isolated_db_uploads_and_audit_log():
    real_db = (PROJECT_ROOT / "instance" / "medimind.db").resolve().as_posix().lower()
    real_uploads = (PROJECT_ROOT / "uploads").resolve()
    real_audit_log = (PROJECT_ROOT / "logs" / "security_audit.json").resolve()

    db_uri = str(flask_app_instance.config.get("SQLALCHEMY_DATABASE_URI", "")).lower()
    assert db_uri.startswith("sqlite:///")
    assert real_db not in db_uri
    assert str(PROJECT_ROOT.resolve().as_posix()).lower() + "/instance/medimind.db" not in db_uri

    upload_folder = Path(flask_app_instance.config["UPLOAD_FOLDER"]).resolve()
    assert upload_folder != real_uploads
    assert upload_folder.exists()

    audit_path = Path(os.environ["SECURITY_AUDIT_LOG_PATH"]).resolve()
    assert audit_path != real_audit_log

    before_size = real_audit_log.stat().st_size if real_audit_log.exists() else 0
    record_security_event(
        event_type="LOGIN_FAILED",
        severity="WARNING",
        client_ip="127.0.0.1",
        identifier="iso_probe@test.medimind",
        endpoint="/api/auth/login",
        status_code=401,
    )
    after_size = real_audit_log.stat().st_size if real_audit_log.exists() else 0
    assert after_size == before_size
    assert audit_path.exists() and "iso_probe@test.medimind" in audit_path.read_text(encoding="utf-8")


def test_subprocess_pytest_preserves_isolation():
    real_db = (PROJECT_ROOT / "instance" / "medimind.db").resolve().as_posix().lower()
    cmd = [
        sys.executable,
        "-c",
        (
            "import os; from pathlib import Path; "
            "from core.main_fastapi import flask_app_instance; "
            "print('SUB_DB=' + flask_app_instance.config['SQLALCHEMY_DATABASE_URI']); "
            "print('SUB_LOG=' + os.environ.get('SECURITY_AUDIT_LOG_PATH', ''))"
        ),
    ]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True)
    assert real_db not in proc.stdout.lower()
    assert str((PROJECT_ROOT / "logs" / "security_audit.json").resolve()) not in proc.stdout
