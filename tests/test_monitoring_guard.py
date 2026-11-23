"""
Kiểm thử tự động phân khu Hybrid Security Observability (Prometheus OpenMetrics + Wazuh SIEM JSON)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from core.models import db
from core.observability import record_security_event


class TestObservabilityGuard(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def test_removed_legacy_cockpit_routes_return_404(self):
        self.assertEqual(self.client.get("/monitoring").status_code, 404)
        self.assertEqual(self.client.get("/api/monitoring/status").status_code, 404)

    def test_prometheus_metrics_loopback_and_security_counters(self):
        record_security_event(
            event_type="LOGIN_FAILED",
            severity="WARNING",
            client_ip="127.0.0.1",
            identifier="attacker@test.com",
            endpoint="/api/auth/login",
            status_code=401,
        )
        res = self.client.get("/metrics")
        self.assertEqual(res.status_code, 200)
        body = res.data.decode("utf-8")
        self.assertIn("medimind_http_requests_total", body)
        self.assertIn("medimind_security_events_total", body)
        self.assertIn('event_type="LOGIN_FAILED"', body)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_prometheus_metrics_blocks_external_ip_without_token(self):
        self.assertEqual(self.client.get("/metrics", environ_base={"REMOTE_ADDR": "203.0.113.55"}).status_code, 403)
        self.assertEqual(self.client.get("/metrics", environ_base={"REMOTE_ADDR": "172.67.10.20"}).status_code, 403)
        self.assertEqual(self.client.get("/metrics", environ_base={"REMOTE_ADDR": "172.16.0.10"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
