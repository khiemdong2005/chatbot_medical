"""Core UI entrypoint, OpenAPI docs and health/readiness routes."""

import os

from flask import jsonify, render_template, session

from routes.shared_helpers import get_request_identity as _get_request_identity


def register_system_routes(app):
    # GIAO DIỆN NGƯỜI DÙNG WEB (UI)
    # ==============================================================

    def _is_production_mode() -> bool:
        from core.shared.settings import get_settings
        env_val = (os.getenv("ENV") or os.getenv("FLASK_ENV") or "").strip().lower()
        if env_val in ("production", "prod"):
            return True
        if env_val in ("development", "dev", "testing", "test"):
            return False
        return bool(get_settings().server.is_production)

    @app.get("/openapi.json")
    def api_spec():
        if _is_production_mode():
            return jsonify({"error": "Not Found"}), 404
        import re

        paths = {}
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/"):
                continue
            path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule)
            parameters = [
                {"name": name, "in": "path", "required": True,
                 "schema": {"type": "integer" if f"<int:{name}>" in rule.rule else "string"}}
                for name in sorted(rule.arguments)
            ]
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                paths.setdefault(path, {})[method.lower()] = {
                    "tags": [path.split("/")[2]],
                    "summary": (app.view_functions[rule.endpoint].__doc__ or rule.endpoint).strip().splitlines()[0],
                    "parameters": parameters,
                    "responses": {"default": {"description": "Phản hồi từ API"}},
                }
        return jsonify(openapi="3.0.3", info={"title": "MediMind Flask API", "version": "1"}, paths=paths)

    @app.get("/docs")
    def api_docs():
        if _is_production_mode():
            return jsonify({"error": "Not Found"}), 404
        return render_template("api_docs.html", paths=api_spec().get_json()["paths"])


    @app.route("/")
    def index():
        """Trang chủ ứng dụng y tế MediMind."""
        # Establish the guest cookie before a chat request and a draft read can overlap.
        if not session.get("user_id"):
            _get_request_identity()
        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        return render_template("index.html", google_maps_api_key=google_maps_api_key)

    @app.route("/health")
    def health_check():
        return jsonify({"status": "ok"})

    @app.route("/ready")
    def readiness_check():
        from core.chat.rag_service import medical_rag_service
        from core.ai.circuit_breaker import gemini_circuit_breaker
        rag_ready = medical_rag_service.is_available()
        cb_status = gemini_circuit_breaker.get_status()
        cb_state = cb_status.get("state", "CLOSED")
        gemini_status = "degraded" if cb_state == "OPEN" else "ready"
        rag_status = "ready" if rag_ready else "not_ready"
        if not rag_ready:
            overall = "not_ready"
            code = 503
        elif cb_state == "OPEN":
            overall = "degraded"
            code = 200
        else:
            overall = "ready"
            code = 200
        return jsonify({
            "status": overall,
            "rag": rag_status,
            "gemini": gemini_status,
            "circuit_breaker": cb_state
        }), code

