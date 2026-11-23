import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

db_path = Path("instance/medimind.db")
if not db_path.exists():
    print(f"❌ Không tìm thấy CSDL tại {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

tables_to_wipe = ["users", "medical_documents", "clinical_consultations", "intake_sessions", "medical_appointments"]

print("⚡ [Bắt đầu dọn sạch kho quân lương - Truncate All Data Tables]")
for tbl in tables_to_wipe:
    cur.execute(f"DELETE FROM '{tbl}'")
    print(f" - Đã xóa sạch dữ liệu bảng: {tbl}")

# Reset SQLite autoincrement sequence
try:
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('users', 'medical_documents', 'clinical_consultations', 'intake_sessions')")
    print(" - Đã reset bộ đếm ID tự tăng (sqlite_sequence) về 1")
except Exception as e:
    print(f" - Lưu ý reset sequence: {e}")

conn.commit()

# VACUUM to reclaim disk space
cur.execute("VACUUM")
print(" - Đã chạy VACUUM tối ưu hóa tập tin CSDL")

print("\n📊 [Kiểm tra trạng thái sau khi xóa]")
for tbl in tables_to_wipe:
    cnt = cur.execute(f"SELECT COUNT(*) FROM '{tbl}'").fetchone()[0]
    print(f"  • Bảng '{tbl}': {cnt} dòng")

conn.close()
print("\n✅ TOÀN BỘ DỮ LIỆU ĐÃ ĐƯỢC XÓA SẠCH SẼ 100%! CSDL ĐÃ SẴN SÀNG CHO ĐẠI CA TEST MỚI!")
