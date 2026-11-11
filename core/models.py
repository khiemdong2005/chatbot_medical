import os
import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Tự động kích hoạt chế độ WAL Mode và timeout 5000ms để triệt tiêu lỗi 'database is locked'."""
    if "sqlite" in str(type(dbapi_connection)).lower() or hasattr(dbapi_connection, "cursor"):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.close()
        except Exception:
            pass


class User(db.Model):
    """
    Mô hình Người dùng (User Model) tuân thủ kiến trúc SQLAlchemy ORM.
    Chạy 100% trên SQLite ở Local và tương thích hoàn toàn khi chuyển dịch lên production.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="patient")  # 'patient' hoặc 'doctor'
    license_code = db.Column(db.String(50), nullable=True)  # Chứng chỉ hành nghề (Bác sĩ)
    phone_number = db.Column(db.String(20), nullable=True)
    dob = db.Column(db.String(50), nullable=True)  # Ngày sinh (VD: 15/08/1995)
    gender = db.Column(db.String(20), nullable=True)  # Giới tính (Nam / Nữ / Khác)
    address = db.Column(db.String(255), nullable=True)  # Địa chỉ / Tỉnh thành
    bhyt = db.Column(db.String(50), nullable=True)  # Số thẻ BHYT
    avatar_url = db.Column(db.String(500), nullable=True)
    clinical_profile = db.Column(db.Text, nullable=True)  # Ảnh đại diện Google hoặc ảnh upload
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Băm mật khẩu 1 chiều an toàn bằng thuật toán scrypt/pbkdf2."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Kiểm tra mật khẩu nhập vào với chuỗi băm trong CSDL."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """Xuất thông tin an toàn và chuẩn hóa vai trò."""
        is_phone = bool(self.email and self.email.endswith("@phone.medimind"))
        real_email = "" if is_phone else (self.email or "")
        display_account = self.phone_number if (is_phone and self.phone_number) else (self.email or "")

        info_parts = []
        if self.gender:
            info_parts.append(self.gender)
        if self.dob:
            info_parts.append(self.dob)
        if self.phone_number:
            info_parts.append(self.phone_number)
        elif not is_phone and self.email:
            info_parts.append(self.email)

        personal_info = " • ".join(info_parts) if info_parts else ("Bác sĩ chuyên khoa" if self.role == "doctor" else "Thành viên")
        badge = "BS" if self.role == "doctor" else "BN"

        user_dict = {
            "id": self.id,
            "email": real_email,
            "display_account": display_account,
            "is_phone_account": is_phone,
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
