import sqlite3
import os
import sys
import webbrowser

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

db_path = os.path.join(os.path.dirname(__file__), "instance", "medimind.db")
html_path = os.path.join(os.path.dirname(__file__), "database_viewer.html")

if not os.path.exists(db_path):
    print("Khong tim thay medimind.db!")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT id, full_name, email, role, phone_number, dob, gender, address, bhyt, password_hash, created_at FROM users")
rows = cur.fetchall()
conn.close()

html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSDL MediMind - Danh sách Người dùng</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    </style>
</head>
<body class="bg-slate-50 text-slate-800 p-6 sm:p-10">
    <div class="max-w-7xl mx-auto">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center pb-6 border-b border-slate-200 gap-4">
            <div>
                <h1 class="text-2xl font-bold text-slate-900 flex items-center gap-2">
                    <span>📊</span> Cơ sở dữ liệu MediMind (medimind.db)
                </h1>
                <p class="text-sm text-slate-500 mt-1">Bảng: <span class="font-mono bg-slate-200 px-2 py-0.5 rounded text-slate-700">users</span> &bull; Tổng cộng: <span class="font-bold text-blue-600">{len(rows)}</span> tài khoản</p>
            </div>
            <div class="flex items-center gap-3">
                <input id="searchInput" onkeyup="filterTable()" type="text" placeholder="Tìm kiếm nhanh họ tên, email, sđt..." 
                       class="px-4 py-2 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm w-72">
            </div>
        </div>

        <div class="mt-6 bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm" id="userTable">
                    <thead class="bg-slate-100/75 text-slate-700 text-xs uppercase tracking-wider font-semibold border-b border-slate-200">
                        <tr>
                            <th class="py-3.5 px-4">ID</th>
                            <th class="py-3.5 px-4">Họ và Tên</th>
                            <th class="py-3.5 px-4">Email / Tài khoản</th>
                            <th class="py-3.5 px-4">Vai trò</th>
                            <th class="py-3.5 px-4">Số điện thoại</th>
                            <th class="py-3.5 px-4">Ngày sinh</th>
                            <th class="py-3.5 px-4">Giới tính</th>
                            <th class="py-3.5 px-4">Mã BHYT</th>
                            <th class="py-3.5 px-4">Ngày tạo</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
"""

for r in rows:
    uid, name, email, role, phone, dob, gender, addr, bhyt, pw_hash, created_at = r
    role_badge = '<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Bác sĩ</span>' if role == 'doctor' else '<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">Bệnh nhân</span>'
    html_content += f"""
                        <tr class="hover:bg-slate-50 transition-colors">
                            <td class="py-3.5 px-4 font-mono font-bold text-slate-500">#{uid}</td>
                            <td class="py-3.5 px-4 font-semibold text-slate-900">{name}</td>
                            <td class="py-3.5 px-4 font-mono text-xs text-blue-600">{email}</td>
                            <td class="py-3.5 px-4">{role_badge}</td>
                            <td class="py-3.5 px-4">{phone or '<span class="text-slate-400">---</span>'}</td>
                            <td class="py-3.5 px-4">{dob or '<span class="text-slate-400">---</span>'}</td>
                            <td class="py-3.5 px-4">{gender or '<span class="text-slate-400">---</span>'}</td>
                            <td class="py-3.5 px-4 font-mono text-xs">{bhyt or '<span class="text-slate-400">---</span>'}</td>
                            <td class="py-3.5 px-4 text-xs text-slate-500">{created_at or '---'}</td>
                        </tr>
    """

html_content += """
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function filterTable() {
            const input = document.getElementById('searchInput');
            const filter = input.value.toLowerCase();
            const table = document.getElementById('userTable');
            const tr = table.getElementsByTagName('tr');

            for (let i = 1; i < tr.length; i++) {
                const text = tr[i].textContent || tr[i].innerText;
                tr[i].style.display = text.toLowerCase().indexOf(filter) > -1 ? '' : 'none';
            }
        }
    </script>
</body>
</html>
"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Đã tạo giao diện xem CSDL tại: {html_path}")
try:
    webbrowser.open("file://" + os.path.abspath(html_path))
    print("Đã tự động mở trình duyệt hiển thị dữ liệu!")
except Exception as e:
    print(f"Không thể mở trình duyệt tự động: {e}")
