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
        "2026_01_05_auth_enhancements",
        "Bổ sung cột avatar_url cho đăng nhập Google và OTP",
        None
    ),
    (
        "2026_01_05_medical_documents_clinical_fields",
        "Bổ sung các cột lâm sàng (chẩn đoán, tóm tắt, json kết quả) cho medical_documents",
        None
    ),
    (
        "2026_01_06_clinical_profile_json",
        "Bổ sung cột clinical_profile lưu hồ sơ y tế mở rộng (Dân tộc, Tôn giáo, Tỉnh thành, CCCD...)",
        None
    ),
    (
        "2026_01_06_intake_sessions_guest_token",
        "Bổ sung cột guest_token cho intake_sessions để kiểm soát quyền phiên khách",
        None
    ),
    ("2026_11_08_consultation_sessions", "Group chat turns by session", None),
    ("2026_11_08_confirmed_summary", "Store explicitly accepted summary", None),
    (
        "2026_11_11_auth_identity_normalization",
        "Chuẩn hóa Authentication: email NULL-able, SĐT E.164, Google Subject ID, bảng auth_identities và loại bỏ synthetic email",
        None
    )
]


def _apply_auth_identity_normalization(conn):
    """
    Thực thi quy trình Expand -> Migrate -> Verify -> Contract cho hệ thống Authentication:
      1. Sao lưu trạng thái định danh gốc vào bảng users_migration_backup_20261111 phục vụ Rollback.
      2. Tái cấu trúc bảng users để cột email cho phép NULL, bổ sung google_sub, account_status, updated_at.
      3. Chuyển đổi các synthetic email (*@phone.medimind, *@phone.medimind.vn) sang email=NULL và phone_number chuẩn E.164 (+84...).
      4. Thiết lập UNIQUE INDEX cho email, phone_number, google_sub và đồng bộ bảng auth_identities.
      5. Xác minh 100% user_id và password_hash được bảo toàn tuyệt đối.
    """
    from core.models import (
        is_synthetic_phone_email,
        extract_phone_from_synthetic_email,
        normalize_email,
        normalize_phone_e164,
    )

    inspector = inspect(conn)
    if "users" not in inspector.get_table_names():
        return

    # Bước 1: Tạo bảng sao lưu định danh gốc phục vụ Rollback an toàn
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users_migration_backup_20261111 (
            user_id INTEGER PRIMARY KEY,
            old_email VARCHAR(120),
            old_phone_number VARCHAR(20),
            old_password_hash VARCHAR(255) NOT NULL,
            migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    existing_cols_info = inspector.get_columns("users")
    existing_col_names = {c["name"] for c in existing_cols_info}
    email_col_info = next((c for c in existing_cols_info if c["name"] == "email"), None)
    email_is_not_null = bool(email_col_info and not email_col_info.get("nullable", True))

    # Đảm bảo các cột cơ bản tồn tại trước khi sao lưu
    optional_cols = [
        ("phone_number", "VARCHAR(20)"),
        ("license_code", "VARCHAR(50)"),
        ("dob", "VARCHAR(50)"),
        ("gender", "VARCHAR(20)"),
        ("address", "VARCHAR(255)"),
        ("bhyt", "VARCHAR(50)"),
        ("avatar_url", "VARCHAR(500)"),
        ("clinical_profile", "TEXT"),
        ("created_at", "DATETIME"),
        ("google_sub", "VARCHAR(255)"),
        ("account_status", "VARCHAR(20) DEFAULT 'active'"),
        ("updated_at", "DATETIME"),
    ]
    for col_name, col_type in optional_cols:
        if col_name not in existing_col_names and col_name.isidentifier():
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
            existing_col_names.add(col_name)

    # Ghi nhận dữ liệu trước chuyển đổi để đối chiếu & rollback
    pre_rows = conn.execute(text(
        "SELECT id, email, phone_number, password_hash FROM users ORDER BY id"
    )).fetchall()
    pre_map = {row[0]: (row[1], row[2], row[3]) for row in pre_rows}

    for uid, (o_email, o_phone, o_pwd) in pre_map.items():
        exists_bk = conn.execute(
            text("SELECT 1 FROM users_migration_backup_20261111 WHERE user_id = :uid"),
            {"uid": uid}
        ).fetchone()
        if not exists_bk:
            conn.execute(
                text("""
                    INSERT INTO users_migration_backup_20261111
                    (user_id, old_email, old_phone_number, old_password_hash, migrated_at)
                    VALUES (:uid, :em, :ph, :pw, :ts)
                """),
                {"uid": uid, "em": o_email, "ph": o_phone, "pw": o_pwd, "ts": datetime.utcnow()}
            )

    # Bước 2 (Expand): Nếu cột email đang bị ràng buộc NOT NULL trên SQLite, rebuild bảng users an toàn
    if email_is_not_null:
        conn.execute(text("DROP INDEX IF EXISTS ix_users_email;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_users_phone_number;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_users_google_sub;"))
        conn.execute(text("""
            CREATE TABLE users_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120),
                phone_number VARCHAR(20),
                google_sub VARCHAR(255),
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(120) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'patient',
                account_status VARCHAR(20) NOT NULL DEFAULT 'active',
                license_code VARCHAR(50),
                dob VARCHAR(50),
                gender VARCHAR(20),
                address VARCHAR(255),
                bhyt VARCHAR(50),
                avatar_url VARCHAR(500),
                clinical_profile TEXT,
                created_at DATETIME,
                updated_at DATETIME
            );
        """))
        conn.execute(text("""
            INSERT INTO users_new (
                id, email, phone_number, google_sub, password_hash, full_name,
                role, account_status, license_code, dob, gender, address,
                bhyt, avatar_url, clinical_profile, created_at, updated_at
            )
            SELECT
                id, email, phone_number, google_sub, password_hash, full_name,
                COALESCE(role, 'patient'), COALESCE(account_status, 'active'),
                license_code, dob, gender, address,
                bhyt, avatar_url, clinical_profile,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
            FROM users;
        """))
        conn.execute(text("DROP TABLE users;"))
        conn.execute(text("ALTER TABLE users_new RENAME TO users;"))

    # Bước 3 (Migrate): Chuẩn hóa dữ liệu email và phone_number, loại bỏ synthetic email
    rows = conn.execute(text(
        "SELECT id, email, phone_number, google_sub FROM users ORDER BY id"
    )).fetchall()

    used_emails = set()
    used_phones = set()
    now_ts = datetime.utcnow()

    # Quét trước các email thật để tránh va chạm
    for uid, raw_email, raw_phone, _ in rows:
        if raw_email and not is_synthetic_phone_email(raw_email):
            norm_em = normalize_email(raw_email) or raw_email.strip().lower()
            used_emails.add((norm_em, uid))

    for uid, raw_email, raw_phone, raw_gsub in rows:
        if is_synthetic_phone_email(raw_email):
            extracted_phone = extract_phone_from_synthetic_email(raw_email)
            norm_phone = normalize_phone_e164(raw_phone) or extracted_phone
            if norm_phone and norm_phone not in used_phones:
                used_phones.add(norm_phone)
                conn.execute(
                    text("""
                        UPDATE users
                        SET email = NULL,
                            phone_number = :ph,
                            account_status = COALESCE(account_status, 'active'),
                            updated_at = :ts
                        WHERE id = :uid
                    """),
                    {"ph": norm_phone, "ts": now_ts, "uid": uid}
                )
            else:
                # Nếu số điện thoại bị trùng với tài khoản khác, chỉ xóa synthetic email thành NULL nếu đã có phone,
                # tuyệt đối không tự động gộp tài khoản (tránh mất dữ liệu).
                logger.warning(f"[Migration Exception] Tài khoản ID={uid} có synthetic email trùng SĐT ({norm_phone}). Giữ nguyên bản ghi để kiểm tra.")
        else:
            new_email = normalize_email(raw_email) if raw_email else None
            if raw_email and not new_email:
                # Giữ nguyên bản ghi email khác thường không thuộc synthetic email
                new_email = raw_email.strip().lower()
            norm_phone = normalize_phone_e164(raw_phone) if raw_phone else None
            if norm_phone:
                if norm_phone not in used_phones:
                    used_phones.add(norm_phone)
                else:
                    # Nếu trùng SĐT với user trước đó, giữ nguyên giá trị cũ và cảnh báo
                    logger.warning(f"[Migration Exception] SĐT {norm_phone} của User ID={uid} trùng lặp.")
                    norm_phone = raw_phone
            conn.execute(
                text("""
                    UPDATE users
                    SET email = :em,
                        phone_number = :ph,
                        account_status = COALESCE(account_status, 'active'),
                        updated_at = COALESCE(updated_at, :ts)
                    WHERE id = :uid
                """),
                {"em": new_email, "ph": norm_phone, "ts": now_ts, "uid": uid}
            )

    # Bước 4: Tạo Unique Indexes và bảng auth_identities
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone_number ON users (phone_number);"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub);"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS auth_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider VARCHAR(30) NOT NULL,
            provider_subject VARCHAR(255) NOT NULL,
            verified_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT uq_auth_identities_provider_subject UNIQUE (provider, provider_subject)
        );
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_identities_user_id ON auth_identities (user_id);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_identities_provider_subject ON auth_identities (provider, provider_subject);"))

    # Đồng bộ dữ liệu từ users sang auth_identities
    migrated_users = conn.execute(text(
        "SELECT id, email, phone_number, google_sub, created_at FROM users ORDER BY id"
    )).fetchall()
    for uid, em, ph, gsub, c_at in migrated_users:
        ts_val = c_at or now_ts
        for prov, subj in (("email", em), ("phone", ph), ("google", gsub)):
            if subj:
                exists_id = conn.execute(
                    text("SELECT 1 FROM auth_identities WHERE provider = :p AND provider_subject = :s"),
                    {"p": prov, "s": subj}
                ).fetchone()
                if not exists_id:
                    conn.execute(
                        text("""
                            INSERT INTO auth_identities (user_id, provider, provider_subject, verified_at, created_at)
                            VALUES (:uid, :p, :s, :v, :c)
                        """),
                        {"uid": uid, "p": prov, "s": subj, "v": ts_val, "c": ts_val}
                    )

    # Bước 5 (Verify): Kiểm chứng toàn vẹn 100% user_id và password_hash sau migration
    post_rows = conn.execute(text(
        "SELECT id, password_hash FROM users ORDER BY id"
    )).fetchall()
    post_map = {r[0]: r[1] for r in post_rows}

    if len(pre_map) != len(post_map):
        raise RuntimeError(
            f"Migration Verification Failed: Số lượng tài khoản thay đổi ({len(pre_map)} -> {len(post_map)})!"
        )
    for uid, (_, _, old_pw) in pre_map.items():
        if uid not in post_map or post_map[uid] != old_pw:
            raise RuntimeError(
                f"Migration Verification Failed: user_id={uid} hoặc password_hash bị sai lệch!"
            )


