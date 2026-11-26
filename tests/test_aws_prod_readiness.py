"""Regression tests for AWS Multi-AZ production readiness:
1. PostgreSQL dialect compatibility in models.py (set_sqlite_pragma) & migrations.py
2. Multi-node shared Redis support with safe In-Memory fallback in OtpManager & RateLimitService
"""
import time
from types import SimpleNamespace
from unittest.mock import patch

from core.auth.otp_service import OtpManager
from core.auth.rate_limit_service import RateLimitService, RedisRateLimitBackend
from core.shared.migrations import MIGRATIONS, _adapt_sql_for_dialect
from core.shared.models import set_sqlite_pragma


class _FakeRedis:
    """Minimal thread-safe Redis mock supporting get/setex/delete/incr/expire/ttl/scan_iter."""

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self._data = {}
        self._expiry = {}

    def _check(self):
        if self.fail:
            raise ConnectionError("Simulated Redis outage")

    def _evict_if_expired(self, key):
        exp = self._expiry.get(key)
        if exp is not None and time.time() > exp:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        self._evict_if_expired(key)
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._check()
        self._data[key] = value
        self._expiry[key] = time.time() + ttl
        return True

    def delete(self, *keys):
        self._check()
        removed = 0
        for k in keys:
            if k in self._data:
                self._data.pop(k, None)
                self._expiry.pop(k, None)
                removed += 1
        return removed

    def incr(self, key):
        self._check()
        self._evict_if_expired(key)
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val

    def expire(self, key, ttl):
        self._check()
        if key in self._data:
            self._expiry[key] = time.time() + ttl
            return True
        return False

    def ttl(self, key):
        self._check()
        self._evict_if_expired(key)
        if key not in self._data:
            return -2
        exp = self._expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - time.time()))

    def scan_iter(self, match="*"):
        self._check()
        prefix = match.rstrip("*")
        return [k for k in list(self._data.keys()) if k.startswith(prefix)]


def test_set_sqlite_pragma_skips_postgres_connection():
    """set_sqlite_pragma must NOT send PRAGMA commands to psycopg2 / PostgreSQL connections."""
    executed = []

    class FakePsycopg2Connection:
        __module__ = "psycopg2.extensions"

        def cursor(self):
            return SimpleNamespace(
                execute=lambda sql: executed.append(sql),
                close=lambda: None,
            )

    set_sqlite_pragma(FakePsycopg2Connection(), None)
    assert executed == [], f"PRAGMA should never be sent to PostgreSQL, got: {executed}"


def test_set_sqlite_pragma_runs_on_sqlite_connection():
    """set_sqlite_pragma must still configure WAL mode on genuine SQLite connections."""
    executed = []

    class FakeSqliteConnection:
        __module__ = "sqlite3"

        def cursor(self):
            return SimpleNamespace(
                execute=lambda sql: executed.append(sql),
                close=lambda: None,
            )

    set_sqlite_pragma(FakeSqliteConnection(), None)
    assert any("journal_mode=WAL" in stmt for stmt in executed)
    assert any("busy_timeout=5000" in stmt for stmt in executed)


def test_migrations_sql_adapts_cleanly_for_postgresql():
    """All raw SQL statements in MIGRATIONS must be free of SQLite-only syntax on PostgreSQL."""
    for version, _desc, sql in MIGRATIONS:
        if not sql:
            continue
        pg_sql = _adapt_sql_for_dialect(sql, "postgresql")
        assert "AUTOINCREMENT" not in pg_sql, f"{version} still contains AUTOINCREMENT on PostgreSQL"
        assert "BOOLEAN DEFAULT 0" not in pg_sql, f"{version} still contains BOOLEAN DEFAULT 0 on PostgreSQL"
        assert "BOOLEAN DEFAULT 1" not in pg_sql, f"{version} still contains BOOLEAN DEFAULT 1 on PostgreSQL"

        sqlite_sql = _adapt_sql_for_dialect(sql, "sqlite")
        assert sqlite_sql == sql


