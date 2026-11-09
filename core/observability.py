# ==============================================================
# MEDIMIND CLINICAL AI - ENTERPRISE OBSERVABILITY & TELEMETRY
# Chuẩn hóa: Google SRE 4 Golden Signals, RED Method & Prometheus TSDB
# ==============================================================

import os
import sys
import time
import ctypes
import platform
import threading
import traceback
from collections import deque
from typing import Optional, Dict, Any, List
from flask import Request, Response

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


# ==============================================================
# 1. PROMETHEUS METRICS SPECIFICATION (SRE & CLINICAL DOMAIN)
# ==============================================================

if PROMETHEUS_AVAILABLE:
    # 1.1 HTTP Golden Signals (Rate, Errors, Duration)
    HTTP_REQUESTS_TOTAL = Counter(
        "medimind_http_requests_total",
        "Tổng số yêu cầu HTTP tới hệ thống",
        ["method", "endpoint", "status"]
    )

    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "medimind_http_request_duration_seconds",
        "Thời gian xử lý yêu cầu HTTP tính bằng giây",
        ["method", "endpoint"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    ACTIVE_USERS_GAUGE = Gauge(
        "medimind_active_users_total",
        "Tổng số lượng tài khoản bệnh nhân/bác sĩ trong hệ thống"
    )

    # 1.2 Clinical Domain Metrics (Y tế & Trí tuệ nhân tạo)
    CLINICAL_TRIAGE_TOTAL = Counter(
        "medimind_clinical_triage_total",
        "Số ca sàng lọc lâm sàng phân loại theo mức độ cấp cứu",
        ["urgency", "specialist"]
    )

    AI_CHAT_LATENCY_SECONDS = Histogram(
        "medimind_ai_chat_latency_seconds",
        "Thời gian suy luận của AI Gemini (giây)",
        ["model"],
        buckets=[0.2, 0.5, 1.0, 2.0, 3.5, 5.0, 8.0, 15.0]
    )

    PRESCRIPTION_SCANS_TOTAL = Counter(
        "medimind_prescription_scans_total",
        "Số lượng đơn thuốc/xét nghiệm được bóc tách OCR",
        ["status"]
    )

    SYSTEM_MEMORY_LOAD_PERCENT = Gauge(
        "medimind_system_memory_load_percent",
        "Tỷ lệ sử dụng bộ nhớ RAM máy chủ (%)"
    )
else:
    HTTP_REQUESTS_TOTAL = None
    HTTP_REQUEST_DURATION_SECONDS = None
    ACTIVE_USERS_GAUGE = None
    CLINICAL_TRIAGE_TOTAL = None
    AI_CHAT_LATENCY_SECONDS = None
    PRESCRIPTION_SCANS_TOTAL = None
    SYSTEM_MEMORY_LOAD_PERCENT = None


# ==============================================================
# 2. IN-MEMORY ROLLING METRICS TRACKER (KHÔNG CẦN DATABASE NGOÀI)
# ==============================================================

class RollingMetricsTracker:
    """
    Theo dõi hiệu năng thời gian thực 60 giây và toàn phiên (In-Memory Ring Buffer).
    Phục vụ trực tiếp Dashboard Cockpit không cần dựng cụm Grafana cồng kềnh.
    """
    def __init__(self, window_size: int = 120):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self.total_requests = 0
        self.status_counts = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
        self.endpoint_counts: Dict[str, int] = {}
        self.recent_latencies = deque(maxlen=200)
        self.recent_timestamps = deque(maxlen=window_size * 5)
        self.recent_errors = deque(maxlen=30)
        self.triage_counts = {"emergency": 0, "moderate": 0, "safe": 0}
        self.total_scans = 0

    def record_request(self, method: str, path: str, status_code: int, duration_sec: float):
        now = time.time()
        with self._lock:
            self.total_requests += 1
            cat = f"{status_code // 100}xx"
            if cat in self.status_counts:
                self.status_counts[cat] += 1
            else:
                self.status_counts["5xx"] += 1

            clean_path = path.split("?")[0]
            if len(clean_path) > 35:
                clean_path = clean_path[:32] + "..."
            self.endpoint_counts[clean_path] = self.endpoint_counts.get(clean_path, 0) + 1

            self.recent_latencies.append(duration_sec)
            self.recent_timestamps.append(now)

            if status_code >= 400:
                self.recent_errors.append({
                    "timestamp": time.strftime("%H:%M:%S", time.localtime(now)),
                    "method": method,
                    "path": clean_path,
                    "status": status_code,
                    "duration_ms": round(duration_sec * 1000, 1)
                })

    def record_triage(self, urgency: str):
        with self._lock:
            urg = (urgency or "safe").lower().strip()
            if "emergency" in urg or "nguy" in urg or "cấp cứu" in urg:
                self.triage_counts["emergency"] += 1
            elif "mod" in urg or "theo dõi" in urg:
                self.triage_counts["moderate"] += 1
            else:
                self.triage_counts["safe"] += 1

    def record_scan(self):
        with self._lock:
            self.total_scans += 1

    def get_snapshot(self) -> Dict[str, Any]:
        now = time.time()
        uptime_sec = max(1, int(now - self.start_time))
        hours, rem = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_formatted = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

        with self._lock:
            # Tính RPS trong 60s gần nhất
            threshold = now - 60.0
            recent_req_count = sum(1 for t in self.recent_timestamps if t >= threshold)
            current_rps = round(recent_req_count / 60.0, 2)

            # Phân tích độ trễ
            latencies = list(self.recent_latencies)
            if latencies:
                avg_latency_ms = round(sum(latencies) / len(latencies) * 1000, 1)
                sorted_lats = sorted(latencies)
                p95_index = int(len(sorted_lats) * 0.95)
                p95_latency_ms = round(sorted_lats[min(p95_index, len(sorted_lats) - 1)] * 1000, 1)
                max_latency_ms = round(sorted_lats[-1] * 1000, 1)
            else:
                avg_latency_ms = 0.0
                p95_latency_ms = 0.0
                max_latency_ms = 0.0

            total_errors = self.status_counts["4xx"] + self.status_counts["5xx"]
            error_rate_pct = round((total_errors / max(1, self.total_requests)) * 100, 2)

            top_endpoints = sorted(self.endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:6]

            return {
                "uptime_seconds": uptime_sec,
                "uptime_formatted": uptime_formatted,
                "total_requests": self.total_requests,
                "current_rps": current_rps,
                "avg_latency_ms": avg_latency_ms,
                "p95_latency_ms": p95_latency_ms,
                "max_latency_ms": max_latency_ms,
                "error_rate_percent": error_rate_pct,
                "status_breakdown": dict(self.status_counts),
                "top_endpoints": top_endpoints,
                "recent_errors": list(self.recent_errors),
                "triage_counts": dict(self.triage_counts),
                "total_scans": self.total_scans
            }


metrics_tracker = RollingMetricsTracker()


# ==============================================================
# 3. PHẦN CỨNG & HẠ TẦNG MÁY CHỦ (STDLIB CTYPES - ZERO PIP OVERHEAD)
# ==============================================================

def get_system_hardware_stats() -> Dict[str, Any]:
    """
    Thu thập thông số RAM, CPU và kích thước CSDL trực tiếp từ Windows OS / POSIX stdlib.
    """
    mem_percent = 0
    total_ram_gb = 0.0
    avail_ram_gb = 0.0

    try:
        if platform.system() == "Windows":
            # Windows Kernel32 GlobalMemoryStatusEx via ctypes
            stat = (ctypes.c_ulonglong * 16)()
            stat[0] = 64  # sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                mem_percent = ctypes.c_ulong.from_buffer(stat, 4).value
                total_ram_gb = round(stat[1] / (1024 ** 3), 2)
                avail_ram_gb = round(stat[2] / (1024 ** 3), 2)
        else:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            info = {l.split(":")[0]: int(l.split(":")[1].split()[0]) for l in lines if ":" in l}
            total = info.get("MemTotal", 1)
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            mem_percent = round((1 - (avail / total)) * 100, 1)
            total_ram_gb = round(total / (1024 * 1024), 2)
            avail_ram_gb = round(avail / (1024 * 1024), 2)
    except Exception:
        mem_percent = 45.0
        total_ram_gb = 16.0
        avail_ram_gb = 8.8

    if PROMETHEUS_AVAILABLE and SYSTEM_MEMORY_LOAD_PERCENT:
        try:
            SYSTEM_MEMORY_LOAD_PERCENT.set(mem_percent)
        except Exception:
            pass

    db_size_mb = 0.0
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "medimind.db")
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "medimind.db")
    if os.path.exists(db_path):
        try:
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        except Exception:
            pass

    return {
        "memory_load_percent": mem_percent,
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": avail_ram_gb,
        "database_size_mb": db_size_mb,
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}"
    }


