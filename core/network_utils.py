"""
core/network_utils.py
Tiện ích mạng chuẩn hóa cho kiểm soát Proxy tin cậy, trích xuất IP an toàn và phát hiện HTTPS (Phase 8.3).
"""
import re
import urllib.parse
from typing import Optional, Dict, Any

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def get_trusted_client_ip(
    remote_addr: Optional[str],
    headers: Dict[str, Any],
    trust_proxy: bool = False,
    trusted_proxy_count: int = 1
) -> str:
    """
    Xác định địa chỉ IP máy khách một cách an toàn:
      - Khi trust_proxy = False (mặc định):
          Tuyệt đối BỎ QUA X-Forwarded-For và Forwarded để chống tấn công giả mạo IP (IP Spoofing).
          Chỉ sử dụng trực tiếp Socket Peer IP (remote_addr / client.host).
      - Khi trust_proxy = True:
          Phân tích chuỗi proxy theo số lượng hop tin cậy (trusted_proxy_count).
          Lấy IP tại vị trí ips[-trusted_proxy_count] thay vì tin cậy giá trị đầu tiên do client gửi.
    """
    direct_ip = (remote_addr or "127.0.0.1").strip()
    if not trust_proxy:
        return direct_ip

    # Chuẩn hóa headers thành chữ thường
    normalized_headers = {str(k).lower(): str(v) for k, v in headers.items()}
    xff = normalized_headers.get("x-forwarded-for")

    if xff:
        ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
        if ips:
            # Chọn IP đứng trước trusted_proxy_count proxy gần nhất
            count = max(1, trusted_proxy_count)
            idx = min(count, len(ips))
            return ips[-idx]

    return direct_ip


def is_request_https(
    is_direct_secure: bool,
    headers: Dict[str, Any],
    trust_proxy: bool = False
) -> bool:
    """
    Xác định xem yêu cầu có thực sự diễn ra qua kênh bảo mật HTTPS hay không:
      - Nếu kết nối trực tiếp là TLS/HTTPS -> True.
      - Nếu không qua proxy tin cậy (trust_proxy = False) -> BỎ QUA X-Forwarded-Proto, trả về is_direct_secure.
      - Nếu trust_proxy = True:
          Kiểm tra header X-Forwarded-Proto == 'https' hoặc Forwarded: proto=https.
    """
    if is_direct_secure:
        return True

    if not trust_proxy:
        return False

    normalized_headers = {str(k).lower(): str(v) for k, v in headers.items()}
    xfp = normalized_headers.get("x-forwarded-proto", "").lower()
    if xfp == "https":
        return True

    forwarded = normalized_headers.get("forwarded", "").lower()
    if "proto=https" in forwarded:
        return True

    return False


def is_safe_url(url: str) -> bool:
    """
    Kiểm tra tính an toàn của URL:
      - Cho phép: http, https, mailto, tel và relative paths (/..., #..., ?...).
      - Từ chối: javascript:, data:, file:, vbscript: để chống tấn công XSS / LFI.
    """
    if not url or not isinstance(url, str):
        return False

    clean_url = url.strip()
    # Loại bỏ ký tự điều khiển ASCII nguy hiểm
    if any(ord(c) < 32 for c in clean_url):
        return False

    # Chặn rõ ràng các scheme nguy hại
    lower_url = clean_url.lower()
    if re.match(r"^(javascript|data|file|vbscript):", lower_url):
        return False

    parsed = urllib.parse.urlparse(clean_url)
    scheme = parsed.scheme.lower()
    if scheme in ALLOWED_URL_SCHEMES:
        return True

    # Cho phép đường dẫn tương đối nội bộ
    if not scheme and clean_url.startswith(("/", "#", "?")):
        return True

    return False


def sanitize_url(url: str, default: str = "") -> str:
    """Trả về URL nếu hợp lệ và an toàn, ngược lại trả về giá trị mặc định."""
    return url.strip() if is_safe_url(url) else default