def test_otp_manager_shared_across_two_nodes_via_redis():
    """EC2 #1 issues OTP -> EC2 #2 verifies and consumes it through shared Redis."""
    shared_redis = _FakeRedis()
    node1 = OtpManager(ttl_seconds=120, cooldown_seconds=60, max_attempts=3, redis_client=shared_redis)
    node2 = OtpManager(ttl_seconds=120, cooldown_seconds=60, max_attempts=3, redis_client=shared_redis)

    with patch("core.auth.otp_service.email_service.send_verification_otp", return_value=True):
        ok, _msg, cooldown = node1.request_otp("multi-az@medimind.vn", channel="email", purpose="register")
    assert ok is True
    assert cooldown == 60

    code = node2.get_active_code("multi-az@medimind.vn", channel="email")
    assert code is not None and len(code) == 6

    # Wrong code on node2 increments shared attempt counter
    ok_bad, _ = node2.verify_otp("multi-az@medimind.vn", channel="email", code="000000", purpose="register")
    assert ok_bad is False

    # Valid code on node2 verifies & marks verified in Redis
    ok_good, _ = node2.verify_otp("multi-az@medimind.vn", channel="email", code=code, purpose="register")
    assert ok_good is True

    # Node1 sees verified status and consumes it once
    assert node1.is_verified("multi-az@medimind.vn", channel="email", consume=True) is True
    assert node2.is_verified("multi-az@medimind.vn", channel="email", consume=True) is False


def test_otp_manager_gracefully_falls_back_when_redis_down():
    """If Redis throws a connection error, OtpManager must gracefully fall back to In-Memory."""
    broken_redis = _FakeRedis(fail=True)
    mgr = OtpManager(ttl_seconds=120, cooldown_seconds=60, max_attempts=3, redis_client=broken_redis)

    with patch("core.auth.otp_service.email_service.send_verification_otp", return_value=True):
        ok, _msg, _cd = mgr.request_otp("fallback@medimind.vn", channel="email", purpose="login_2fa")
    assert ok is True
    code = mgr.get_active_code("fallback@medimind.vn", channel="email")
    assert code is not None
    ok_verify, _ = mgr.verify_otp("fallback@medimind.vn", channel="email", code=code, purpose="login_2fa")
    assert ok_verify is True
    assert mgr.is_verified("fallback@medimind.vn", channel="email", consume=True) is True


def test_rate_limit_shared_across_two_nodes_and_fallback():
    """RedisRateLimitBackend enforces shared counters across EC2 nodes and degrades safely."""
    shared_redis = _FakeRedis()
    svc1 = RateLimitService(backend=RedisRateLimitBackend(redis_client=shared_redis))
    svc2 = RateLimitService(backend=RedisRateLimitBackend(redis_client=shared_redis))

    assert svc1.check_login_rate_limit("1.2.3.4", "user@test.vn", max_attempts=3, window_seconds=60) is True
    assert svc2.check_login_rate_limit("1.2.3.4", "user@test.vn", max_attempts=3, window_seconds=60) is True
    assert svc1.check_login_rate_limit("1.2.3.4", "user@test.vn", max_attempts=3, window_seconds=60) is True
    # 4th attempt across nodes must be blocked
    assert svc2.check_login_rate_limit("1.2.3.4", "user@test.vn", max_attempts=3, window_seconds=60) is False

    # Reset from node1 unblocks node2
    svc1.reset_login_attempts("1.2.3.4", "user@test.vn")
    assert svc2.check_login_rate_limit("1.2.3.4", "user@test.vn", max_attempts=3, window_seconds=60) is True

    # Outage fallback test
    broken_svc = RateLimitService(backend=RedisRateLimitBackend(redis_client=_FakeRedis(fail=True)))
    assert broken_svc.check_login_rate_limit("9.9.9.9", "x@test.vn", max_attempts=1, window_seconds=60) is True
    assert broken_svc.check_login_rate_limit("9.9.9.9", "x@test.vn", max_attempts=1, window_seconds=60) is False
