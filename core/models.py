import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    """
    Mô hình Người dùng (User Model) tuân thủ kiến trúc SQLAlchemy ORM.
    Chạy 100% trên SQLite ở Local và tương thích hoàn toàn khi chuyển dịch lên AWS RDS PostgreSQL.
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
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Băm mật khẩu 1 chiều an toàn bằng thuật toán scrypt/pbkdf2."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Kiểm tra mật khẩu nhập vào với chuỗi băm trong CSDL."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """Xuất thông tin an toàn và đồng bộ thông tin cá nhân bên dưới họ tên."""
        is_phone = self.email.endswith("@phone.medimind")
        display_account = self.phone_number if (is_phone and self.phone_number) else self.email

        info_parts = []
        if self.gender:
            info_parts.append(self.gender)
        if self.dob:
            info_parts.append(self.dob)
        if self.phone_number:
            info_parts.append(self.phone_number)
        elif not is_phone and self.email:
            info_parts.append(self.email)

        personal_info = " • ".join(info_parts) if info_parts else "Thành viên"

        return {
            "id": self.id,
            "email": display_account,
            "name": self.full_name,
            "role": personal_info,
            "personal_info": personal_info,
            "roleType": "patient",
            "badge": "BN",
            "phone_number": self.phone_number or "",
            "dob": self.dob or "",
            "gender": self.gender or "",
            "address": self.address or "",
            "bhyt": self.bhyt or ""
        }


def init_db(app):
    """Khởi tạo cơ sở dữ liệu và tự động nâng cấp cấu trúc bảng nếu cần."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN dob VARCHAR(50)"))
                conn.commit()
        except Exception:
            pass
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN gender VARCHAR(20)"))
                conn.commit()
        except Exception:
            pass
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN address VARCHAR(255)"))
                conn.commit()
        except Exception:
            pass
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("ALTER TABLE users ADD COLUMN bhyt VARCHAR(50)"))
                conn.commit()
        except Exception:
            pass
        _seed_demo_accounts()


def _seed_demo_accounts():
    """Tạo sẵn 2 tài khoản Bác sĩ và Bệnh nhân mẫu nếu chưa tồn tại trong CSDL."""
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
