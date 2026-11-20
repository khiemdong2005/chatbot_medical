"""
================================================================================
🩺 MEDIMIND LOCAL OBSERVABILITY & METRICS REGISTRY
================================================================================
Mục đích:
  - Hệ thống Registry quan sát và giám sát sức khỏe runtime hoàn toàn cục bộ (Local),
    bảo vệ quyền riêng tư tuyệt đối (Zero-PHI), không phụ thuộc vào bất kỳ dịch vụ Cloud nào.
  - Theo dõi đa chiều:
      + Request counters: Total, Success, Fallback, Emergency Short-circuits.
      + Retrieval counters: Success, Miss, BM25 Only, Query Expansion Used/Degraded.
      + Query Expansion counters: Attempts, Success, Failure, Cache Hit.
      + AI & Gemini counters: Requests, Success, Retries, 429 Rate Limits, 5xx Server Errors, Timeouts.
      + Circuit Breaker state: State, Consecutive Failures, Cooldown Remaining.
      + Safety & Guardrails: Emergency Short-circuits, Unsafe Blocks (Prescription/Overconfident).
      + Error Classification breakdown: AUTH_ERROR, RATE_LIMIT, SERVER_ERROR, TIMEOUT, NETWORK_ERROR, SCHEMA_ERROR, UNKNOWN.
      + Stage Latencies: Bounded rolling window (mặc định 1000 mẫu) tính Count, Mean, P50, P95, Min, Max.
  - Ngưỡng đánh giá sức khỏe (Health & Readiness):
      + HEALTHY / READY: RAG hoạt động bình thường, Circuit Breaker CLOSED, tỉ lệ lỗi thấp.
      + DEGRADED: Circuit Breaker OPEN, hoặc Fallback Rate > 20%, hoặc 429 Rate > 10%.
      + NOT_READY: RAG collection không khả dụng hoặc chưa khởi tạo.
================================================================================
"""

import os
import math
import time
import logging
import threading
from collections import deque
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("Observability")

# Giới hạn kích thước rolling window để bảo vệ bộ nhớ RAM
DEFAULT_WINDOW_SIZE = 1000


