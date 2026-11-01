import sqlite3
import os
import sys

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

db_path = os.path.join(os.path.dirname(__file__), "instance", "medimind.db")

if not os.path.exists(db_path):
    print(f"Khong tim thay file database tai: {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("SELECT id, full_name, email, role, phone_number, dob, gender, bhyt FROM users")
    rows = cur.fetchall()

    print("\n" + "=" * 110)
    print(" DANH SACH TAI KHOAN TRONG DATABASE (instance/medimind.db)")
    print("=" * 110)
    header = f"{'ID':<4} | {'HO VA TEN':<22} | {'EMAIL / TAI KHOAN':<25} | {'VAI TRO':<10} | {'SDT':<12} | {'NGAY SINH':<10} | {'BHYT'}"
    print(header)
    print("-" * 110)
    for r in rows:
        uid, name, email, role, phone, dob, gender, bhyt = r
        phone_str = phone or "---"
        dob_str = dob or "---"
        bhyt_str = bhyt or "---"
        print(f"{uid:<4} | {str(name):<22} | {str(email):<25} | {str(role):<10} | {phone_str:<12} | {dob_str:<10} | {bhyt_str}")
    print("=" * 110)
    print(f" Tong cong: {len(rows)} tai khoan.\n")
except Exception as e:
    print(f"Loi khi doc database: {e}")
finally:
    conn.close()
