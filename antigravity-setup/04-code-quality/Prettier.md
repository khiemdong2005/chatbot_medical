# 20. Prettier — Chuẩn hóa định dạng mã nguồn

## 📌 Tổng quan
Prettier là opinionated code formatter hỗ trợ JavaScript, HTML, CSS, JSON, Markdown. Tự động căn lề, chấm phẩy, ngắt dòng đồng nhất cho toàn bộ đội ngũ lập trình.

## 🚀 Cài đặt trên Windows 11
```powershell
npm install --save-dev prettier
```

## ⚙️ Cấu hình `.prettierrc`
```json
{
  "semi": true,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "es5",
  "printWidth": 100
}
```

## 💡 Mẹo dùng với Antigravity
* Chạy format toàn bộ dự án: `npx prettier --write "static/**/*.{js,css}"`.
