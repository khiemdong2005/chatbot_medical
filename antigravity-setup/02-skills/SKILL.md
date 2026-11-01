---
name: reusable-agent-skill-template
description: Định nghĩa kỹ năng chuẩn cho AI Agent trong Antigravity để tái sử dụng xuyên suốt các phiên làm việc.
---

# 07. SKILL.md — Định nghĩa kỹ năng Agent tái sử dụng

## 📌 Tổng quan
`SKILL.md` là định dạng chuẩn để đóng gói chuyên môn, quy trình nghiệp vụ và các công cụ hỗ trợ thành một kỹ năng mà Antigravity có thể kích hoạt tự động hoặc qua slash command.

## 📂 Cấu trúc một Skill chuẩn
```text
my-custom-skill/
├── SKILL.md             # File hướng dẫn chính kèm YAML frontmatter
├── scripts/             # Script Python/Bash bổ trợ
├── examples/            # Mã nguồn và ví dụ minh họa
└── references/          # Tài liệu chuyên sâu tham chiếu
```

## 📝 Mẫu nội dung SKILL.md
```markdown
---
name: my-skill-name
description: Giải thích ngắn gọn kỹ năng này làm gì và khi nào nên kích hoạt.
---

# Hướng dẫn Kỹ năng
1. Quy tắc bắt buộc tuân thủ.
2. Các bước thực hiện tuần tự.
3. Tiêu chí nghiệm thu đầu ra.
```

## 💡 Mẹo dùng với Antigravity
* Đặt kỹ năng dự án vào `.gemini/skills/` hoặc thư mục cấu hình toàn cục `~/.gemini/antigravity/skills/`.
* Giữ phần `description` trong YAML frontmatter thật rõ ràng để Agent biết chính xác khi nào cần tự kích hoạt kỹ năng.
