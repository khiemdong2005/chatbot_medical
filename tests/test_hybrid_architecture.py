"""Architectural contract tests for Hybrid Structure 1.4 (Modular Monolith).

Enforces:
1. All 7 Hybrid subpackages exist under ``core/`` and legacy ``core.<mod>`` shims
   alias the exact same module object (``is``) with zero split-brain state.
2. Unidirectional dependency boundaries:
   - ``core/shared/*`` never imports domain modules or ``routes.*``.
   - Domain/platform modules under ``core/`` never import ``routes.*``.
3. Thin Entrypoint invariant: ``app.py`` stays concise and delegates HTTP endpoints
   to modular domain route files under ``routes/``.
4. Endpoint parity: all expected Flask routes remain registered after extraction.
"""

import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HYBRID_MODULE_MAP = {
    "shared": (
        "settings",
        "models",
        "migrations",
        "db_utils",
        "cache_service",
        "storage_service",
        "cleanup_service",
        "api_errors",
        "logging_redaction",
        "network_utils",
    ),
    "auth": (
        "otp_service",
        "csrf_protection",
        "rate_limit_service",
        "security_headers",
        "security_patch",
        "email_service",
        "sms_service",
    ),
    "ai": (
        "ai_types",
        "llm_provider",
        "gemini_service",
        "interpretation_service",
        "prompts",
        "circuit_breaker",
        "retry_policy",
    ),
    "chat": (
        "chat_service",
        "consultation_service",
        "intake_service",
        "triage",
        "health_context",
        "rag_service",
        "document_chunker",
        "query_expansion_service",
        "reranker_service",
        "grounding_service",
    ),
    "ocr": (
        "ocr_extractor",
        "ocr_parallel_service",
        "pipeline_orchestrator",
        "preprocessing_service",
        "image_preprocessor",
        "prescription_crop_service",
        "prescription_service",
        "reconciliation_service",
        "gemini_schema_service",
        "validation_service",
    ),
    "nutrition": (
        "nutrition_ai",
        "nutrition_options",
        "nutrition_rules",
        "nutrition_service",
        "recipe_catalog",
        "recipe_features",
    ),
    "facilities": (
        "facilities_service",
        "appointment_service",
    ),
}

EXPECTED_ROUTE_MODULES = (
    "__init__.py",
    "shared_helpers.py",
    "auth_routes.py",
    "chat_routes.py",
    "ocr_routes.py",
    "clinical_routes.py",
    "nutrition_routes.py",
    "facilities_routes.py",
    "system_routes.py",
)

DOMAIN_PACKAGES = ("chat", "ocr", "nutrition", "facilities", "routers")


def _extract_imported_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_hybrid_subpackages_and_shim_identity():
    """Every canonical Hybrid module exists and its legacy core.<mod> alias is identical."""
    for subpkg, modules in HYBRID_MODULE_MAP.items():
        pkg_dir = ROOT / "core" / subpkg
        assert (pkg_dir / "__init__.py").is_file(), f"Missing package __init__.py in {pkg_dir}"
        for mod in modules:
            canonical_path = pkg_dir / f"{mod}.py"
            assert canonical_path.is_file(), f"Missing canonical module {canonical_path}"
            canonical_mod = importlib.import_module(f"core.{subpkg}.{mod}")
            legacy_mod = importlib.import_module(f"core.{mod}")
            assert legacy_mod is canonical_mod, (
                f"Split-brain module detected: core.{mod} is not core.{subpkg}.{mod}"
            )


def test_unidirectional_dependency_boundaries():
    """Shared kernel must not import domains; core subpackages must not import routes/."""
    violations: list[tuple[str, str, str]] = []
    for subpkg in HYBRID_MODULE_MAP:
        for py_file in sorted((ROOT / "core" / subpkg).glob("*.py")):
            imports = _extract_imported_modules(py_file)
            for imp in imports:
                if imp == "routes" or imp.startswith("routes."):
                    violations.append((str(py_file.relative_to(ROOT)), imp, "core->routes"))
                if subpkg == "shared" and any(
                    imp == f"core.{dom}" or imp.startswith(f"core.{dom}.")
                    for dom in DOMAIN_PACKAGES
                ):
                    violations.append((str(py_file.relative_to(ROOT)), imp, "shared->domain"))

    assert violations == [], f"Hybrid dependency violations detected: {violations}"


def test_thin_entrypoint_and_route_modules_exist():
    """app.py stays thin (<350 lines) and all modular route files exist under routes/."""
    app_lines = (ROOT / "app.py").read_text(encoding="utf-8").splitlines()
    assert len(app_lines) < 350, f"app.py bloated to {len(app_lines)} lines (expected < 350)"

    routes_dir = ROOT / "routes"
    for filename in EXPECTED_ROUTE_MODULES:
        assert (routes_dir / filename).is_file(), f"Missing route module routes/{filename}"


def test_modular_routes_preserve_all_core_endpoints():
    """All core domain HTTP endpoints remain registered on create_app()."""
    from app import create_app

    flask_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    rules = {rule.rule for rule in flask_app.url_map.iter_rules()}

    expected_paths = {
        "/",
        "/health",
        "/ready",
        "/openapi.json",
        "/docs",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/me",
        "/api/chat",
        "/api/intake/session",
        "/api/prescription/scan",
        "/api/prescription/history",
        "/api/upload-lab",
        "/api/clinical-summary",
        "/api/consultations",
        "/api/appointments",
        "/api/nutrition/options",
        "/api/nutrition/analyze",
        "/api/facilities",
        "/api/config/maps",
    }
    missing = expected_paths - rules
    assert not missing, f"Missing expected Flask endpoints after route extraction: {sorted(missing)}"
