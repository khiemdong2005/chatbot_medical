"""
core/csrf_protection.py
Chính sách bảo vệ CSRF và Kiểm tra Nguồn gốc (Origin / Referer Policy) dùng chung cho MediMind.
Áp dụng đồng bộ cho cả Flask WSGI routes và FastAPI native routes (Phase 8.2 Hardening).
"""
import urllib.parse
from typing import Optional, Set, Tuple, Any, Mapping
from core.settings import get_settings


def get_trusted_origins(request_host: Optional[str] = None) -> Set[str]:
    """
    Tổng hợp danh sách các Origin được tin cậy:
    1. settings.security.cors_allowed_origins
    2. Same-origin host từ request.host (nếu có)
    3. Local dev origins nếu không phải production
    """
    settings = get_settings()
    trusted: Set[str] = set()

    # 1. Origins từ cấu hình CORS
    for origin in settings.security.cors_allowed_origins:
        clean = origin.strip().lower().rstrip("/")
        if clean:
            trusted.add(clean)

    # 2. Same-origin host từ Header Host của request
    if request_host:
        host_clean = request_host.strip().lower()
        trusted.add(f"http://{host_clean}")
        trusted.add(f"https://{host_clean}")
        if ":" not in host_clean:
            trusted.add(f"http://{host_clean}:5000")
            trusted.add(f"http://{host_clean}:8000")

    # 3. Mặc định phát triển cục bộ nếu không ở chế độ Production
    if not settings.server.is_production:
        trusted.add("http://localhost:5000")
        trusted.add("http://localhost:8000")
        trusted.add("http://127.0.0.1:5000")
        trusted.add("http://127.0.0.1:8000")

    return trusted


def validate_csrf_request(
    method: str,
    headers: Mapping[str, Any],
    cookies: Mapping[str, Any],
    request_host: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Xác thực CSRF theo chính sách bảo mật Phase 8.2:
    - Safe methods (GET, HEAD, OPTIONS, TRACE): Luôn cho phép.
    - Mutating methods (POST, PUT, DELETE, PATCH):
      1. Nếu có Origin -> Origin phải nằm trong danh sách trusted origins.
      2. Nếu không có Origin -> Kiểm tra Referer (Origin trích xuất từ Referer phải thuộc trusted).
      3. Nếu không có cả Origin và Referer:
         - Nếu mang phiên xác thực (session cookie / guest_token) -> TỪ CHỐI (403).
         - Nếu không mang phiên xác thực (API không dùng session) -> Cho phép.
    """
    norm_method = (method or "").upper()
    if norm_method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return True, None

    trusted = get_trusted_origins(request_host)

    # 1. Kiểm tra Origin header
    origin = headers.get("origin") or headers.get("Origin")
    if origin:
        norm_origin = str(origin).strip().lower().rstrip("/")
        if norm_origin in trusted:
            return True, None
        return False, "Yêu cầu bị từ chối do vi phạm chính sách cùng nguồn gốc (Origin Policy Mismatch)."

    # 2. Kiểm tra Referer header nếu Origin vắng mặt
    referer = headers.get("referer") or headers.get("Referer")
    if referer:
        try:
            parsed = urllib.parse.urlparse(str(referer))
            referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")
            if referer_origin in trusted:
                return True, None
        except Exception:
            pass
        return False, "Yêu cầu bị từ chối do vi phạm chính sách Referer (Referer Policy Mismatch)."

    # 3. Cả Origin và Referer đều vắng mặt:
    # Nếu request mang phiên đăng nhập (ambient credentials) -> từ chối vì nguy cơ CSRF
    has_session = bool(cookies.get("session") or cookies.get("guest_token"))
    if has_session:
        return False, "Yêu cầu thay đổi trạng thái mang phiên xác thực bị từ chối do thiếu tiêu đề Origin hoặc Referer (CSRF Protection)."

    return True, None
