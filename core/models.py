import os
import re
import datetime
from typing import Optional, List
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

UNUSABLE_PASSWORD_PREFIX = "!unusable_oauth_password"
_SYNTHETIC_PHONE_EMAIL_RE = re.compile(r"^(\+?\d{8,15})@phone\.medimind(?:\.vn)?$", re.IGNORECASE)
_EMAIL_FORMAT_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_synthetic_phone_email(value: Optional[str]) -> bool:
    """Kiểm tra xem chuỗi email có phải là synthetic email của tài khoản SĐT cũ hay không."""
    if not value or not isinstance(value, str):
        return False
    return bool(_SYNTHETIC_PHONE_EMAIL_RE.match(value.strip()))


def extract_phone_from_synthetic_email(value: Optional[str]) -> Optional[str]:
    """Trích xuất và chuẩn hóa số điện thoại E.164 từ synthetic email cũ."""
    if not value or not isinstance(value, str):
        return None
    m = _SYNTHETIC_PHONE_EMAIL_RE.match(value.strip())
    if not m:
        return None
    return normalize_phone_e164(m.group(1))


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Chuẩn hóa địa chỉ email thật (lowercase, trim). Trả về None nếu rỗng hoặc là email giả lập."""
    if not email or not isinstance(email, str):
        return None
    cleaned = email.strip().lower()
    if not cleaned or is_synthetic_phone_email(cleaned):
        return None
    if not _EMAIL_FORMAT_RE.match(cleaned):
        return None
    return cleaned


def normalize_phone_e164(phone: Optional[str]) -> Optional[str]:
    """
    Chuẩn hóa số điện thoại về định dạng quốc tế E.164 (VD: 0987656789 -> +84987656789).
    Trả về None nếu chuỗi không phải số điện thoại hợp lệ (9-15 chữ số).
    """
    if not phone or not isinstance(phone, str):
        return None
    raw = phone.strip()
    if not raw or "@" in raw:
        return None
    cleaned = re.sub(r"[^\d+]", "", raw)
    if not cleaned:
        return None
    if cleaned.startswith("+"):
        digits = re.sub(r"\D", "", cleaned[1:])
        if not digits:
            return None
        if digits.startswith("840") and len(digits) == 12:
            digits = "84" + digits[3:]
        if len(digits) < 9 or len(digits) > 15:
            return None
        if digits.startswith("84") and len(digits) != 11:
            return None
        return f"+{digits}"

    digits = re.sub(r"\D", "", cleaned)
    if digits.startswith("0"):
        if len(digits) != 10:
            return None
        return f"+84{digits[1:]}"
    if digits.startswith("84"):
        if len(digits) != 11:
            return None
        return f"+{digits}"
    if len(digits) == 9:
        return f"+84{digits}"
    return None


def format_phone_local(phone: Optional[str]) -> str:
    """Chuyển đổi số điện thoại E.164 (+84987656789) sang dạng nội địa (0987656789) khi cần."""
    if not phone or not isinstance(phone, str):
        return ""
    norm = normalize_phone_e164(phone) or phone.strip()
    if norm.startswith("+84") and len(norm) == 12:
        return "0" + norm[3:]
    return norm


def phone_lookup_candidates(phone: Optional[str]) -> List[str]:
    """Trả về danh sách các biến thể chuẩn hóa (E.164 và nội địa 0...) phục vụ truy vấn index."""
    if not phone or not isinstance(phone, str):
        return []
    raw = phone.strip()
    if is_synthetic_phone_email(raw):
        norm = extract_phone_from_synthetic_email(raw)
    else:
        norm = normalize_phone_e164(raw)
    candidates = []
    if norm:
        candidates.append(norm)
        local_fmt = format_phone_local(norm)
        if local_fmt and local_fmt not in candidates:
            candidates.append(local_fmt)
        digits_only = norm.lstrip("+")
        if digits_only and digits_only not in candidates:
            candidates.append(digits_only)
    else:
        digits = "".join(filter(str.isdigit, raw))
        if 9 <= len(digits) <= 15:
            candidates.append(digits)
    return candidates


from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Tự động kích hoạt chế độ WAL Mode, Foreign Keys và timeout 5000ms."""
    if "sqlite" in str(type(dbapi_connection)).lower() or hasattr(dbapi_connection, "cursor"):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.close()
        except Exception:
            pass


