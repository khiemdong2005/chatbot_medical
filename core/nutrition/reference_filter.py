"""Independent Reference Filter for Clinical Safety Verification (Phase 3.1).

Implements an independent, pure linear scan baseline over recipes and metadata
without utilizing the In-Memory Inverted Index data structures.
Used for parity audits, property-based tests, and monotonicity checks.
"""

from copy import deepcopy
import logging
import re
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set

from core.nutrition.clinical_constraints import (
    CandidatePools,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.metadata_index import (
    STANDARD_COMBO_ROLES,
    SUPPORTED_ALLERGENS,
)

logger = logging.getLogger(__name__)

# Residual pattern for organ meat (excluding "sò huyết", "trái tim", "hình tim")
ORGAN_MEAT_REGEX = re.compile(
    r"\b(?:gan|cật|tim|lòng|dạ\s+trường|mề|dồi(?:\s+trường)?|pate|tiết|(?<!sò\s)huyết)\b",
    re.IGNORECASE,
)
ORGAN_EXCLUSION_CLEANER = re.compile(r"(?:sò\s+huyết|(?:trái|hình)\s+tim)", re.IGNORECASE)

# Dairy residual pattern
DAIRY_RESIDUAL_REGEX = re.compile(
    r"\b(?:sữa\s+(?:bò|tươi|đặc)|bơ\s+(?:lạt|động\s+vật|anchor)|phô\s+mai|whipping|kem\s+tươi)\b",
    re.IGNORECASE,
)

# Soy residual pattern
SOY_RESIDUAL_REGEX = re.compile(
    r"\b(?:nước\s+tương|xì\s+dầu|đậu\s+nành|tàu\s+hũ\s+ky|tàu\s+vị\s+yểu)\b",
    re.IGNORECASE,
)

# Gluten residual pattern
GLUTEN_RESIDUAL_REGEX = re.compile(
    r"\b(?:yến\s+mạch|lúa\s+mạch|bột\s+mì|mì\s+căn|bánh\s+mì)\b",
    re.IGNORECASE,
)


class ReferenceFilter:
    """Linear-scan reference baseline for verifying candidate selection correctness."""

    @classmethod
    def filter_candidates(
        cls,
        resolved: ResolvedConstraints,
        recipe_by_id: Dict[str, Dict[str, Any]],
        metadata_by_id: Dict[str, Dict[str, Any]],
        manual_review_ids: Optional[Set[str]] = None,
    ) -> List[str]:
        """Perform sequential scan and evaluate all hard constraints deterministically."""
        if not resolved.is_safe_to_proceed:
            return []

        manual_review = manual_review_ids or set()
        surviving_ids: List[str] = []

        for rid, meta in metadata_by_id.items():
            # 1. Manual review exclusion
            if rid in manual_review:
                continue

            # 2. Specifically excluded recipe IDs
            if rid in resolved.hard_excluded_recipe_ids:
                continue

            # 3. Hard excluded roles (e.g. dessert for diabetes policy)
            primary_role = meta.get("primary_role")
            if resolved.hard_excluded_roles and primary_role in resolved.hard_excluded_roles:
                continue

            # 4. Allergen exclusions (Fail-closed: known_present and unknown)
            if resolved.hard_excluded_allergens:
                allergen_assessments = meta.get("allergen_assessments") or {}
                allergen_blocked = False
                for a in resolved.hard_excluded_allergens:
                    if a not in SUPPORTED_ALLERGENS:
                        continue
                    status = allergen_assessments.get(a, {}).get("status", "unknown")
                    if status in ("known_present", "unknown"):
                        allergen_blocked = True
                        break
                if allergen_blocked:
                    continue

            # 5. Ingredient exclusions
            if resolved.hard_excluded_ingredients:
                norm_ings = set(meta.get("normalized_ingredients") or [])
                if norm_ings & resolved.hard_excluded_ingredients:
                    continue

            # 6. Ingredient group exclusions
            if resolved.hard_excluded_ingredient_groups:
                groups = set(meta.get("ingredient_groups") or [])
                if groups & resolved.hard_excluded_ingredient_groups:
                    continue

            # 7. Cooking method exclusions
            if resolved.hard_excluded_cooking_methods:
                methods = set(meta.get("cooking_methods") or [])
                if methods & resolved.hard_excluded_cooking_methods:
                    continue

            # 8. Residual clinical safety checks
            recipe = recipe_by_id.get(rid) or {}
            title = recipe.get("title", "")
            raw_ingredients = " ".join(recipe.get("raw_ingredients", []))
            full_text = f"{title} {raw_ingredients}"

            # Organ meat check
            if "organ_meat" in resolved.hard_excluded_ingredient_groups or "organ_meat" in resolved.hard_excluded_ingredients:
                cleaned_text = ORGAN_EXCLUSION_CLEANER.sub("", full_text)
                if ORGAN_MEAT_REGEX.search(cleaned_text):
                    continue

            # Dairy residual check
            if "cow_milk" in resolved.hard_excluded_allergens:
                if DAIRY_RESIDUAL_REGEX.search(full_text):
                    continue

            # Soy residual check
            if "soy" in resolved.hard_excluded_allergens:
                if SOY_RESIDUAL_REGEX.search(full_text):
                    continue

            # Gluten residual check
            if "wheat_gluten" in resolved.hard_excluded_allergens or any(r.rule_id == "RULE_CELIAC_GLUTEN_FREE" for r in resolved.applied_rules):
                if GLUTEN_RESIDUAL_REGEX.search(full_text):
                    continue

            surviving_ids.append(rid)

        return sorted(surviving_ids)
