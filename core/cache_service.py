# ==============================================================
# MEDIMIND CLINICAL AI - IN-MEMORY & REDIS CACHE SERVICE
# ==============================================================

import os
import time
import json
from functools import wraps
from typing import Any, Optional, Dict
from flask import request, jsonify

# Khởi tạo kết nối Redis với cơ chế Graceful Fallback
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False


class InMemoryCache:
    """Bộ nhớ đệm trong RAM (In-Memory Dictionary) dự phòng khi không có Redis."""
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        if time.time() > item["expires_at"]:
            del self._store[key]
            return None
        return item["value"]

    def set(self, key: str, value: Any, ttl: int = 60):
        self._store[key] = {
            "value": value,
            "expires_at": time.time() + ttl
        }

    def delete(self, key: str):
        self._store.pop(key, None)

    def delete_pattern(self, pattern: str):
        prefix = pattern.replace("*", "")
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            self._store.pop(k, None)

    def check_rate_limit(self, identifier: str, max_requests: int = 30, window_seconds: int = 60) -> bool:
        """Kiểm tra giới hạn tần suất yêu cầu (Rate Limiting). Trả về True nếu bị chặn."""
        now = time.time()
        key = f"rate_limit:{identifier}"
        record = self._store.get(key)

        if not record or now > record["expires_at"]:
            self._store[key] = {"count": 1, "expires_at": now + window_seconds}
            return False

        if record["count"] >= max_requests:
            return True

        record["count"] += 1
        return False


class CacheService:
    """Hệ thống Caching đa tầng: Tự động dùng Redis nếu có, fallback sang RAM nếu offline."""
    def __init__(self):
        self.redis_client = None
        self.memory_cache = InMemoryCache()
        self._init_redis()

    def _init_redis(self):
        if not REDIS_AVAILABLE:
            print("ℹ️ [Cache Service] Thư viện 'redis' chưa nạp. Đang sử dụng In-Memory Cache nội bộ.")
            return

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            client = redis.from_url(redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
            client.ping()
            self.redis_client = client
            print(f"✅ [Cache Service] Đã kết nối thành công máy chủ Redis ({redis_url}).")
        except Exception as e:
            self.redis_client = None
            print(f"⚠️ [Cache Service] Không thể kết nối Redis ({e}). Tự động kích hoạt In-Memory Cache dự phòng.")

    def get(self, key: str) -> Optional[Any]:
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                return json.loads(data) if data else None
            except Exception:
                pass
        return self.memory_cache.get(key)

    def set(self, key: str, value: Any, ttl: int = 60):
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl, json.dumps(value))
                return
            except Exception:
                pass
        self.memory_cache.set(key, value, ttl)

    def delete(self, key: str):
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception:
                pass
        self.memory_cache.delete(key)

    def delete_pattern(self, pattern: str):
        if self.redis_client:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            except Exception:
                pass
        self.memory_cache.delete_pattern(pattern)

    def is_rate_limited(self, identifier: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
        if self.redis_client:
            try:
                key = f"rate_limit:{identifier}"
                current = self.redis_client.incr(key)
                if current == 1:
                    self.redis_client.expire(key, window_seconds)
                return current > max_requests
            except Exception:
                pass
        return self.memory_cache.check_rate_limit(identifier, max_requests, window_seconds)


# Khởi tạo thể hiện Singleton
cache_service = CacheService()


def cache_response(ttl_seconds: int = 60, key_prefix: str = "view"):
    """Decorator cache kết quả HTTP GET trả về JSON của endpoint."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if request.method != "GET":
                return fn(*args, **kwargs)

            cache_key = f"{key_prefix}:{request.path}:{request.query_string.decode('utf-8')}"
            cached_data = cache_service.get(cache_key)
            if cached_data is not None:
                resp = jsonify(cached_data)
                resp.headers["X-Cache-Status"] = "HIT"
                return resp

            response = fn(*args, **kwargs)
            if isinstance(response, tuple):
                data, status_code = response[0], response[1]
            else:
                data, status_code = response, 200

            if status_code == 200 and hasattr(data, "get_json"):
                json_content = data.get_json()
                if json_content:
                    cache_service.set(cache_key, json_content, ttl=ttl_seconds)

            return response
        return wrapper
    return decorator
