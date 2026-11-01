import pytest
from sqlalchemy import create_engine, inspect, text
from core.migrations import run_migrations, MIGRATIONS


def test_migrations_are_versioned_and_tracked():
    """Kiểm thử: Migrations có phiên bản rõ ràng và được lưu vết trong schema_migrations."""
    # Dùng database in-memory riêng biệt
    engine = create_engine("sqlite:///:memory:")

    # Tạo bảng users trước để test việc thêm cột
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(120) NOT NULL,
                role VARCHAR(20) DEFAULT 'patient'
            );
        """))

    # Chạy migrations lần 1
    run_migrations(engine)

    # Kiểm tra bảng schema_migrations tồn tại
    inspector = inspect(engine)
    assert "schema_migrations" in inspector.get_table_names()

    # Kiểm tra tất cả các phiên bản migration đã được lưu vết
    with engine.connect() as conn:
        applied = {
            row[0] for row in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        }
        for version, desc, _ in MIGRATIONS:
            assert version in applied, f"Migration {version} chưa được ghi nhận vào schema_migrations!"

        # Kiểm tra các cột mới đã được thêm vào bảng users
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        for col_name in ["dob", "gender", "address", "bhyt"]:
            assert col_name in user_cols, f"Cột {col_name} chưa được thêm vào bảng users!"

    # Chạy migrations lần 2 (Idempotency) -> Phải an toàn, không báo lỗi, không áp dụng trùng
    run_migrations(engine)

