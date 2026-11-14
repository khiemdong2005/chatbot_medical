"""
scripts/check_config.py
Kiểm tra tính hợp lệ và sự đầy đủ của cấu hình MediMind trước khi khởi động.
Phân loại các biến cấu hình thành:
  - OK
  - MISSING OPTIONAL
  - MISSING REQUIRED
  - INVALID
TUYỆT ĐỐI KHÔNG IN RA GIÁ TRỊ NHẠY CẢM HOẶC BÍ MẬT (Zero Secret Leaking).
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.settings import get_settings


def check_configuration():
    settings = get_settings()
    results = []
    has_required_missing = False

    # 1. SECRET_KEY
    if settings.security.secret_key:
        results.append(("SECRET_KEY", "OK (PRESENT)", "Khóa mật mã phiên đã được cấu hình rõ ràng."))
    else:
        if settings.server.is_production:
            results.append(("SECRET_KEY", "MISSING REQUIRED", "Bắt buộc phải có SECRET_KEY trong môi trường Production."))
            has_required_missing = True
        else:
            results.append(("SECRET_KEY", "MISSING OPTIONAL (DEV FALLBACK)", "Đang dùng fallback cố định cho môi trường Dev."))

    # 2. DATABASE_URL & Path
    db_url = settings.paths.database_url
    if db_url and db_url.startswith("sqlite:///"):
        results.append(("DATABASE_URL", "OK", f"SQLite persistent target: {settings.paths.database_path.name}"))
    elif db_url:
        results.append(("DATABASE_URL", "OK", "External database connection string."))
    else:
        results.append(("DATABASE_URL", "INVALID", "Không xác định được đường dẫn CSDL."))
        has_required_missing = True

    # 3. GEMINI_API_KEY
    gemini_key = settings.gemini.api_key
    if gemini_key:
        clean_key = gemini_key.strip()
        if clean_key.startswith("YOUR_") or clean_key == "your_google_gemini_api_key_here":
            results.append(("GEMINI_API_KEY", "INVALID", "Khóa là template placeholder chưa điền."))
        elif len(clean_key) < 10:
            results.append(("GEMINI_API_KEY", "INVALID", "Định dạng khóa quá ngắn."))
        else:
            results.append(("GEMINI_API_KEY", "OK (PRESENT)", f"Đã nạp khóa Gemini AI cho model '{settings.gemini.chat_model}'."))
    else:
        results.append(("GEMINI_API_KEY", "MISSING OPTIONAL", "Chưa cấu hình. Ứng dụng khởi động ở chế độ Offline/Degraded Fallback."))

    # 4. GOOGLE OAUTH
    if settings.security.google_client_id and settings.security.google_client_secret:
        results.append(("GOOGLE_OAUTH", "OK (PRESENT)", "Đã cấu hình đăng nhập Google Single Sign-On."))
    else:
        results.append(("GOOGLE_OAUTH", "MISSING OPTIONAL", "Đăng nhập Google không khả dụng (chỉ dùng email/mật khẩu/OTP)."))

    # 5. SMS PROVIDER (Twilio / SpeedSMS)
    if (settings.messaging.twilio_account_sid and settings.messaging.twilio_auth_token) or settings.messaging.speedsms_auth_token:
        results.append(("SMS_GATEWAY", "OK (PRESENT)", "Đã cấu hình cổng SMS gửi mã OTP."))
    else:
        results.append(("SMS_GATEWAY", "MISSING OPTIONAL", "Chưa cấu hình SMS (OTP chuyển sang log/email/terminal)."))

    # 6. SMTP EMAIL
    if settings.messaging.smtp_server and settings.messaging.smtp_username:
        results.append(("SMTP_EMAIL", "OK (PRESENT)", f"Máy chủ gửi email {settings.messaging.smtp_server}:{settings.messaging.smtp_port}."))
    else:
        results.append(("SMTP_EMAIL", "MISSING OPTIONAL", "Chưa cấu hình SMTP email."))

    # 7. RAG KNOWLEDGE BASE
    chroma_dir = settings.paths.chroma_dir
    if chroma_dir.exists():
        results.append(("RAG_KNOWLEDGE_BASE", "OK", f"Thư mục ChromaDB khả dụng ({chroma_dir.name})."))
    else:
        results.append(("RAG_KNOWLEDGE_BASE", "MISSING OPTIONAL", "Chưa khởi tạo thư mục vector ChromaDB (chạy ingest.py)."))

    # Output table
    print("=" * 70)
    print("       🩺 MEDIMIND CONFIGURATION & READINESS AUDIT")
    print("=" * 70)
    for var, status, detail in results:
        status_color = "[+]" if "OK" in status else ("[-]" if "MISSING OPTIONAL" in status else "[!]")
        print(f" {status_color} {var:<18}: {status:<28} | {detail}")
    print("=" * 70)

    if has_required_missing:
        print(" ❌ CẤU HÌNH THIẾU CÁC BIẾN BẮT BUỘC. ỨNG DỤNG KHÔNG THỂ KHỞI CHẠY AN TOÀN.")
        return 1
    else:
        print(" ✅ CẤU HÌNH HỢP LỆ. ỨNG DỤNG SẴN SÀNG KHỞI ĐỘNG.")
        return 0


if __name__ == "__main__":
    sys.exit(check_configuration())
