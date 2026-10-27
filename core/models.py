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
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Băm mật khẩu 1 chiều an toàn bằng thuật toán scrypt/pbkdf2."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Kiểm tra mật khẩu nhập vào với chuỗi băm trong CSDL."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """Xuất thông tin an toàn (loại bỏ trường password_hash)."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.full_name,
            "role": "Bác sĩ lâm sàng" if self.role == "doctor" else "Bệnh nhân",
            "roleType": self.role,
            "badge": "BS" if self.role == "doctor" else "BN",
            "license_code": self.license_code or "",
            "phone_number": self.phone_number or ""
        }


def init_db(app):
    """Khởi tạo cơ sở dữ liệu và nạp dữ liệu hạt giống (Seed Data) mẫu."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
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
            phone_number="0987654321"
        )
        patient.set_password("MatKhau123@")
        db.session.add(patient)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