def rollback_auth_identity_migration(engine):
    """
    Khôi phục (Rollback) migration 2026_11_11_auth_identity_normalization về trạng thái định danh ban đầu
    từ bảng sao lưu users_migration_backup_20261111 mà không làm mất tài khoản hay bệnh án.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "users_migration_backup_20261111" not in inspector.get_table_names():
            return False
        backups = conn.execute(text(
            "SELECT user_id, old_email, old_phone_number FROM users_migration_backup_20261111"
        )).fetchall()
        for uid, old_em, old_ph in backups:
            conn.execute(
                text("UPDATE users SET email = :em, phone_number = :ph WHERE id = :uid"),
                {"em": old_em, "ph": old_ph, "uid": uid}
            )
        conn.execute(
            text("DELETE FROM schema_migrations WHERE version = '2026_11_11_auth_identity_normalization'")
        )
    return True


def run_migrations(engine):
    """
    Hệ thống Migration có phiên bản chính thức (Versioned Migrations):
      - Ghi nhận lịch sử di trú trong bảng schema_migrations.
      - Kiểm tra từng phiên bản, thực thi tuần tự trong transaction.
      - Báo lỗi rõ ràng và dừng lại nếu migration thất bại; không nuốt exception.
    """
    is_sqlite = "sqlite" in str(engine.url).lower()
    raw_conn = None
    if is_sqlite:
        # Tắt tạm thời foreign_keys trước khi mở transaction để cho phép rebuild bảng users an toàn trên SQLite
        raw_conn = engine.raw_connection()
        raw_conn.cursor().execute("PRAGMA foreign_keys=OFF;")
        raw_conn.close()

    try:
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
                        if "users" in inspector.get_table_names():
                            existing_cols = {col["name"] for col in inspect(conn).get_columns("users")}
                            columns_to_add = [
                                ("dob", "VARCHAR(50)"),
                                ("gender", "VARCHAR(20)"),
                                ("address", "VARCHAR(255)"),
                                ("bhyt", "VARCHAR(50)")
                            ]
                            for col_name, col_type in columns_to_add:
                                if col_name not in existing_cols:
                                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
                    elif version == "2026_01_05_auth_enhancements":
                        if "users" in inspector.get_table_names():
                            existing_cols = {col["name"] for col in inspect(conn).get_columns("users")}
                            if "avatar_url" not in existing_cols:
                                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500);"))
                    elif version == "2026_01_05_medical_documents_clinical_fields":
                        if "medical_documents" in inspector.get_table_names():
                            existing_cols = {col["name"] for col in inspect(conn).get_columns("medical_documents")}
                            doc_columns_to_add = [
                                ("doc_type", "VARCHAR(50) DEFAULT 'prescription'"),
                                ("diagnosis", "TEXT"),
                                ("facility", "VARCHAR(255)"),
                                ("doctor", "VARCHAR(255)"),
                                ("patient_name", "VARCHAR(255)"),
                                ("summary", "TEXT"),
                                ("parsed_data", "TEXT")
                            ]
                            for col_name, col_type in doc_columns_to_add:
                                if col_name not in existing_cols:
                                    conn.execute(text(f"ALTER TABLE medical_documents ADD COLUMN {col_name} {col_type};"))
                    elif version == "2026_01_06_clinical_profile_json":
                        if "users" in inspector.get_table_names():
                            existing_cols = {col["name"] for col in inspect(conn).get_columns("users")}
                            if "clinical_profile" not in existing_cols:
                                conn.execute(text("ALTER TABLE users ADD COLUMN clinical_profile TEXT;"))
                    elif version == "2026_01_06_intake_sessions_guest_token":
                        if "intake_sessions" in inspector.get_table_names():
                            existing_cols = {col["name"] for col in inspect(conn).get_columns("intake_sessions")}
                            if "guest_token" not in existing_cols:
                                conn.execute(text("ALTER TABLE intake_sessions ADD COLUMN guest_token VARCHAR(100);"))
                    elif version == "2026_11_08_consultation_sessions":
                        cols = {c["name"] for c in inspect(conn).get_columns("clinical_consultations")}
                        if "conversation_id" not in cols:
                            conn.execute(text("ALTER TABLE clinical_consultations ADD COLUMN conversation_id VARCHAR(100)"))
                            conn.execute(text("CREATE UNIQUE INDEX uq_consultation_session ON clinical_consultations(user_id, conversation_id)"))
                        if "turns_json" not in cols:
                            conn.execute(text("ALTER TABLE clinical_consultations ADD COLUMN turns_json TEXT"))
                    elif version == "2026_11_08_confirmed_summary":
                        if "confirmed_summary" not in {c["name"] for c in inspect(conn).get_columns("clinical_consultations")}:
                            conn.execute(text("ALTER TABLE clinical_consultations ADD COLUMN confirmed_summary TEXT"))
                    elif version == "2026_11_11_auth_identity_normalization":
                        _apply_auth_identity_normalization(conn)
                    elif sql:
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
    finally:
        if is_sqlite:
            raw_conn = engine.raw_connection()
            raw_conn.cursor().execute("PRAGMA foreign_keys=ON;")
            raw_conn.close()