class LocalMetricsRegistry:
    """
    Registry lưu trữ và tổng hợp metrics runtime Thread-Safe cho môi trường Local.
    """

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE):
        self._lock = threading.Lock()
        self.window_size = max(100, window_size)
        self.enabled = os.getenv("SYSTEM_METRICS_ENABLED", "true").lower() in ("1", "true", "yes")

        # 1. Bộ đếm định lượng (Deterministic Counters)
        self._counters: Dict[str, int] = {
            # Requests
            "requests_total": 0,
            "requests_success": 0,
            "requests_fallback": 0,
            "emergency_short_circuit_total": 0,

            # Retrieval
            "retrieval_success_total": 0,
            "retrieval_miss_total": 0,
            "retrieval_bm25_only_total": 0,
            "retrieval_query_expansion_used_total": 0,
            "retrieval_query_expansion_degraded_total": 0,
            "retrieval_no_results_total": 0,

            # Query Expansion
            "query_expansion_attempt_total": 0,
            "query_expansion_success_total": 0,
            "query_expansion_failure_total": 0,
            "query_expansion_cache_hit_total": 0,

            # AI & Gemini Provider
            "gemini_request_total": 0,
            "gemini_success_total": 0,
            "retry_total": 0,
            "rate_limit_429_total": 0,
            "server_error_5xx_total": 0,
            "timeout_total": 0,
            "circuit_breaker_open_total": 0,
            "llm_request_total": 0,
            "llm_success_total": 0,
            "llm_failure_total": 0,
            "llm_retry_total": 0,

            # Safety Guardrails
            "unsafe_guardrail_block_total": 0,

            # Error Classification Breakdown
            "error_auth_total": 0,
            "error_rate_limit_total": 0,
            "error_server_error_total": 0,
            "error_timeout_total": 0,
            "error_network_error_total": 0,
            "error_schema_error_total": 0,
            "error_unknown_total": 0,

            # Backward-compatibility legacy counters
            "ai_request_count": 0,
            "ai_success_count": 0,
            "ai_retry_count": 0,
            "ai_fallback_count": 0,
            "ai_429_count": 0,
            "ai_5xx_count": 0,
            "ai_timeout_count": 0,
            "circuit_open_count": 0,
            "query_expansion_success": 0,
            "query_expansion_failure": 0,
        }

        # 2. Bounded Rolling Window cho độ trễ từng stage (Tránh phình RAM vô hạn)
        self._latencies: Dict[str, deque] = {
            "triage_latency_ms": deque(maxlen=self.window_size),
            "query_expansion_latency_ms": deque(maxlen=self.window_size),
            "retrieval_latency_ms": deque(maxlen=self.window_size),
            "generation_latency_ms": deque(maxlen=self.window_size),
            "guardrail_latency_ms": deque(maxlen=self.window_size),
            "total_request_latency_ms": deque(maxlen=self.window_size),
            "attempt_count": deque(maxlen=self.window_size),
        }

        self._start_time = time.time()

    def is_enabled(self) -> bool:
        return self.enabled

    def increment(self, counter_name: str, value: int = 1):
        """
        Tăng bộ đếm chỉ định, hỗ trợ mapping tương thích ngược và phân loại lỗi.
        """
        if not self.enabled or value <= 0:
            return

        with self._lock:
            # Tăng counter chính
            if counter_name in self._counters:
                self._counters[counter_name] += value
            else:
                self._counters[counter_name] = value

            # Đồng bộ các alias tương thích ngược (Bi-directional mapping)
            alias_map = {
                "ai_request_count": "gemini_request_total",
                "gemini_request_total": "ai_request_count",
                "llm_request_total": "gemini_request_total",
                "ai_success_count": "gemini_success_total",
                "gemini_success_total": "ai_success_count",
                "llm_success_total": "gemini_success_total",
                "ai_retry_count": "retry_total",
                "retry_total": "ai_retry_count",
                "llm_retry_total": "retry_total",
                "ai_fallback_count": "requests_fallback",
                "requests_fallback": "ai_fallback_count",
                "llm_failure_total": "requests_fallback",
                "ai_429_count": "rate_limit_429_total",
                "rate_limit_429_total": "ai_429_count",
                "ai_5xx_count": "server_error_5xx_total",
                "server_error_5xx_total": "ai_5xx_count",
                "ai_timeout_count": "timeout_total",
                "timeout_total": "ai_timeout_count",
                "circuit_open_count": "circuit_breaker_open_total",
                "circuit_breaker_open_total": "circuit_open_count",
                "query_expansion_success": "query_expansion_success_total",
                "query_expansion_success_total": "query_expansion_success",
                "query_expansion_failure": "query_expansion_failure_total",
                "query_expansion_failure_total": "query_expansion_failure",
            }
            mapped_alias = alias_map.get(counter_name)
            if mapped_alias and mapped_alias in self._counters:
                self._counters[mapped_alias] += value

            # Tự động đồng bộ sang error classification breakdown
            if counter_name in ("rate_limit_429_total", "ai_429_count"):
                self._counters["error_rate_limit_total"] += value
            elif counter_name in ("server_error_5xx_total", "ai_5xx_count"):
                self._counters["error_server_error_total"] += value
            elif counter_name in ("timeout_total", "ai_timeout_count"):
                self._counters["error_timeout_total"] += value

    def record_error(self, error_class: str, value: int = 1):
        """Ghi nhận lỗi theo bảng phân loại ErrorClassification."""
        if not self.enabled or value <= 0:
            return
        mapping = {
            "AUTH_ERROR": "error_auth_total",
            "RATE_LIMIT": "error_rate_limit_total",
            "SERVER_ERROR": "error_server_error_total",
            "TIMEOUT": "error_timeout_total",
            "NETWORK_ERROR": "error_network_error_total",
            "SCHEMA_ERROR": "error_schema_error_total",
            "UNKNOWN": "error_unknown_total",
        }
        target_counter = mapping.get(str(error_class).upper(), "error_unknown_total")
        self.increment(target_counter, value)

    def record_latency(self, stage: str, latency_ms: float):
        """
        Ghi nhận độ trễ (milliseconds) vào bounded rolling window.
        """
        if not self.enabled or not math.isfinite(latency_ms) or latency_ms < 0:
            return

        with self._lock:
            if stage not in self._latencies:
                self._latencies[stage] = deque(maxlen=self.window_size)
            self._latencies[stage].append(latency_ms)

    def record_attempts(self, attempts: int):
        """Ghi nhận số lần retry/thử của request."""
        self.record_latency("attempt_count", float(attempts))

    @staticmethod
    def _compute_percentile(sorted_list: List[float], percentile: float) -> float:
        if not sorted_list:
            return 0.0
        k = (len(sorted_list) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_list[int(k)]
        d0 = sorted_list[int(f)] * (c - k)
        d1 = sorted_list[int(c)] * (k - f)
        return d0 + d1

    def get_summary(self) -> Dict[str, Any]:
        """
        Tổng hợp toàn bộ chỉ số metrics, độ trễ và trạng thái sức khỏe hệ thống.
        Không chứa bất kỳ thông tin nhận dạng người bệnh (Zero-PHI).
        """
        with self._lock:
            counters_copy = dict(self._counters)
            latencies_summary = {}

            for stage, dq in self._latencies.items():
                if not dq:
                    latencies_summary[stage] = {
                        "count": 0,
                        "mean": 0.0,
                        "p50": 0.0,
                        "p95": 0.0,
                        "min": 0.0,
                        "max": 0.0
                    }
                else:
                    sorted_vals = sorted(dq)
                    mean_val = sum(sorted_vals) / len(sorted_vals)
                    latencies_summary[stage] = {
                        "count": len(sorted_vals),
                        "mean": round(mean_val, 2),
                        "p50": round(self._compute_percentile(sorted_vals, 50), 2),
                        "p95": round(self._compute_percentile(sorted_vals, 95), 2),
                        "min": round(sorted_vals[0], 2),
                        "max": round(sorted_vals[-1], 2)
                    }

        # 3. Trạng thái Circuit Breaker
        from core.circuit_breaker import gemini_circuit_breaker
        cb_status = gemini_circuit_breaker.get_status()

        # 4. Tính toán tỉ lệ phần trăm & Trạng thái Sức khỏe
        req_total = counters_copy["requests_total"]
        req_success = counters_copy["requests_success"]
        req_fallback = counters_copy["requests_fallback"]
        fallback_rate_pct = round((req_fallback / req_total * 100.0), 2) if req_total > 0 else 0.0

        ai_req = counters_copy["gemini_request_total"]
        ai_succ = counters_copy["gemini_success_total"]
        ai_success_rate_pct = round((ai_succ / ai_req * 100.0), 2) if ai_req > 0 else 100.0
        ai_429_count = counters_copy["rate_limit_429_total"]
        ai_429_rate_pct = round((ai_429_count / ai_req * 100.0), 2) if ai_req > 0 else 0.0

        retrieval_success = counters_copy["retrieval_success_total"]
        retrieval_miss = counters_copy["retrieval_miss_total"]
        retrieval_total = retrieval_success + retrieval_miss
        retrieval_success_rate_pct = round((retrieval_success / retrieval_total * 100.0), 2) if retrieval_total > 0 else 100.0

        exp_attempts = counters_copy["query_expansion_attempt_total"]
        exp_cache_hits = counters_copy["query_expansion_cache_hit_total"]
        exp_cache_hit_rate_pct = round((exp_cache_hits / exp_attempts * 100.0), 2) if exp_attempts > 0 else 0.0

        # Kiểm tra trạng thái RAG
        from core.rag_service import medical_rag_service
        rag_available = medical_rag_service.is_available()

        # Đánh giá Health Status theo ngưỡng quy định
        # - RAG không khả dụng -> NOT_READY
        # - Circuit OPEN hoặc Fallback > 20% hoặc 429 > 10% -> DEGRADED
        # - Ngược lại -> HEALTHY / READY
        if not rag_available:
            system_status = "NOT_READY"
            rag_status = "NOT_READY"
        else:
            rag_status = "READY"
            is_degraded = (
                cb_status.get("state") == "OPEN" or
                (req_total >= 5 and fallback_rate_pct > 20.0) or
                (ai_req >= 5 and ai_429_rate_pct > 10.0)
            )
            system_status = "DEGRADED" if is_degraded else "READY"

        gemini_status = "DEGRADED" if cb_status.get("state") == "OPEN" else "READY"

        uptime_seconds = round(time.time() - self._start_time, 1)

        return {
            "status": system_status,
            "uptime_seconds": uptime_seconds,
            "components": {
                "rag": rag_status,
                "gemini": gemini_status,
                "circuit_breaker": cb_status.get("state", "CLOSED"),
            },
            "requests": {
                "total": req_total,
                "success": req_success,
                "fallback": req_fallback,
                "fallback_rate_pct": fallback_rate_pct,
                "emergency_short_circuit": counters_copy["emergency_short_circuit_total"],
            },
            "ai": {
                "requests_total": ai_req,
                "success_total": ai_succ,
                "success_rate_pct": ai_success_rate_pct,
                "retries_total": counters_copy["retry_total"],
                "rate_limit_429": ai_429_count,
                "rate_limit_429_rate_pct": ai_429_rate_pct,
                "server_error_5xx": counters_copy["server_error_5xx_total"],
                "timeout": counters_copy["timeout_total"],
            },
            "retrieval": {
                "success": retrieval_success,
                "miss": retrieval_miss,
                "success_rate_pct": retrieval_success_rate_pct,
                "provenance": {
                    "bm25_only": counters_copy["retrieval_bm25_only_total"],
                    "query_expansion_used": counters_copy["retrieval_query_expansion_used_total"],
                    "query_expansion_degraded": counters_copy["retrieval_query_expansion_degraded_total"],
                    "no_results": counters_copy["retrieval_no_results_total"],
                }
            },
            "query_expansion": {
                "attempts": exp_attempts,
                "success": counters_copy["query_expansion_success_total"],
                "failure": counters_copy["query_expansion_failure_total"],
                "cache_hits": exp_cache_hits,
                "cache_hit_rate_pct": exp_cache_hit_rate_pct,
            },
            "safety": {
                "emergency_short_circuits": counters_copy["emergency_short_circuit_total"],
                "unsafe_guardrail_blocks": counters_copy["unsafe_guardrail_block_total"],
            },
            "circuit_breaker": {
                "state": cb_status.get("state", "CLOSED"),
                "failure_count": cb_status.get("consecutive_failures", 0),
                "failure_threshold": cb_status.get("failure_threshold", 5),
                "cooldown_remaining": cb_status.get("cooldown_remaining", 0.0),
            },
            "errors": {
                "AUTH_ERROR": counters_copy["error_auth_total"],
                "RATE_LIMIT": counters_copy["error_rate_limit_total"],
                "SERVER_ERROR": counters_copy["error_server_error_total"],
                "TIMEOUT": counters_copy["error_timeout_total"],
                "NETWORK_ERROR": counters_copy["error_network_error_total"],
                "SCHEMA_ERROR": counters_copy["error_schema_error_total"],
                "UNKNOWN": counters_copy["error_unknown_total"],
            },
            "latency": latencies_summary,
            "latencies": latencies_summary,
            "counters": counters_copy,
        }

    def reset(self):
        """Đặt lại toàn bộ số liệu thống kê về trạng thái ban đầu."""
        with self._lock:
            for k in self._counters:
                self._counters[k] = 0
            for k in self._latencies:
                self._latencies[k].clear()
            self._start_time = time.time()

    def log_event(
        self,
        stage: str,
        request_id: str,
        latency_ms: float,
        status: str,
        error_class: Optional[str] = None,
        retry_count: int = 0,
        query_hash: Optional[str] = None
    ):
        """
        Ghi log có cấu trúc bảo vệ quyền riêng tư (Privacy-Safe Structured Logging).
        Tuyệt đối không log nội dung câu hỏi thô hay thông tin y tế bệnh nhân.
        """
        parts = [
            f"[OBSERVABILITY]",
            f"req_id={request_id}",
            f"stage={stage}",
            f"status={status}",
            f"latency_ms={latency_ms:.2f}",
            f"retries={retry_count}"
        ]
        if error_class:
            parts.append(f"error={error_class}")
        if query_hash:
            parts.append(f"hash={query_hash[:8]}")

        logger.info(" ".join(parts))


# Singleton instance dùng chung
metrics_collector = LocalMetricsRegistry()
MetricsCollector = LocalMetricsRegistry  # Alias tương thích ngược


# ==============================================================
# HYBRID SECURITY OBSERVABILITY & SIEM (PROMETHEUS + WAZUH)
# ==============================================================

import ctypes
import datetime
import json
import platform
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

