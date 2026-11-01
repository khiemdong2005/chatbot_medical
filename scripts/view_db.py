import os
from dotenv import load_dotenv

load_dotenv()

from app import app
from core.models import db, User

def display_database():
    with app.app_context():
        users = User.query.all()
        print("\n" + "=" * 115)
        print("📊 DANH SÁCH HỒ SƠ NGƯỜI DÙNG TRONG CƠ SỞ DỮ LIỆU MEDIMIND (instance/medimind.db)")
        print("=" * 115)
        header = f"{'ID':<4} | {'HỌ VÀ TÊN':<20} | {'GIỚI TÍNH':<9} | {'NGÀY SINH':<10} | {'SĐT / TÀI KHOẢN':<20} | {'MÃ BHYT':<14} | {'ĐỊA CHỈ'}"
        print(header)
        print("-" * 115)
        for u in users:
            gender = u.gender or "---"
            dob = u.dob or "---"
            phone_or_email = u.phone_number or (u.email if not u.email.endswith('@phone.medimind') else u.email.replace('@phone.medimind', ''))
            bhyt = u.bhyt or "---"
            addr = u.address or "---"
            print(f"{u.id:<4} | {u.full_name:<20} | {gender:<9} | {dob:<10} | {phone_or_email:<20} | {bhyt:<14} | {addr}")
        print("=" * 115)
        print(f"Tổng cộng: {len(users)} hồ sơ đang lưu trữ trong CSDL SQLite.\n")

if __name__ == "__main__":
    display_database()
