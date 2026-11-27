"""MediMind Core Package (Modular Monolith).

Provides backward-compatibility aliasing from legacy ``core.<module>`` imports
to canonical ``core.<domain>.<module>`` subpackages without cluttering ``core/``
with flat shim files.
"""

from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
import sys

_LEGACY_ALIASES: dict[str, str] = {
    # core.ai
    "ai_types": "core.ai.ai_types",
    "circuit_breaker": "core.ai.circuit_breaker",
    "gemini_service": "core.ai.gemini_service",
    "interpretation_service": "core.ai.interpretation_service",
    "llm_provider": "core.ai.llm_provider",
    "prompts": "core.ai.prompts",
    "retry_policy": "core.ai.retry_policy",
    # core.auth
    "csrf_protection": "core.auth.csrf_protection",
    "email_service": "core.auth.email_service",
    "otp_service": "core.auth.otp_service",
    "rate_limit_service": "core.auth.rate_limit_service",
    "security_headers": "core.auth.security_headers",
    "security_patch": "core.auth.security_patch",
    "sms_service": "core.auth.sms_service",
    # core.chat
    "chat_service": "core.chat.chat_service",
    "consultation_service": "core.chat.consultation_service",
    "document_chunker": "core.chat.document_chunker",
    "grounding_service": "core.chat.grounding_service",
    "health_context": "core.chat.health_context",
    "intake_service": "core.chat.intake_service",
    "query_expansion_service": "core.chat.query_expansion_service",
    "rag_service": "core.chat.rag_service",
    "reranker_service": "core.chat.reranker_service",
    "triage": "core.chat.triage",
    # core.facilities
    "appointment_service": "core.facilities.appointment_service",
    "facilities_service": "core.facilities.facilities_service",
    # core.nutrition
    "nutrition_ai": "core.nutrition.nutrition_ai",
    "nutrition_options": "core.nutrition.nutrition_options",
    "nutrition_rules": "core.nutrition.nutrition_rules",
    "nutrition_service": "core.nutrition.nutrition_service",
    "recipe_catalog": "core.nutrition.recipe_catalog",
    "recipe_features": "core.nutrition.recipe_features",
    # core.ocr
    "gemini_schema_service": "core.ocr.gemini_schema_service",
    "groq_schema_service": "core.ocr.groq_schema_service",
    "image_preprocessor": "core.ocr.image_preprocessor",
    "ocr_extractor": "core.ocr.ocr_extractor",
    "ocr_parallel_service": "core.ocr.ocr_parallel_service",
    "pipeline_orchestrator": "core.ocr.pipeline_orchestrator",
    "preprocessing_service": "core.ocr.preprocessing_service",
    "prescription_crop_service": "core.ocr.prescription_crop_service",
    "prescription_service": "core.ocr.prescription_service",
    "reconciliation_service": "core.ocr.reconciliation_service",
    "validation_service": "core.ocr.validation_service",
    # core.shared
    "api_errors": "core.shared.api_errors",
    "cache_service": "core.shared.cache_service",
    "cleanup_service": "core.shared.cleanup_service",
    "db_utils": "core.shared.db_utils",
    "logging_redaction": "core.shared.logging_redaction",
    "migrations": "core.shared.migrations",
    "models": "core.shared.models",
    "network_utils": "core.shared.network_utils",
    "settings": "core.shared.settings",
    "storage_service": "core.shared.storage_service",
}


class _CoreAliasLoader(Loader):
    def __init__(self, target_name: str) -> None:
        self._target_name = target_name

    def create_module(self, spec: ModuleSpec):
        return import_module(self._target_name)

    def exec_module(self, module) -> None:
        pass


class _CoreAliasFinder(MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname.startswith("core.") and fullname.count(".") == 1:
            leaf = fullname.split(".", 1)[1]
            canonical = _LEGACY_ALIASES.get(leaf)
            if canonical:
                return ModuleSpec(fullname, _CoreAliasLoader(canonical))
        return None


if not any(isinstance(f, _CoreAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _CoreAliasFinder())


def __getattr__(name: str):
    canonical = _LEGACY_ALIASES.get(name)
    if canonical:
        module = import_module(canonical)
        sys.modules[f"core.{name}"] = module
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