class User(db.Model):
    """
    Mô hình Người dùng (User Model) chuẩn hóa Authentication:
      - email: Địa chỉ email thật (NULL nếu đăng ký bằng SĐT và chưa cung cấp email)
      - phone_number: Số điện thoại thật chuẩn hóa E.164 (+84...), UNIQUE & INDEXED
      - google_sub: Định danh Google Subject ID (OpenID Connect sub), UNIQUE & INDEXED
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=True, index=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False, default=UNUSABLE_PASSWORD_PREFIX)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="patient")  # 'patient', 'doctor', 'admin'
    account_status = db.Column(db.String(20), nullable=False, default="active")  # 'active', 'locked', 'disabled'
    license_code = db.Column(db.String(50), nullable=True)  # Chứng chỉ hành nghề (Bác sĩ)
    dob = db.Column(db.String(50), nullable=True)  # Ngày sinh (VD: 15/08/1995)
    gender = db.Column(db.String(20), nullable=True)  # Giới tính (Nam / Nữ / Khác)
    address = db.Column(db.String(255), nullable=True)  # Địa chỉ / Tỉnh thành
    bhyt = db.Column(db.String(50), nullable=True)  # Số thẻ BHYT
    avatar_url = db.Column(db.String(500), nullable=True)
    clinical_profile = db.Column(db.Text, nullable=True)  # Hồ sơ y tế mở rộng (JSON)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow
    )

    def set_password(self, password: str) -> None:
        """Băm mật khẩu 1 chiều an toàn bằng thuật toán scrypt/pbkdf2."""
        self.password_hash = generate_password_hash(password)

    def set_unusable_password(self) -> None:
        """Đánh dấu tài khoản OAuth chưa thiết lập mật khẩu nội bộ (không lưu mật khẩu Google)."""
        self.password_hash = UNUSABLE_PASSWORD_PREFIX

    def has_usable_password(self) -> bool:
        """Kiểm tra tài khoản có mật khẩu băm hợp lệ để đăng nhập bằng mật khẩu hay không."""
        return bool(self.password_hash and not self.password_hash.startswith("!"))

    def check_password(self, password: str) -> bool:
        """Kiểm tra mật khẩu nhập vào với chuỗi băm trong CSDL."""
        if not password or not self.has_usable_password():
            return False
        try:
            return check_password_hash(self.password_hash, password)
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Xuất thông tin an toàn và chuẩn hóa vai trò."""
        is_synthetic = is_synthetic_phone_email(self.email)
        real_email = "" if (not self.email or is_synthetic) else self.email
        is_phone_only = bool(not real_email and self.phone_number)
        display_account = real_email or (self.phone_number or "")

        info_parts = []
        if self.gender:
            info_parts.append(self.gender)
        if self.dob:
            info_parts.append(self.dob)
        if self.phone_number:
            info_parts.append(self.phone_number)
        elif real_email:
            info_parts.append(real_email)

        personal_info = " • ".join(info_parts) if info_parts else ("Bác sĩ chuyên khoa" if self.role == "doctor" else "Thành viên")
        badge = "BS" if self.role == "doctor" else "BN"

        user_dict = {
            "id": self.id,
            "email": real_email,
            "display_account": display_account,
            "is_phone_account": is_phone_only,
            "google_linked": bool(self.google_sub),
            "account_status": self.account_status or "active",
            "name": self.full_name,
            "full_name": self.full_name,
            "role": self.role,
            "roleType": self.role,
            "personal_info": personal_info,
            "badge": badge,
            "phone_number": self.phone_number or "",
            "dob": self.dob or "",
            "gender": self.gender or "",
            "address": self.address or "",
            "bhyt": self.bhyt or "",
            "avatar_url": self.avatar_url or "",
            "joined_date": self.created_at.strftime("%d/%m/%Y") if self.created_at else ""
        }
        if self.clinical_profile:
            try:
                import json
                extra = json.loads(self.clinical_profile)
                if isinstance(extra, dict):
                    user_dict.update(extra)
            except Exception:
                pass
        return user_dict


