"""
================================================================================
🩺 MEDIMIND CROSS-LANGUAGE QUERY EXPANSION SERVICE
================================================================================
Mục đích:
  - Mở rộng câu hỏi y tế tiếng Việt sang thuật ngữ tìm kiếm tiếng Anh súc tích
    để giải quyết bài toán Lexical Mismatch với kho y văn tiếng Anh (MedlinePlus/NIH).
  - Tách biệt hoàn toàn khỏi logic điều phối chat (Separation of Concerns).
  - Fallback an toàn: Khi timeout, lỗi mạng, quota 429/500/503 -> tự động dùng câu gốc.
  - Bounded LRU Cache với khóa băm SHA256: Tăng tốc và bảo mật dữ liệu riêng tư.
  - Tuyệt đối không log thông tin truy vấn y khoa thô của người bệnh trong production.
================================================================================
"""

import os
import re
import time
import json
import uuid
import hashlib
import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from core.retry_policy import (
    RetryPolicy, execute_with_retry, classify_exception, ErrorClassification
)
from core.circuit_breaker import gemini_circuit_breaker, CircuitBreakerOpenError
from core.observability import metrics_collector
from core.settings import settings

load_dotenv()
logger = logging.getLogger("QueryExpansionService")

# Cấu hình mặc định từ Central Settings (có dự phòng đọc env trực tiếp nếu patched)
DEFAULT_EXPANSION_ENABLED = (
    os.getenv("RAG_QUERY_EXPANSION_ENABLED", "true" if settings.rag.query_expansion_enabled else "false").lower() in ("1", "true", "yes")
)
DEFAULT_EXPANSION_PROVIDER = os.getenv("RAG_QUERY_EXPANSION_PROVIDER", settings.rag.query_expansion_provider).lower()
DEFAULT_EXPANSION_TIMEOUT = float(
    os.getenv("QUERY_EXPANSION_TIMEOUT_SECONDS") or os.getenv("RAG_QUERY_EXPANSION_TIMEOUT_SECONDS") or str(settings.rag.query_expansion_timeout_seconds)
)
DEFAULT_EXPANSION_MODEL = os.getenv("RAG_QUERY_EXPANSION_MODEL", settings.gemini.expansion_model)


@dataclass
class ExpandedQuery:
    """Cấu trúc dữ liệu kết quả mở rộng truy vấn."""
    original_query: str
    expanded_query: str
    used_expansion: bool
    provider: str
    degraded: bool
    latency_ms: float = 0.0
    cached: bool = False


class QueryExpansionProvider(ABC):
    """Giao diện trừu tượng cho các nhà cung cấp dịch vụ mở rộng truy vấn."""

    @abstractmethod
    def expand(self, query: str, timeout_seconds: float = 3.0) -> str:
        """
        Chuyển đổi truy vấn tìm kiếm y tế tiếng Việt thành các thuật ngữ tìm kiếm tiếng Anh.
        Nếu lỗi hoặc không chuyển đổi được, trả về chuỗi rỗng.
        """
        pass


