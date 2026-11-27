"""MediMind Scripts Package.

Organizes repository utilities into domain subpackages (``scripts/rag``,
``scripts/eval``, ``scripts/ops``) while keeping CI/entrypoint scripts at the
top level and aliasing legacy ``scripts.<module>`` imports seamlessly.
"""

from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
import sys

_SCRIPT_ALIASES: dict[str, str] = {
    # scripts.rag
    "build_full_legacy_bilingual": "scripts.rag.build_full_legacy_bilingual",
    "build_legacy_bilingual_metadata": "scripts.rag.build_legacy_bilingual_metadata",
    "build_v4_shadow": "scripts.rag.build_v4_shadow",
    "controlled_v4_activation": "scripts.rag.controlled_v4_activation",
    "curate_tier_a": "scripts.rag.curate_tier_a",
    "enrich_legacy_corpus": "scripts.rag.enrich_legacy_corpus",
    "generate_complete_legacy_dict": "scripts.rag.generate_complete_legacy_dict",
    "promote_and_unify_sources": "scripts.rag.promote_and_unify_sources",
    # scripts.eval
    "analyze_rag_retrieval": "scripts.eval.analyze_rag_retrieval",
    "build_answer_config_snapshot": "scripts.eval.build_answer_config_snapshot",
    "build_answer_eval_dataset": "scripts.eval.build_answer_eval_dataset",
    "build_rag_test_draft": "scripts.eval.build_rag_test_draft",
    "build_safety_eval_dataset": "scripts.eval.build_safety_eval_dataset",
    "cache_cross_language_queries": "scripts.eval.cache_cross_language_queries",
    "evaluate_answer_quality": "scripts.eval.evaluate_answer_quality",
    "evaluate_clinical_safety": "scripts.eval.evaluate_clinical_safety",
    "evaluate_cross_language": "scripts.eval.evaluate_cross_language",
    "evaluate_dilution_ablations": "scripts.eval.evaluate_dilution_ablations",
    "evaluate_expanded_retrieval": "scripts.eval.evaluate_expanded_retrieval",
    "evaluate_holdout_frozen_winner": "scripts.eval.evaluate_holdout_frozen_winner",
    "evaluate_rag_holdout": "scripts.eval.evaluate_rag_holdout",
    "evaluate_rag_runtime_expansion": "scripts.eval.evaluate_rag_runtime_expansion",
    "evaluate_reliability": "scripts.eval.evaluate_reliability",
    "evaluate_retrieval": "scripts.eval.evaluate_retrieval",
    "evaluate_shadow_retrieval": "scripts.eval.evaluate_shadow_retrieval",
    "experimental_cross_language": "scripts.eval.experimental_cross_language",
    "query_expansion_experiment": "scripts.eval.query_expansion_experiment",
    "validate_rag_test_set": "scripts.eval.validate_rag_test_set",
    "verify_cases_abcd": "scripts.eval.verify_cases_abcd",
    # scripts.ops
    "check_gemini_connection": "scripts.ops.check_gemini_connection",
    "scan_env_vars": "scripts.ops.scan_env_vars",
    "update_db": "scripts.ops.update_db",
    "view_db": "scripts.ops.view_db",
    "wipe_all_data": "scripts.ops.wipe_all_data",
}


class _ScriptsAliasLoader(Loader):
    def __init__(self, target_name: str) -> None:
        self._target_name = target_name

    def create_module(self, spec: ModuleSpec):
        return import_module(self._target_name)

    def exec_module(self, module) -> None:
        pass


class _ScriptsAliasFinder(MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname.startswith("scripts.") and fullname.count(".") == 1:
            leaf = fullname.split(".", 1)[1]
            canonical = _SCRIPT_ALIASES.get(leaf)
            if canonical:
                return ModuleSpec(fullname, _ScriptsAliasLoader(canonical))
        return None


if not any(isinstance(f, _ScriptsAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _ScriptsAliasFinder())


def __getattr__(name: str):
    canonical = _SCRIPT_ALIASES.get(name)
    if canonical:
        module = import_module(canonical)
        sys.modules[f"scripts.{name}"] = module
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
