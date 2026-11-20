import sys
import sqlite3
import json
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "instance" / "medimind.db"

def get_connection():
    if not DB_PATH.exists():
        print(f"❌ Không tìm thấy CSDL tại {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def update_user(user_id=1, role=None, blood=None, allergies=None, height=None, weight=None, dob=None, phone=None, name=None):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    if not user:
        print(f"❌ Không tìm thấy user với id = {user_id}")
        return

    updates = []
    params = []

    if role:
        updates.append("role = ?")
        params.append(role)
        if role == "doctor":
            updates.append("license_code = ?")
            params.append("BS-CK1-2026")
    if dob:
        updates.append("dob = ?")
        params.append(dob)
    if phone:
        updates.append("phone_number = ?")
        params.append(phone)
    if name:
        updates.append("full_name = ?")
        params.append(name)

    # Clinical profile JSON
    raw_cp = user["clinical_profile"] or "{}"
    try:
        cp = json.loads(raw_cp)
    except Exception:
        cp = {}

    changed_cp = False
    if blood:
        cp["blood_type"] = blood
        changed_cp = True
    if allergies:
        cp["allergies"] = allergies
        changed_cp = True
    if height:
        cp["height"] = str(height)
        changed_cp = True
    if weight:
        cp["weight"] = str(weight)
        changed_cp = True

    if changed_cp:
        updates.append("clinical_profile = ?")
        params.append(json.dumps(cp, ensure_ascii=False))

    if updates:
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        cur.execute(sql, tuple(params))
        conn.commit()
        print(f"✅ Đã cập nhật thành công User #{user_id}!")
    else:
        print("ℹ️ Không có thông số nào cần cập nhật.")

    conn.close()

def add_sample_consultations(user_id=1):
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cur.fetchone():
        print(f"❌ Không tìm thấy user #{user_id}")
        return

    sample_cases = [
        (
            user_id,
            "Tôi bị đau rát họng, nuốt đau 3 ngày nay và sốt nhẹ 38.2 độ.",
            "Dựa trên triệu chứng nuốt đau và sốt, phác đồ MedlinePlus gợi ý hội chứng Viêm họng cấp tính. Khuyến nghị súc họng nước muối sinh lý, bù nước điện giải và theo dõi nhiệt độ.",
            "Mức độ nhẹ",
            25,
            "Đau họng, sốt 38.2°C, nuốt vướng",
            "Nội tổng quát",
            0
        ),
        (
            user_id,
            "Thỉnh thoảng tim đập nhanh hồi hộp khi làm việc áp lực căng thẳng.",
            "Phân tích điện tâm đồ và dấu hiệu lâm sàng: Nhịp xoang nhanh nhẹ do stress. Khuyến cáo điều hòa nhịp thở, hạn chế caffeine và tái khám chuyên khoa tim mạch.",
            "Theo dõi",
            40,
            "Hồi hộp, tim đập nhanh từng cơn",
            "Tim mạch",
            0
        )
    ]

    for c in sample_cases:
        cur.execute("""
            INSERT INTO clinical_consultations 
            (user_id, message, answer, risk_level, risk_score, symptoms, specialist, is_emergency, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-2 days'))
        """, c)

    conn.commit()
    print(f"✅ Đã thêm 2 ca khám & tư vấn mẫu cho User #{user_id} vào bảng clinical_consultations!")
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MediMind Database Test Utility")
    parser.add_argument("--id", type=int, default=1, help="User ID (mặc định: 1)")
    parser.add_argument("--role", choices=["patient", "doctor"], help="Đổi vai trò: patient hoặc doctor")
    parser.add_argument("--blood", help="Cập nhật nhóm máu (VD: O+, A+, B+, AB+)")
    parser.add_argument("--allergies", help="Cập nhật dị ứng (VD: 'Penicillin, Hải sản')")
    parser.add_argument("--height", type=int, help="Chiều cao cm (VD: 172)")
    parser.add_argument("--weight", type=int, help="Cân nặng kg (VD: 65)")
    parser.add_argument("--dob", help="Ngày sinh (VD: 04/10/2005)")
    parser.add_argument("--phone", help="Số điện thoại")
    parser.add_argument("--name", help="Họ và tên")
    parser.add_argument("--add-records", action="store_true", help="Bơm 2 ca khám lâm sàng mẫu để test Timeline hồ sơ")

    args = parser.parse_args()

    if args.add_records:
        add_sample_consultations(args.id)
    else:
        update_user(
            user_id=args.id,
            role=args.role,
            blood=args.blood,
            allergies=args.allergies,
            height=args.height,
            weight=args.weight,
            dob=args.dob,
            phone=args.phone,
            name=args.name
        )