# ==============================================================
# 4. HỆ THỐNG CẢNH BÁO TỨC THỜI TELEGRAM (ALERTING ENGINE)
# ==============================================================

class TelegramAlerter:
    """Hệ thống bắn tin nhắn báo động sự cố trực tiếp qua Telegram Bot API."""
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._last_alert_time: Dict[str, float] = {}

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_alert(self, title: str, message: str, level: str = "ERROR", extra: Optional[Dict[str, Any]] = None) -> bool:
        now = time.time()
        dedup_key = f"{level}:{title}"
        if now - self._last_alert_time.get(dedup_key, 0) < 60:
            return True
        self._last_alert_time[dedup_key] = now

        icon = "🚨" if level == "CRITICAL" else "⚠️" if level == "ERROR" else "ℹ️"
        text = f"{icon} *[MEDIMIND SRE ALERT - {level}]*\n\n"
        text += f"*Tiêu đề:* `{title}`\n"
        text += f"*Chi tiết:* {message}\n"
        text += f"*Thời gian:* `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"

        if extra:
            text += "\n*Ngữ cảnh tác chiến:*\n"
            for k, v in extra.items():
                text += f"• `{k}`: `{str(v)[:200]}`\n"

        if not self.is_configured():
            print("\n" + "=" * 70)
            print(f"🔔 [TELEGRAM SRE ALERT SIMULATOR] ({level})")
            print(text)
            print("=" * 70 + "\n")
            return True

        try:
            import urllib.request
            import urllib.parse
            import json

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
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
            "User-Agent": req.headers.get("User-Agent", "Unknown")[:70],
            "Exception": type(error).__name__
        }
        self.send_alert(
            title="Lỗi máy chủ nội bộ (500 Internal Server Error)",
            message=f"Đã xảy ra ngoại lệ không xử lý: `{str(error)}`\n\n```python\n{tb[-300:]}\n```",
            level="CRITICAL",
            extra=extra_info
        )


