"""Presentation / HTTP Layer (Hybrid Structure 1.4): modular Flask route registration."""

from routes.auth_routes import register_auth_routes
from routes.chat_routes import register_chat_routes
from routes.clinical_routes import register_clinical_routes
from routes.facilities_routes import register_facilities_routes
from routes.nutrition_routes import register_nutrition_routes
from routes.ocr_routes import register_ocr_routes
from routes.system_routes import register_system_routes


def register_all_routes(app, gemini_service):
    """Mount all domain route modules onto the Flask application instance."""
    register_auth_routes(app)
    register_chat_routes(app, gemini_service)
    register_ocr_routes(app)
    register_clinical_routes(app)
    register_nutrition_routes(app)
    register_facilities_routes(app)
    register_system_routes(app)