class GeminiQueryExpansionProvider(QueryExpansionProvider):
    """Nhà cung cấp mở rộng truy vấn sử dụng Google Gemini API qua Unified LLM Provider."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from core.llm_provider import llm_provider
        self.llm_provider = llm_provider
        self.api_key = (api_key or self.llm_provider.resolve_api_key(profile="query_expansion")).strip()
        self.model = model or DEFAULT_EXPANSION_MODEL
        self._client = None

    @property
    def client(self):
        if self._client is not None:
            return self._client
        if self.is_available():
            try:
                return self.llm_provider.get_client(self.api_key)
            except Exception:
                return None
        return None

    @client.setter
    def client(self, val):
        self._client = val

    def is_available(self) -> bool:
        return self.llm_provider.is_configured(profile="query_expansion", explicit_key=self.api_key)

    def expand(self, query: str, timeout_seconds: float = 3.0) -> str:
        if not self.is_available():
            return ""

        system_instruction = (
            "Convert this Vietnamese medical search query into a concise English medical retrieval query.\n\n"
            "Rules:\n"
            "- Return English medical search terms only.\n"
            "- Do not answer the question.\n"
            "- Do not diagnose.\n"
            "- Do not add medical advice.\n"
            "- Preserve symptoms, medications, disease names and negation.\n"
            "- If a symptom is negated or denied (e.g. 'không sốt', 'không khó thở'), do not include it as an affirmative search term.\n"
            "- Keep the result concise (e.g., 'Tôi bị đau ngực và khó thở' -> 'chest pain shortness of breath')."
        )

        prompt = f"Medical query: {query.strip()[:1000]}"

        try:
            from core.llm_provider import LLMProviderError
            response_text = self.llm_provider.generate_text(
                prompt=prompt,
                model=self.model,
                system_instruction=system_instruction,
                temperature=0.0,
                max_output_tokens=60,
                timeout_seconds=timeout_seconds,
                operation="query_expansion",
                api_key=self.api_key,
                circuit_breaker=gemini_circuit_breaker
            )
            if not response_text:
                return ""

            cleaned = response_text.strip()
            # Loại bỏ định dạng markdown hoặc dấu ngoặc kép thừa
            cleaned = re.sub(r"^[`'\"]+|[`'\"]+$", "", cleaned).strip()
            cleaned = re.sub(r"\s+", " ", cleaned).lower()
            return cleaned[:300]
        except CircuitBreakerOpenError:
            logger.warning("Gemini expansion skipped because Circuit Breaker is OPEN.")
            return ""
        except Exception as e:
            cls = classify_exception(e)
            logger.warning("Gemini expansion call failed (%s: %s).", cls.value, type(e).__name__)
            return ""


class QueryExpansionService:
    """
    Dịch vụ quản lý mở rộng truy vấn đa ngôn ngữ có cache và cơ chế phòng thủ (Resilience).
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        provider_name: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        provider: Optional[QueryExpansionProvider] = None,
        cache_size: int = 500
    ):
        self.enabled = DEFAULT_EXPANSION_ENABLED if enabled is None else bool(enabled)
        self.provider_name = (provider_name or DEFAULT_EXPANSION_PROVIDER).lower()
        self.timeout_seconds = DEFAULT_EXPANSION_TIMEOUT if timeout_seconds is None else float(timeout_seconds)
        self.cache_size = max(1, cache_size)
        self._cache: OrderedDict[str, str] = OrderedDict()

        if provider is not None:
            self.provider = provider
        elif self.provider_name == "gemini":
            self.provider = GeminiQueryExpansionProvider()
        else:
            self.provider = GeminiQueryExpansionProvider()

    def _hash_key(self, text: str) -> str:
        """Tạo khóa hash SHA-256 an toàn từ chuỗi truy vấn đã chuẩn hóa."""
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _get_from_cache(self, key_hash: str) -> Optional[str]:
        if key_hash in self._cache:
            self._cache.move_to_end(key_hash)
            return self._cache[key_hash]
        return None

    def _put_to_cache(self, key_hash: str, value: str):
        if key_hash in self._cache:
            self._cache.move_to_end(key_hash)
        self._cache[key_hash] = value
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def clear_cache(self):
        """Xóa sạch bộ nhớ đệm."""
        self._cache.clear()

    def expand_for_retrieval(
        self,
        query: str,
        language: str = "vi"
    ) -> ExpandedQuery:
        """
        Mở rộng câu truy vấn để phục vụ tìm kiếm y văn đa ngôn ngữ.
        
        Quy tắc an toàn:
        - Nếu tính năng bị tắt -> bỏ qua (used_expansion=False).
        - Nếu ngôn ngữ không phải tiếng Việt (ví dụ tiếng Anh) -> bỏ qua (used_expansion=False).
        - Nếu query rỗng -> bỏ qua (used_expansion=False).
        - Nếu cache hit -> trả về ngay lập tức (cached=True).
        - Nếu gọi provider thất bại/timeout -> fallback về query gốc (degraded=True, used_expansion=False).
        - Tuyệt đối không làm crash pipeline retrieval.
        """
        start_time = time.perf_counter()

        if not isinstance(query, str) or not query.strip():
            return ExpandedQuery(
                original_query="" if query is None else query,
                expanded_query="" if query is None else query,
                used_expansion=False,
                provider="none",
                degraded=False,
                latency_ms=0.0
            )

        trimmed_query = query.strip()

        # Chỉ áp dụng mở rộng khi tính năng được bật
        if not self.enabled:
            return ExpandedQuery(
                original_query=trimmed_query,
                expanded_query=trimmed_query,
                used_expansion=False,
                provider="disabled",
                degraded=False,
                latency_ms=0.0
            )

        # Chỉ mở rộng cho tiếng Việt, tiếng Anh đã khớp trực tiếp với kho y văn
        if language != "vi":
            return ExpandedQuery(
                original_query=trimmed_query,
                expanded_query=trimmed_query,
                used_expansion=False,
                provider="bypassed",
                degraded=False,
                latency_ms=0.0
            )

        metrics_collector.increment("query_expansion_attempt_total")

        # 1. Kiểm tra Cache
        key_hash = self._hash_key(trimmed_query)
        cached_result = self._get_from_cache(key_hash)
        if cached_result:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            metrics_collector.increment("query_expansion_cache_hit_total")
            metrics_collector.increment("query_expansion_success_total")
            logger.debug("Query expansion cache hit (latency: %.2f ms)", latency_ms)
            return ExpandedQuery(
                original_query=trimmed_query,
                expanded_query=cached_result,
                used_expansion=True,
                provider=self.provider_name,
                degraded=False,
                latency_ms=round(latency_ms, 2),
                cached=True
            )

        # 2. Gọi Provider với cơ chế Fallback an toàn
        try:
            expansion = self.provider.expand(trimmed_query, timeout_seconds=self.timeout_seconds)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            if expansion and expansion.strip():
                final_expansion = expansion.strip()
                self._put_to_cache(key_hash, final_expansion)
                metrics_collector.increment("query_expansion_success")
                metrics_collector.record_latency("query_expansion_latency_ms", latency_ms)
                metrics_collector.log_event("query_expansion", "exp", latency_ms, "SUCCESS", query_hash=key_hash)
                logger.info(
                    "Query expansion success (provider=%s, latency_ms=%.2f, cached=False)",
                    self.provider_name, latency_ms
                )
                return ExpandedQuery(
                    original_query=trimmed_query,
                    expanded_query=final_expansion,
                    used_expansion=True,
                    provider=self.provider_name,
                    degraded=False,
                    latency_ms=round(latency_ms, 2),
                    cached=False
                )
            else:
                # Provider trả về rỗng -> Fallback
                metrics_collector.increment("query_expansion_failure")
                metrics_collector.record_latency("query_expansion_latency_ms", latency_ms)
                metrics_collector.log_event("query_expansion", "exp", latency_ms, "FALLBACK", query_hash=key_hash)
                logger.warning(
                    "Query expansion returned empty; falling back to original query (latency_ms=%.2f)",
                    latency_ms
                )
                return ExpandedQuery(
                    original_query=trimmed_query,
                    expanded_query=trimmed_query,
                    used_expansion=False,
                    provider=self.provider_name,
                    degraded=True,
                    latency_ms=round(latency_ms, 2),
                    cached=False
                )
        except Exception as err:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            metrics_collector.increment("query_expansion_failure")
            metrics_collector.record_latency("query_expansion_latency_ms", latency_ms)
            metrics_collector.log_event("query_expansion", "exp", latency_ms, "FALLBACK", error_class=type(err).__name__, query_hash=key_hash)
            logger.warning(
                "Query expansion exception (%s); falling back to original query (latency_ms=%.2f)",
                type(err).__name__, latency_ms
            )
            return ExpandedQuery(
                original_query=trimmed_query,
                expanded_query=trimmed_query,
                used_expansion=False,
                provider=self.provider_name,
                degraded=True,
                latency_ms=round(latency_ms, 2),
                cached=False
            )


# Thể hiện Singleton dùng chung trong toàn ứng dụng
query_expansion_service = QueryExpansionService()
