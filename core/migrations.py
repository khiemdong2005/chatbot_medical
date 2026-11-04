import logging
from datetime import datetime
from sqlalchemy import inspect, text

logger = logging.getLogger("MediMindMigrations")

MIGRATIONS = [
    (
        "2026_01_01_init_schema",
        "Tạo bảng quản lý phiên bản migration",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(50) PRIMARY KEY,
            description VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ),
    (
        "2026_01_02_user_profile_columns",
        "Bổ sung các cột hồ sơ bệnh nhân cho bảng users",
        None  # Xử lý bằng hàm Python để kiểm tra cột tránh lỗi trên SQLite/Postgres
    ),
    (
        "2026_01_03_medical_documents_table",
        "Xác nhận bảng medical_documents bảo vệ quyền sở hữu tệp tải lên (RBAC)",
        """
        CREATE TABLE IF NOT EXISTS medical_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            storage_filename VARCHAR(255) UNIQUE NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            file_size INTEGER NOT NULL,
            file_type VARCHAR(20) NOT NULL,
            mime_type VARCHAR(100),
            owner_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        );
        """
    ),
    (
        "2026_01_04_clinical_consultations_table",
        "Xác nhận bảng clinical_consultations lưu trữ ca tư vấn thực tế",
        """
        CREATE TABLE IF NOT EXISTS clinical_consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            answer TEXT NOT NULL,
            risk_level VARCHAR(100),
            risk_score INTEGER DEFAULT 30,
            symptoms TEXT,
            specialist VARCHAR(100),
            is_emergency BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    ),
    (
        "2026_01_06_clinical_profile_json",
        "Bổ sung cột clinical_profile lưu hồ sơ y tế mở rộng (Dân tộc, Tôn giáo, Tỉnh thành, CCCD...)",
        None
    ),
    (
        "2026_01_05_auth_enhancements",
        "Bổ sung cột avatar_url cho đăng nhập Google và OTP",
        None
    )
]


def run_migrations(engine):
    """
    Hệ thống Migration có phiên bản chính thức (Versioned Migrations):
      - Ghi nhận lịch sử di trú trong bảng schema_migrations.
      - Kiểm tra từng phiên bản, thực thi tuần tự trong transaction.
      - Báo lỗi rõ ràng và dừng lại nếu migration thất bại; không nuốt exception.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)

        # Bước 1: Tạo bảng schema_migrations nếu chưa có
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(50) PRIMARY KEY,
                description VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Bước 2: Lấy danh sách các phiên bản đã áp dụng
        applied_versions = {
            row[0] for row in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        }

        # Bước 3: Duyệt và thực thi các migration chưa áp dụng
        for version, desc, sql in MIGRATIONS:
            if version in applied_versions:
                continue

            logger.info(f"Đang thực thi migration [{version}]: {desc}...")
            try:
                if version == "2026_01_02_user_profile_columns":
                    # Xử lý thêm cột có kiểm tra tồn tại
                    if "users" in inspector.get_table_names():
                        existing_cols = {col["name"] for col in inspector.get_columns("users")}
                        columns_to_add = [
                            ("dob", "VARCHAR(50)"),
                            ("gender", "VARCHAR(20)"),
                            ("address", "VARCHAR(255)"),
                            ("bhyt", "VARCHAR(50)")
                        ]
                        for col_name, col_type in columns_to_add:
                            if col_name not in existing_cols:
                                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
                elif version == "2026_01_06_clinical_profile_json":
                    if "users" in inspector.get_table_names():
                        existing_cols = {col["name"] for col in inspector.get_columns("users")}
                        if "clinical_profile" not in existing_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN clinical_profile TEXT;"))
                elif version == "2026_01_05_auth_enhancements":
                    if "users" in inspector.get_table_names():
                        existing_cols = {col["name"] for col in inspector.get_columns("users")}
                        if "avatar_url" not in existing_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500);"))
                elif sql:
                    # Chạy câu lệnh SQL tạo bảng / index
                    for stmt in sql.strip().split(";"):
                        stmt_clean = stmt.strip()
                        if stmt_clean:
                            conn.execute(text(stmt_clean))

                # Đánh dấu phiên bản đã hoàn tất
                conn.execute(
                    text("INSERT INTO schema_migrations (version, description, applied_at) VALUES (:v, :d, :t)"),
                    {"v": version, "d": desc, "t": datetime.utcnow()}
                )
                applied_versions.add(version)
                logger.info(f"✅ Áp dụng thành công migration [{version}]")
            except Exception as e:
                logger.error(f"❌ Thất bại khi chạy migration [{version}]: {e}")
                raise RuntimeError(f"Database migration failed at [{version}]: {e}") from e
