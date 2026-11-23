"""Clinical Constraint Filter.

Applies resolved hard and soft constraints using the In-Memory Inverted Index (Phase 2),
performs residual clinical safety verifications, and separates candidates into
distinct meal pools (Combo roles, Standalone, Beverage, Dessert, Snack).

Operates with zero LLM dependencies and deterministic latency.
"""

from copy import deepcopy
import logging
import re
import time
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from core.nutrition.clinical_constraints import (
    CandidatePools,
    ClinicalRuleDefinition,
    ClinicalSafetyStatus,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.metadata_index import (
    get_metadata_index,
    InMemoryInvertedIndex,
    SUPPORTED_ALLERGENS,
    STANDARD_COMBO_ROLES,
)

logger = logging.getLogger(__name__)

ORGAN_MEAT_REGEX = re.compile(
    r"\b(?:gan|cật|tim|lòng|dạ\s+trường|mề|dồi(?:\s+trường)?|pate|tiết|(?<!sò\s)huyết)\b",
    re.IGNORECASE,
)
ORGAN_EXCLUSION_CLEANER = re.compile(r"(?:sò\s+huyết|(?:trái|hình)\s+tim)", re.IGNORECASE)

DAIRY_RESIDUAL_REGEX = re.compile(
    r"\b(?:sữa\s+(?:bò|tươi|đặc)|bơ\s+(?:lạt|động\s+vật|anchor)|phô\s+mai|whipping|kem\s+tươi)\b",
    re.IGNORECASE,
)

SOY_RESIDUAL_REGEX = re.compile(
    r"\b(?:nước\s+tương|xì\s+dầu|đậu\s+nành|tàu\s+hũ\s+ky|tàu\s+vị\s+yểu)\b",
    re.IGNORECASE,
)

GLUTEN_RESIDUAL_REGEX = re.compile(
    r"\b(?:yến\s+mạch|lúa\s+mạch|bột\s+mì|mì\s+căn|bánh\s+mì)\b",
    re.IGNORECASE,
)


class ConstraintFilter:
    """Executes indexed candidate retrieval and residual safety checks."""

    @classmethod
    def filter_candidates(
        cls,
        resolved: ResolvedConstraints,
        index: Optional[InMemoryInvertedIndex] = None,
        recipe_type: str = "food",
    ) -> CandidatePools:
        """Filter the logical catalog into separate candidate pools by meal role."""
        t_start = time.perf_counter()
        idx = index or get_metadata_index()

        pools = CandidatePools()
        pools.soft_constraints = {
            # Clinical directives
            "clinical_preferred_ingredients": list(resolved.soft_preferred_ingredients),
            "clinical_preferred_ingredient_groups": list(resolved.soft_preferred_ingredient_groups),
            "clinical_preferred_cooking_methods": list(resolved.soft_preferred_cooking_methods),
            "clinical_avoided_ingredients": list(resolved.soft_avoided_ingredients),
            "clinical_avoided_ingredient_groups": list(resolved.soft_avoided_ingredient_groups),
            "clinical_avoided_cooking_methods": list(resolved.soft_avoided_cooking_methods),
            # User personal preferences
            "user_preferred_ingredients": list(resolved.user_preferred_ingredients),
            "user_preferred_ingredient_groups": list(resolved.user_preferred_ingredient_groups),
            "user_preferred_cooking_methods": list(resolved.user_preferred_cooking_methods),
            "user_avoided_ingredients": list(resolved.user_avoided_ingredients),
            "user_avoided_cooking_methods": list(resolved.user_avoided_cooking_methods),
            # Backwards-compatible aliases
            "preferred_ingredients": list(resolved.soft_preferred_ingredients),
            "preferred_ingredient_groups": list(resolved.soft_preferred_ingredient_groups),
            "preferred_cooking_methods": list(resolved.soft_preferred_cooking_methods),
            "avoided_ingredients": list(resolved.soft_avoided_ingredients),
            "avoided_ingredient_groups": list(resolved.soft_avoided_ingredient_groups),
            "avoided_cooking_methods": list(resolved.soft_avoided_cooking_methods),
            "nutrient_limits": resolved.nutrient_limits,
        }
        pools.unresolved_constraints = list(resolved.unresolved_constraints)
        pools.warnings = list(resolved.warnings)

        # ---------------------------------------------------------------------
        # 1. Immediate Safety Halts (Fail-closed on unsupported / clinical blocks)
        # ---------------------------------------------------------------------
        if not resolved.is_safe_to_proceed:
            status_val = resolved.safety_status.value if isinstance(resolved.safety_status, SafetyStatus) else (resolved.safety_halt_reason or "SAFETY_HALT")
            pools.safety_status = ClinicalSafetyStatus(status_val)
            total_duration_ms = (time.perf_counter() - t_start) * 1000.0
            pools.execution_metrics = {
                "initial_candidate_count": len(idx.all_recipe_ids),
                "surviving_count": 0,
                "unique_candidate_count": 0,
                "total_role_memberships": 0,
                "safety_halt": True,
                "safety_status": pools.safety_status,
                "is_combo_viable": False,
                "is_standalone_viable": False,
                "total_latency_ms": round(total_duration_ms, 3),
            }
            return pools

        # ---------------------------------------------------------------------
        # 2. In-Memory Inverted Index Filtering (Fast Set Algebra)
        # ---------------------------------------------------------------------
        t_filter_start = time.perf_counter()

        initial_count = len(idx.all_recipe_ids)

        # Run primary inverted index filtering
        surviving_ids_list = idx.filter_candidate_ids(
            candidate_ids=idx.all_recipe_ids,
            excluded_allergens=resolved.hard_excluded_allergens,
            excluded_ingredients=resolved.hard_excluded_ingredients,
            excluded_ingredient_groups=resolved.hard_excluded_ingredient_groups,
            excluded_cooking_methods=resolved.hard_excluded_cooking_methods,
            exclude_manual_review=True,
            deterministic=True,
        )
        surviving_set: Set[str] = set(surviving_ids_list)

        # Exclude hard excluded roles (e.g. dessert role for diabetes policy)
        if resolved.hard_excluded_roles:
            role_blocked: Set[str] = set()
            for r in resolved.hard_excluded_roles:
                role_blocked.update(idx.get_ids_by_primary_role(r))
            surviving_set.difference_update(role_blocked)

        # Remove specifically excluded recipe IDs (e.g. from history / rotation)
        if resolved.hard_excluded_recipe_ids:
            surviving_set.difference_update(resolved.hard_excluded_recipe_ids)

        t_filter_end = time.perf_counter()

        # ---------------------------------------------------------------------
        # 3. Residual Clinical Safety Checks (Defense-in-depth)
        # ---------------------------------------------------------------------
        t_residual_start = time.perf_counter()
        residual_blocked: Set[str] = set()

        # Check organ meat residual text if gout/organ meat exclusion is active
        if "organ_meat" in resolved.hard_excluded_ingredient_groups or "organ_meat" in resolved.hard_excluded_ingredients:
            for rid in surviving_set:
                recipe = idx.get_recipe_by_id(rid)
                if not recipe:
                    continue
                full_text = f"{recipe.get('title', '')} {' '.join(recipe.get('raw_ingredients', []))}"
                cleaned_text = ORGAN_EXCLUSION_CLEANER.sub("", full_text)
                if ORGAN_MEAT_REGEX.search(cleaned_text):
                    residual_blocked.add(rid)

        # Check cow_milk allergy residual text (catch butter/dairy street food ambiguities)
        if "cow_milk" in resolved.hard_excluded_allergens:
            for rid in surviving_set:
                recipe = idx.get_recipe_by_id(rid)
                if not recipe:
                    continue
                full_text = f"{recipe.get('title', '')} {' '.join(recipe.get('raw_ingredients', []))}"
                if DAIRY_RESIDUAL_REGEX.search(full_text):
                    residual_blocked.add(rid)

        # Check soy allergy residual text (catch soy sauce / tofu ambiguities)
        if "soy" in resolved.hard_excluded_allergens:
            for rid in surviving_set:
                recipe = idx.get_recipe_by_id(rid)
                if not recipe:
                    continue
                full_text = f"{recipe.get('title', '')} {' '.join(recipe.get('raw_ingredients', []))}"
                if SOY_RESIDUAL_REGEX.search(full_text):
                    residual_blocked.add(rid)

        # Check celiac / strict gluten avoidance (block unverified oats / barley)
        if "wheat_gluten" in resolved.hard_excluded_allergens or any(r.rule_id == "RULE_CELIAC_GLUTEN_FREE" for r in resolved.applied_rules):
            for rid in surviving_set:
                recipe = idx.get_recipe_by_id(rid)
                if not recipe:
                    continue
                full_text = f"{recipe.get('title', '')} {' '.join(recipe.get('raw_ingredients', []))}"
                if GLUTEN_RESIDUAL_REGEX.search(full_text):
                    residual_blocked.add(rid)

        if residual_blocked:
            surviving_set.difference_update(residual_blocked)

        t_residual_end = time.perf_counter()

        # ---------------------------------------------------------------------
        # 4. Candidate Pool Segregation
        # ---------------------------------------------------------------------
        # A. Group A: Combo Candidates (staple, main_dish, soup, vegetable)
        pools.combo_candidates["staple"] = sorted(list(surviving_set & idx.get_ids_by_combo_role("staple")))
        pools.combo_candidates["main_dish"] = sorted(list(surviving_set & idx.get_ids_by_combo_role("main_dish")))
        pools.combo_candidates["soup"] = sorted(list(surviving_set & idx.get_ids_by_combo_role("soup")))
        pools.combo_candidates["vegetable"] = sorted(list(surviving_set & idx.get_ids_by_combo_role("vegetable")))

        # B. Group B: Standalone Candidates (One-dish meals: phở, bún, cháo, bánh canh, lẩu...)
        pools.standalone_candidates = sorted(list(surviving_set & idx.get_ids_by_primary_role("standalone")))

        # C. Auxiliary pools (Beverages, Desserts, Snacks)
        pools.beverage_candidates = sorted(list(surviving_set & idx.get_ids_by_primary_role("beverage")))
        pools.dessert_candidates = sorted(list(surviving_set & idx.get_ids_by_primary_role("dessert")))
        pools.snack_candidates = sorted(list(surviving_set & idx.get_ids_by_primary_role("snack")))

        # D. Statistics and metrics
        total_surviving = len(surviving_set)
        pools.unique_candidate_ids = set(surviving_set)
        pools.total_role_memberships = (
            sum(len(v) for v in pools.combo_candidates.values()) +
            len(pools.standalone_candidates) +
            len(pools.beverage_candidates) +
            len(pools.dessert_candidates) +
            len(pools.snack_candidates)
        )

        is_combo_viable = all(len(pools.combo_candidates[r]) > 0 for r in STANDARD_COMBO_ROLES)
        is_standalone_viable = len(pools.standalone_candidates) > 0

        # Check if entire pool is exhausted
        if total_surviving == 0:
            pools.safety_status = ClinicalSafetyStatus(SafetyStatus.NO_ELIGIBLE_CANDIDATES.value)
            pools.warnings.append(
                "Không có món ăn trong cơ sở dữ liệu đáp ứng đồng thời tất cả các ràng buộc khắt khe đã chọn. "
                "Hệ thống không tự ý nới lỏng rào cản an toàn."
            )
        else:
            pools.safety_status = ClinicalSafetyStatus(SafetyStatus.PASSED_KNOWN_CONSTRAINTS.value)

        t_total_end = time.perf_counter()

        pools.execution_metrics = {
            "initial_candidate_count": initial_count,
            "surviving_count": total_surviving,
            "unique_candidate_count": total_surviving,
            "total_role_memberships": pools.total_role_memberships,
            "removed_count": initial_count - total_surviving,
            "combo_staple_count": len(pools.combo_candidates["staple"]),
            "combo_main_count": len(pools.combo_candidates["main_dish"]),
            "combo_soup_count": len(pools.combo_candidates["soup"]),
            "combo_vegetable_count": len(pools.combo_candidates["vegetable"]),
            "standalone_count": len(pools.standalone_candidates),
            "beverage_count": len(pools.beverage_candidates),
            "dessert_count": len(pools.dessert_candidates),
            "snack_count": len(pools.snack_candidates),
            "is_combo_viable": is_combo_viable,
            "is_standalone_viable": is_standalone_viable,
            "indexed_filtering_ms": round((t_filter_end - t_filter_start) * 1000.0, 3),
            "residual_validation_ms": round((t_residual_end - t_residual_start) * 1000.0, 3),
            "total_latency_ms": round((t_total_end - t_start) * 1000.0, 3),
        }

        return pools