telegram_alerter = TelegramAlerter()


# ==============================================================
# 5. ĐỒNG BỘ CHỈ SỐ LÂM SÀNG & HTTP HANDLERS
# ==============================================================

def record_http_metrics(method: str, endpoint: str, status_code: int, duration_seconds: float):
    """Ghi nhận chỉ số HTTP vào cả Prometheus TSDB và In-Memory Ring Buffer."""
    metrics_tracker.record_request(method, endpoint, status_code, duration_seconds)

    if PROMETHEUS_AVAILABLE and HTTP_REQUESTS_TOTAL:
        try:
            status_str = str(status_code)
            clean_endpoint = endpoint.split("?")[0]
            if len(clean_endpoint) > 40:
                clean_endpoint = clean_endpoint[:38] + "..."
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=clean_endpoint, status=status_str).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=clean_endpoint).observe(duration_seconds)
        except Exception:
            pass


def record_clinical_triage(urgency: str, specialist: str = "Triage"):
    """Ghi nhận phân loại cấp cứu lâm sàng."""
    metrics_tracker.record_triage(urgency)
    if PROMETHEUS_AVAILABLE and CLINICAL_TRIAGE_TOTAL:
        try:
            CLINICAL_TRIAGE_TOTAL.labels(urgency=urgency, specialist=specialist).inc()
        except Exception:
            pass


def record_ai_latency(duration_seconds: float, model: str = "gemini-3.5-flash"):
    """Ghi nhận thời gian phản hồi của AI."""
    if PROMETHEUS_AVAILABLE and AI_CHAT_LATENCY_SECONDS:
        try:
            AI_CHAT_LATENCY_SECONDS.labels(model=model).observe(duration_seconds)
        except Exception:
            pass


def record_prescription_scan(status: str = "success"):
    """Ghi nhận chỉ số quét OCR đơn thuốc."""
    metrics_tracker.record_scan()
    if PROMETHEUS_AVAILABLE and PRESCRIPTION_SCANS_TOTAL:
        try:
            PRESCRIPTION_SCANS_TOTAL.labels(status=status).inc()
        except Exception:
            pass


def get_prometheus_metrics_response() -> Response:
    """Trả về phản hồi định dạng text chuẩn của Prometheus cho endpoint /metrics."""
    if PROMETHEUS_AVAILABLE:
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
    return Response("# Prometheus client is not installed\n", mimetype="text/plain", status=200)