class AuthIdentity(db.Model):
    """
    Bảng liên kết đa định danh xác thực (Multi-Provider Identity Mapping):
      - Cho phép 1 người dùng (user_id) liên kết Email, Số điện thoại (E.164) và Google OIDC (sub).
      - Đảm bảo tính duy nhất (provider, provider_subject) trên toàn hệ thống.
    """
    __tablename__ = "auth_identities"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False)  # 'email' | 'phone' | 'google'
    provider_subject = db.Column(db.String(255), nullable=False)
    verified_at = db.Column(db.DateTime, nullable=True, default=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("provider", "provider_subject", name="uq_auth_identities_provider_subject"),
        db.Index("ix_auth_identities_provider_subject", "provider", "provider_subject"),
    )

    user = db.relationship(
        "User",
        backref=db.backref("auth_identities", lazy="selectin", cascade="all, delete-orphan")
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "provider_subject": self.provider_subject,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def sync_user_identities(user: User, verified: bool = True) -> None:
    """
    Đồng bộ các trường định danh trên User (email, phone_number, google_sub)
    vào bảng auth_identities trong cùng transaction hiện tại.
    """
    if not user or not user.id:
        return
    now = datetime.datetime.utcnow() if verified else None
    desired = {}
    norm_email = normalize_email(user.email)
    if norm_email:
        desired["email"] = norm_email
    norm_phone = normalize_phone_e164(user.phone_number)
    if norm_phone:
        desired["phone"] = norm_phone
    if user.google_sub and str(user.google_sub).strip():
        desired["google"] = str(user.google_sub).strip()

    existing_rows = AuthIdentity.query.filter_by(user_id=user.id).all()
    by_provider = {row.provider: row for row in existing_rows}

    for provider, subject in desired.items():
        if provider in by_provider:
            row = by_provider[provider]
            if row.provider_subject != subject:
                row.provider_subject = subject
                if now:
                    row.verified_at = now
        else:
            conflict = AuthIdentity.query.filter_by(provider=provider, provider_subject=subject).first()
            if not conflict:
                db.session.add(AuthIdentity(
                    user_id=user.id,
                    provider=provider,
                    provider_subject=subject,
                    verified_at=now
                ))


class MedicalDocument(db.Model):
    """
    Mô hình quản lý tệp tài liệu y khoa / kết quả xét nghiệm gắn với chủ sở hữu (RBAC).
    Không cho phép truy cập hoặc xóa tài liệu của người dùng khác.
    """
    __tablename__ = "medical_documents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    storage_filename = db.Column(db.String(255), unique=True, nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    doc_type = db.Column(db.String(50), nullable=True, default="prescription")  # 'prescription' hoặc 'lab_test'
    diagnosis = db.Column(db.Text, nullable=True)  # Chẩn đoán bệnh (mắc bệnh gì)
    facility = db.Column(db.String(255), nullable=True)  # Bệnh viện / Phòng khám
    doctor = db.Column(db.String(255), nullable=True)  # Bác sĩ điều trị
    patient_name = db.Column(db.String(255), nullable=True)  # Tên bệnh nhân ghi trên đơn
    summary = db.Column(db.Text, nullable=True)  # Tóm tắt nhanh danh mục thuốc / chỉ số
    parsed_data = db.Column(db.Text, nullable=True)  # Toàn bộ JSON kết quả phân tích để xem lại ngay
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    owner = db.relationship("User", backref=db.backref("documents", lazy=True, cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        def format_size(bytes_size):
            if bytes_size < 1024:
                return f"{bytes_size} B"
            elif bytes_size < 1024 * 1024:
                return f"{bytes_size / 1024:.1f} KB"
            else:
                return f"{bytes_size / (1024 * 1024):.1f} MB"

        return {
            "id": self.id,
            "name": self.original_filename,
            "filename": self.storage_filename,
            "size": format_size(self.file_size),
            "size_bytes": self.file_size,
            "type": self.file_type.upper(),
            "doc_type": self.doc_type or "prescription",
            "diagnosis": self.diagnosis or "Chưa phân loại bệnh",
            "facility": self.facility or "Cơ sở Y tế",
            "doctor": self.doctor or "",
            "patient_name": self.patient_name or "",
            "summary": self.summary or "",
            "has_parsed_data": bool(self.parsed_data),
            "uploaded_at": self.created_at.strftime("%H:%M %d/%m/%Y") if self.created_at else "",
            "created_at_iso": self.created_at.isoformat() if self.created_at else "",
            "owner_id": self.owner_id
        }


class ClinicalConsultation(db.Model):
    """
    Mô hình lưu trữ lịch sử tư vấn lâm sàng phục vụ tóm tắt trước khám (Pre-visit Summary).
    Đảm bảo dữ liệu tóm tắt được trích xuất từ ca tư vấn thực của người dùng, không dùng dữ liệu giả.
    """
    __tablename__ = "clinical_consultations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    conversation_id = db.Column(db.String(100), nullable=True)
    confirmed_summary = db.Column(db.Text, nullable=True)
    turns_json = db.Column(db.Text, nullable=True)
    __table_args__ = (db.UniqueConstraint("user_id", "conversation_id", name="uq_consultation_session"),)
    message = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    risk_level = db.Column(db.String(100), nullable=True)
    risk_score = db.Column(db.Integer, default=30)
    symptoms = db.Column(db.Text, nullable=True)  # JSON-encoded string
    specialist = db.Column(db.String(100), nullable=True)
    is_emergency = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    user = db.relationship("User", backref=db.backref("consultations", lazy=True, cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        import json
        symptoms_list = []
        try:
            symptoms_list = json.loads(self.symptoms or "[]")
        except Exception:
            symptoms_list = []
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "messages": json.loads(self.turns_json or "[]"),
            "message": self.message,
            "answer": self.answer,
            "risk_level": self.risk_level or "Theo dõi tại nhà",
            "risk_score": self.risk_score,
            "symptoms": symptoms_list,
            "specialist": self.specialist or "Y học gia đình",
            "is_emergency": bool(self.is_emergency),
            "created_at": self.created_at.strftime("%H:%M %d/%m/%Y") if self.created_at else ""
        }


class IntakeSessionRecord(db.Model):
    """
    Mô hình lưu trữ bền vững các phiên hỏi bệnh lâm sàng (Intake Session) có cấu trúc.
    Giữ toàn vẹn dữ liệu khi khởi động lại server hoặc chạy multi-worker.
    """
    __tablename__ = "intake_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    guest_token = db.Column(db.String(100), nullable=True, index=True)
    status = db.Column(db.String(50), default="collecting")
    turn_count = db.Column(db.Integer, default=0)
    facts_json = db.Column(db.Text, nullable=False, default="{}")
    messages_json = db.Column(db.Text, nullable=False, default="[]")
    attachments_json = db.Column(db.Text, nullable=False, default="[]")
    is_emergency = db.Column(db.Boolean, default=False)
    is_confirmed = db.Column(db.Boolean, default=False)
    version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.String(50), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = db.relationship("User", backref=db.backref("intake_sessions", lazy=True, cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        import json
        try:
            facts = json.loads(self.facts_json or "{}")
        except Exception:
            facts = {}
        try:
            messages = json.loads(self.messages_json or "[]")
        except Exception:
            messages = []
        try:
            attachments = json.loads(self.attachments_json or "[]")
        except Exception:
            attachments = []
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "guest_token": self.guest_token,
            "status": self.status,
            "turn_count": self.turn_count,
            "facts": facts,
            "messages": messages,
            "attachments": attachments,
            "is_emergency": bool(self.is_emergency),
            "is_confirmed": bool(self.is_confirmed),
            "version": self.version,
            "created_at": self.created_at or ""
        }



class MedicalAppointment(db.Model):
    """Bảng lưu trữ lịch hẹn khám chữa bệnh tại các cơ sở y tế / bệnh viện."""
    __tablename__ = "medical_appointments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    facility_id = db.Column(db.String(50), nullable=False)
    facility_name = db.Column(db.String(255), nullable=False)
    facility_address = db.Column(db.String(255), nullable=True)
    specialty = db.Column(db.String(100), nullable=True)
    appointment_date = db.Column(db.String(20), nullable=False)
    appointment_time = db.Column(db.String(20), nullable=False)
    patient_name = db.Column(db.String(120), nullable=False)
    patient_phone = db.Column(db.String(20), nullable=False)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default="pending", nullable=False)  # pending | confirmed | cancelled
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    user = db.relationship("User", backref=db.backref("appointments", lazy=True, cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "facility_id": self.facility_id,
            "facility_name": self.facility_name,
            "facility_address": self.facility_address or "",
            "specialty": self.specialty or "",
            "appointment_date": self.appointment_date,
            "appointment_time": self.appointment_time,
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "note": self.note or "",
            "status": self.status,
            "created_at": self.created_at.strftime("%H:%M %d/%m/%Y") if self.created_at else ""
        }


def init_db(app):
    """Khởi tạo cơ sở dữ liệu và tự động nâng cấp cấu trúc bảng nếu cần."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        from core.migrations import run_migrations
        run_migrations(db.engine)

        seed_enabled = os.getenv("SEED_DEMO_ACCOUNTS", "false").lower() in ("true", "1", "yes")
        if seed_enabled:
            _seed_demo_accounts()


def _seed_demo_accounts():
    """Tạo sẵn 2 tài khoản Bác sĩ và Bệnh nhân mẫu nếu cấu hình SEED_DEMO_ACCOUNTS được bật."""
    # 1. Bác sĩ mẫu
    doctor = User.query.filter_by(email="bacsi.an@medimind.vn").first()
    if not doctor:
        doctor = User(
            email="bacsi.an@medimind.vn",
            full_name="BS. CKI Nguyễn Văn An",
            role="doctor",
            license_code="CCHN-8429/BYT",
            phone_number="0912345678"
        )
        doctor.set_password("MatKhau123@")
        db.session.add(doctor)

    # 2. Bệnh nhân mẫu
    patient = User.query.filter_by(email="benhnhan.an@gmail.com").first()
    if not patient:
        patient = User(
            email="benhnhan.an@gmail.com",
            full_name="Nguyễn Văn An",
            role="patient",
            phone_number="0987654321",
            dob="15/08/1995",
            gender="Nam"
        )
        patient.set_password("MatKhau123@")
        db.session.add(patient)
    else:
        if not patient.dob:
            patient.dob = "15/08/1995"
        if not patient.gender:
            patient.gender = "Nam"
        db.session.add(patient)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
