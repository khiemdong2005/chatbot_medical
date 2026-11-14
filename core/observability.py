# ==============================================================
# MEDIMIND CLINICAL AI - HYBRID SECURITY OBSERVABILITY & SIEM
# Chuẩn hóa: Prometheus TSDB (Grafana) & Wazuh SIEM JSON Audit Stream
# ==============================================================

import ctypes
import datetime
import json
import os
import platform
import threading
from typing import Any, Dict, Optional
from flask import Response

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


# ==============================================================
# 1. PROMETHEUS METRICS SPECIFICATION (GRAFANA & SRE GOLDEN SIGNALS)
# ==============================================================

if PROMETHEUS_AVAILABLE:
    HTTP_REQUESTS_TOTAL = Counter(
        "medimind_http_requests_total",
        "Tổng số yêu cầu HTTP tới hệ thống",
        ["method", "endpoint", "status"],
    )

    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "medimind_http_request_duration_seconds",
        "Thời gian xử lý yêu cầu HTTP tính bằng giây",
        ["method", "endpoint"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    ACTIVE_USERS_GAUGE = Gauge(
        "medimind_active_users_total",
        "Tổng số lượng tài khoản người dùng trong hệ thống",
    )

    CLINICAL_TRIAGE_TOTAL = Counter(
        "medimind_clinical_triage_total",
        "Số ca sàng lọc lâm sàng phân loại theo mức độ cấp cứu",
        ["urgency", "specialist"],
    )

    AI_CHAT_LATENCY_SECONDS = Histogram(
        "medimind_ai_chat_latency_seconds",
        "Thời gian suy luận của AI Gemini (giây)",
        ["model"],
        buckets=[0.2, 0.5, 1.0, 2.0, 3.5, 5.0, 8.0, 15.0],
    )

    PRESCRIPTION_SCANS_TOTAL = Counter(
        "medimind_prescription_scans_total",
        "Số lượng đơn thuốc/xét nghiệm được bóc tách OCR",
        ["status"],
    )

    SYSTEM_MEMORY_LOAD_PERCENT = Gauge(
        "medimind_system_memory_load_percent",
        "Tỷ lệ sử dụng bộ nhớ RAM máy chủ (%)",
    )

    SECURITY_EVENTS_TOTAL = Counter(
        "medimind_security_events_total",
        "Tổng số sự kiện an ninh (SIEM / Wazuh Telemetry)",
        ["event_type", "severity"],
    )
else:
    HTTP_REQUESTS_TOTAL = None
    HTTP_REQUEST_DURATION_SECONDS = None
    ACTIVE_USERS_GAUGE = None
    CLINICAL_TRIAGE_TOTAL = None
    AI_CHAT_LATENCY_SECONDS = None
    PRESCRIPTION_SCANS_TOTAL = None
    SYSTEM_MEMORY_LOAD_PERCENT = None
    SECURITY_EVENTS_TOTAL = None


# ==============================================================
# 2. WAZUH SIEM JSON AUDIT STREAM (logs/security_audit.json)
# ==============================================================

_AUDIT_LOG_LOCK = threading.Lock()
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_AUDIT_LOG_PATH = os.path.join(_PROJECT_ROOT, "logs", "security_audit.json")

_MITRE_MAPPING = {
    "LOGIN_FAILED": "T1110.001",
    "LOGIN_BRUTE_FORCE_LOCKED": "T1110",
    "OTP_VERIFY_FAILED": "T1110.001",
    "OAUTH_INVALID_TOKEN": "T1078",
    "ACCOUNT_TAKEOVER_BLOCKED": "T1078.004",
    "MALICIOUS_FILE_UPLOAD_BLOCKED": "T1190",
    "UNHANDLED_SERVER_ERROR": "T1499",
}


def record_security_event(
    event_type: str,
    severity: str = "WARNING",
    client_ip: str = "",
    identifier: str = "",
    endpoint: str = "",
    status_code: int = 0,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Ghi nhận sự kiện bảo mật ra luồng JSON chuẩn Wazuh SIEM (1 JSON/dòng)
    và tăng bộ đếm Prometheus `medimind_security_events_total`.
    Trường `srcip` và `dstuser` tương thích trực tiếp với Wazuh Active Response.
    """
    sev = (severity or "WARNING").upper().strip()
    evt = (event_type or "UNKNOWN_EVENT").upper().strip()

    if PROMETHEUS_AVAILABLE and SECURITY_EVENTS_TOTAL:
        try:
            SECURITY_EVENTS_TOTAL.labels(event_type=evt, severity=sev).inc()
        except Exception:
            pass

    payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "service": "medimind_clinical_ai",
        "event_type": evt,
        "severity": sev,
        "mitre_attack_id": _MITRE_MAPPING.get(evt, ""),
        "srcip": client_ip or "127.0.0.1",
        "dstuser": identifier or "anonymous",
        "endpoint": endpoint,
        "status_code": status_code,
        "details": details or {},
    }

    log_path = os.getenv("SECURITY_AUDIT_LOG_PATH", _DEFAULT_AUDIT_LOG_PATH)
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with _AUDIT_LOG_LOCK:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


# ==============================================================
# 3. SYSTEM MEMORY GAUGE REFRESHER FOR PROMETHEUS
# ==============================================================

def _refresh_memory_gauge() -> None:
    if not (PROMETHEUS_AVAILABLE and SYSTEM_MEMORY_LOAD_PERCENT):
        return
    try:
        if platform.system() == "Windows":
            stat = (ctypes.c_ulonglong * 16)()
            stat[0] = 64
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                mem_percent = ctypes.c_ulong.from_buffer(stat, 4).value
                SYSTEM_MEMORY_LOAD_PERCENT.set(mem_percent)
        else:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                info = {
                    l.split(":")[0]: int(l.split(":")[1].split()[0])
                    for l in f
                    if ":" in l
                }
            total = info.get("MemTotal", 1)
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            SYSTEM_MEMORY_LOAD_PERCENT.set(round((1 - (avail / total)) * 100, 1))
    except Exception:
        pass


# ==============================================================
# 4. METRICS RECORDING HANDLERS
# ==============================================================

def record_http_metrics(
    method: str, endpoint: str, status_code: int, duration_seconds: float
) -> None:
    """Ghi nhận chỉ số HTTP RED (Rate, Errors, Duration) vào Prometheus TSDB."""
    if PROMETHEUS_AVAILABLE and HTTP_REQUESTS_TOTAL:
        try:
            status_str = str(status_code)
            clean_endpoint = endpoint.split("?")[0]
            if len(clean_endpoint) > 40:
                clean_endpoint = clean_endpoint[:38] + "..."
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=clean_endpoint, status=status_str
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=clean_endpoint
            ).observe(duration_seconds)
        except Exception:
            pass


def record_clinical_triage(urgency: str, specialist: str = "Triage") -> None:
    """Ghi nhận phân loại cấp cứu lâm sàng."""
    if PROMETHEUS_AVAILABLE and CLINICAL_TRIAGE_TOTAL:
        try:
            CLINICAL_TRIAGE_TOTAL.labels(
                urgency=urgency, specialist=specialist
            ).inc()
        except Exception:
            pass


def record_ai_latency(
    duration_seconds: float, model: str = "gemini-3.5-flash"
) -> None:
    """Ghi nhận thời gian phản hồi của AI."""
    if PROMETHEUS_AVAILABLE and AI_CHAT_LATENCY_SECONDS:
        try:
            AI_CHAT_LATENCY_SECONDS.labels(model=model).observe(duration_seconds)
        except Exception:
            pass


def record_prescription_scan(status: str = "success") -> None:
    """Ghi nhận chỉ số quét OCR đơn thuốc."""
    if PROMETHEUS_AVAILABLE and PRESCRIPTION_SCANS_TOTAL:
        try:
            PRESCRIPTION_SCANS_TOTAL.labels(status=status).inc()
        except Exception:
            pass


def get_prometheus_metrics_response() -> Response:
    """Trả về phản hồi định dạng text chuẩn OpenMetrics cho Prometheus server."""
    _refresh_memory_gauge()
    if PROMETHEUS_AVAILABLE:
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
    return Response(
        "# Prometheus client is not installed\n", mimetype="text/plain", status=200
    )
