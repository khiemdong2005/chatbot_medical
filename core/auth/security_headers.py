"""
core/security_headers.py
Chính sách Security Headers dùng chung giữa Flask (WSGI) và FastAPI (ASGI) (Phase 8.3).
Đảm bảo tính nhất quán (Parity) 100% về phòng vệ trình duyệt và che giấu thông tin máy chủ.
"""
from typing import Dict

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://accounts.google.com/gsi/client https://cdnjs.cloudflare.com https://unpkg.com https://maps.googleapis.com https://maps.gstatic.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://unpkg.com; "
    "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
    "img-src 'self' data: blob: https://*.googleusercontent.com https://images.unsplash.com https://image.cooky.vn https://monngonmoingay.com https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://maps.googleapis.com https://maps.gstatic.com; "
    "connect-src 'self' https://accounts.google.com/gsi/ https://maps.googleapis.com https://mapsresources-pa.googleapis.com https://maps.gstatic.com; "
    "frame-src 'self' https://accounts.google.com/gsi/ https://www.google.com https://maps.google.com; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'self';"
)


def get_security_headers(is_https: bool = False) -> Dict[str, str]:
    """
    Trả về bộ headers phòng vệ an ninh đồng nhất cho toàn hệ thống:
      - X-Content-Type-Options: nosniff (chống MIME-sniffing)
      - X-Frame-Options: SAMEORIGIN (chống Clickjacking)
      - Referrer-Policy: strict-origin-when-cross-origin
      - Permissions-Policy: hạn chế truy cập phần cứng nhạy cảm
      - X-Permitted-Cross-Domain-Policies: none (chống Flash/PDF cross-domain)
      - Content-Security-Policy (CSP)
      - Strict-Transport-Security (HSTS - chỉ cấp phát khi request thực sự là HTTPS)
      - Server: Che giấu danh tính framework (MediMind-Clinical-Engine)
    """
    headers = {
        "Server": "MediMind-Clinical-Engine",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), payment=()",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Content-Security-Policy": CSP_POLICY,
    }

    if is_https:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return headers
