# ==============================================================
# MEDIMIND CLINICAL AI - OBSERVABILITY & TELEGRAM ALERTING
# ==============================================================

import os
import time
import traceback
import requests
from typing import Optional, Dict, Any
from flask import Request, Response

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


if PROMETHEUS_AVAILABLE:
    # 1. Đo tổng số lượng Request theo Method, Endpoint, Status Code
    HTTP_REQUESTS_TOTAL = Counter(
        "medimind_http_requests_total",
        "Tổng số yêu cầu HTTP tới hệ thống",
        ["method", "endpoint", "status"]
    )

    # 2. Đo phân phối thời gian phản hồi (Latency Histogram)
    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "medimind_http_request_duration_seconds",
        "Thời gian xử lý yêu cầu HTTP tính bằng giây",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    # 3. Chỉ số đếm số tài khoản đăng ký
    ACTIVE_USERS_GAUGE = Gauge(
        "medimind_active_users_total",
        "Tổng số lượng tài khoản bệnh nhân/bác sĩ trong hệ thống"
    )
else:
    HTTP_REQUESTS_TOTAL = None
    HTTP_REQUEST_DURATION_SECONDS = None
    ACTIVE_USERS_GAUGE = None


class TelegramAlerter:
    """Hệ thống bắn tin nhắn báo động sự cố trực tiếp qua Telegram Bot API."""
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_alert(self, title: str, message: str, level: str = "ERROR", extra: Optional[Dict[str, Any]] = None) -> bool:
        icon = "🚨" if level == "CRITICAL" else "⚠️" if level == "ERROR" else "ℹ️"
        text = f"{icon} *[MEDIMIND ALERT - {level}]*\n\n"
        text += f"*Tiêu đề:* `{title}`\n"
        text += f"*Chi tiết:* {message}\n"
        text += f"*Thời gian:* `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"

        if extra:
            text += "\n*Ngữ cảnh:*\n"
            for k, v in extra.items():
                text += f"• `{k}`: `{str(v)[:200]}`\n"

        if not self.is_configured():
            print("\n" + "!" * 70)
            print(f"🔔 [TELEGRAM ALERT SIMULATOR] ({level})")
            print(text)
            print("!" * 70 + "\n")
            return True

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            res = requests.post(url, json=payload, timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"❌ [Telegram Alert] Gửi cảnh báo thất bại: {e}")
            return False

    def notify_server_error(self, error: Exception, req: Request):
        """Tự động đóng gói ngữ cảnh lỗi HTTP 500 gửi về Telegram."""
        tb = traceback.format_exc()
        extra_info = {
            "Method": req.method,
            "Path": req.path,
            "IP": req.headers.get("CF-Connecting-IP") or req.remote_addr,
            "User-Agent": req.headers.get("User-Agent", "Unknown")[:80],
            "Exception": type(error).__name__
        }
        self.send_alert(
            title=f"Lỗi máy chủ nội bộ (500 Internal Server Error)",
            message=f"Đã xảy ra ngoại lệ không xử lý: `{str(error)}`\n\n```python\n{tb[-400:]}\n```",
            level="CRITICAL",
            extra=extra_info
        )


telegram_alerter = TelegramAlerter()


def record_http_metrics(method: str, endpoint: str, status_code: int, duration_seconds: float):
    """Ghi nhận chỉ số HTTP vào Prometheus Metrics."""
    if PROMETHEUS_AVAILABLE and HTTP_REQUESTS_TOTAL:
        try:
            status_str = str(status_code)
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=status_str).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration_seconds)
        except Exception:
            pass


def get_prometheus_metrics_response() -> Response:
    """Trả về phản hồi định dạng text của Prometheus cho endpoint /metrics."""
    if PROMETHEUS_AVAILABLE:
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
    return Response("# Prometheus client is not installed\n", mimetype="text/plain", status=200)
