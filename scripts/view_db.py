import os
import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "instance" / "medimind.db"


def display_database():
    if not DB_PATH.exists():
        print(f"Không tìm thấy tệp CSDL tại: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    users = conn.execute(
        "SELECT id, email, full_name, gender, dob, phone_number, avatar_url, created_at FROM users ORDER BY id ASC"
    ).fetchall()

    print("\n" + "=" * 135)
    print(f"📊 DANH SÁCH HỒ SƠ NGƯỜI DÙNG TRONG CƠ SỞ DỮ LIỆU MEDIMIND ({DB_PATH.relative_to(ROOT_DIR)})")
    print("=" * 135)
    header = f"{'ID':<3} | {'HỌ VÀ TÊN':<20} | {'EMAIL / ĐỊNH DANH':<30} | {'GIỚI TÍNH':<9} | {'NGÀY SINH':<10} | {'SĐT':<12} | {'NGUỒN TK':<14} | {'NGÀY TẠO'}"
    print(header)
    print("-" * 135)

    for u in users:
        uid = u["id"]
        name = (u["full_name"] or "---")[:20]
        email = (u["email"] or "---")[:30]
        gender = u["gender"] or "---"
        dob = u["dob"] or "---"
        phone = u["phone_number"] or "---"
        avatar = u["avatar_url"] or ""
        auth_source = "Google OAuth" if "googleusercontent.com" in avatar else ("Google Demo" if "ui-avatars.com" in avatar else "Tài khoản nội bộ")
        created = (u["created_at"] or "")[:19]
        print(f"{uid:<3} | {name:<20} | {email:<30} | {gender:<9} | {dob:<10} | {phone:<12} | {auth_source:<14} | {created}")

    print("=" * 135)
    print(f"✅ Tổng cộng: {len(users)} hồ sơ người dùng đang lưu trữ trong instance/medimind.db.\n")
    conn.close()


if __name__ == "__main__":
    display_database()
