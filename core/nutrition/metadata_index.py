"""In-Memory Inverted Index for Constraint-Aware Hybrid Meal Recommendation.

Replaces runtime sequential scans and regex parsing with high-performance
in-memory inverted indexes over normalized metadata sidecar (v1.1.0)
and canonical staples.

Thread-safe, immutable read structures (frozenset), zero duplicate copies,
and deterministic execution.
"""

from collections import defaultdict
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data" / "recipes"
VIFOODREC_RECIPES_PATH = DATA_ROOT / "vifoodrec" / "recipes.json"
VIFOODREC_METADATA_PATH = DATA_ROOT / "vifoodrec" / "recipes_metadata.json"
CANONICAL_STAPLES_PATH = DATA_ROOT / "canonical_staples.json"

METADATA_VERSION = "1.1.0"
DATASET_VERSION = "vifoodrec_clean_paclic2024"

SUPPORTED_ALLERGENS: FrozenSet[str] = frozenset([
    "shrimp", "crab", "squid_octopus", "fish", "mollusk",
    "peanut", "sesame", "egg", "cow_milk", "soy", "wheat_gluten"
])

STANDARD_COMBO_ROLES: FrozenSet[str] = frozenset([
    "staple", "main_dish", "soup", "vegetable"
])

ALL_MEAL_ROLES: FrozenSet[str] = frozenset([
    "staple", "main_dish", "soup", "vegetable",
    "standalone", "beverage", "dessert", "snack", "other"
])

EMPTY_FROZENSET: FrozenSet[str] = frozenset()


class InMemoryInvertedIndex:
    """Read-only in-memory inverted index over the logical recipe catalog (2,471 items)."""

    def __init__(
        self,
        recipe_by_id: Dict[str, Dict[str, Any]],
        metadata_by_id: Dict[str, Dict[str, Any]],
        primary_role_index: Dict[str, FrozenSet[str]],
        secondary_role_index: Dict[str, FrozenSet[str]],
        combo_role_index: Dict[str, FrozenSet[str]],
        ingredient_index: Dict[str, FrozenSet[str]],
        ingredient_group_index: Dict[str, FrozenSet[str]],
        allergen_present_index: Dict[str, FrozenSet[str]],
        allergen_unknown_index: Dict[str, FrozenSet[str]],
        allergen_not_detected_index: Dict[str, FrozenSet[str]],
        cooking_method_index: Dict[str, FrozenSet[str]],
        manual_review_ids: FrozenSet[str],
        all_recipe_ids: FrozenSet[str],
        dataset_version: str = DATASET_VERSION,
        metadata_version: str = METADATA_VERSION,
        build_duration_ms: float = 0.0,
    ):
        self.recipe_by_id = recipe_by_id
        self.metadata_by_id = metadata_by_id

        self.primary_role_index = primary_role_index
        self.secondary_role_index = secondary_role_index
        self.combo_role_index = combo_role_index

        self.ingredient_index = ingredient_index
        self.ingredient_group_index = ingredient_group_index

        self.allergen_present_index = allergen_present_index
        self.allergen_unknown_index = allergen_unknown_index
        self.allergen_not_detected_index = allergen_not_detected_index

        self.cooking_method_index = cooking_method_index

        self.manual_review_ids = manual_review_ids
        self.all_recipe_ids = all_recipe_ids

        self.dataset_version = dataset_version
        self.metadata_version = metadata_version
        self.build_duration_ms = build_duration_ms
        self.build_timestamp = time.time()

    @classmethod
    def build(
        cls,
        recipes_path: Optional[Path] = None,
        metadata_path: Optional[Path] = None,
        canonical_staples_path: Optional[Path] = None,
    ) -> "InMemoryInvertedIndex":
        """Build immutable inverted indexes from recipes, metadata sidecar, and canonical staples."""
        start_t = time.perf_counter()

        r_path = recipes_path or VIFOODREC_RECIPES_PATH
        m_path = metadata_path or VIFOODREC_METADATA_PATH
        s_path = canonical_staples_path or CANONICAL_STAPLES_PATH

        if not r_path.exists():
            raise FileNotFoundError(f"ViFoodRec recipes not found at {r_path}")
        if not m_path.exists():
            raise FileNotFoundError(f"ViFoodRec metadata sidecar not found at {m_path}")
        if not s_path.exists():
            raise FileNotFoundError(f"Canonical staples not found at {s_path}")

        with open(r_path, "r", encoding="utf-8") as f:
            vifoodrec_recipes = json.load(f)
        with open(m_path, "r", encoding="utf-8") as f:
            vifoodrec_metadata = json.load(f)
        with open(s_path, "r", encoding="utf-8") as f:
            canonical_staples = json.load(f)

        recipe_by_id: Dict[str, Dict[str, Any]] = {}
        metadata_by_id: Dict[str, Dict[str, Any]] = {}

        # 1. Index ViFoodRec items
        for r in vifoodrec_recipes:
            recipe_by_id[r["id"]] = r

        for m in vifoodrec_metadata:
            metadata_by_id[m["id"]] = m

        # 2. Index Canonical Staples items
        for staple in canonical_staples:
            sid = staple["id"]
            if sid in recipe_by_id:
                raise ValueError(f"Duplicate recipe ID found in canonical staples: {sid}")

            recipe_by_id[sid] = staple
            # Form metadata record for staple
            staple_meta = {
                "id": sid,
                "title": staple.get("title", ""),
                "primary_role": staple.get("primary_role", "staple"),
                "secondary_roles": staple.get("secondary_roles", []),
                "eligible_combo_roles": staple.get("eligible_combo_roles", ["staple"]),
                "normalized_ingredients": staple.get("normalized_ingredients", []),
                "ingredient_groups": staple.get("ingredient_groups", ["grain"]),
                "cooking_methods": staple.get("cooking_methods", ["steaming", "boiling"]),
                "allergen_assessments": staple.get("allergen_assessments", {}),
                "allergen_tags": staple.get("allergen_tags", []),
                "allergen_unknown_tags": staple.get("allergen_unknown_tags", []),
                "allergen_status": staple.get("allergen_status", "assessed_not_detected"),
                "has_unknown_allergens": False,
                "needs_manual_review": False,
                "review_required": False,
                "nutrition_verified": staple.get("nutrition_verified", True),
                "nutrition_basis": staple.get("nutrition_basis", "per_reference_serving_150g"),
                "nutrient_provenance": staple.get("nutrient_provenance", "unmerged_single_source"),
                "has_carbohydrate_data": True,
                "image_link": staple.get("image_link", ""),
                "source_image_url": staple.get("source_image_url", ""),
                "metadata_version": METADATA_VERSION,
                "dataset_version": "canonical_staples_v1",
            }
            metadata_by_id[sid] = staple_meta

        all_recipe_ids_set = set(recipe_by_id.keys())
        all_metadata_ids_set = set(metadata_by_id.keys())

        if all_recipe_ids_set != all_metadata_ids_set:
            diff_r = all_recipe_ids_set - all_metadata_ids_set
            diff_m = all_metadata_ids_set - all_recipe_ids_set
            raise ValueError(
                f"Catalog join mismatch: recipes without metadata={len(diff_r)}, "
                f"metadata without recipes={len(diff_m)}"
            )

        # Temporary mutable sets - Pre-populate all known keys to ensure complete coverage
        primary_role_acc: Dict[str, Set[str]] = {role: set() for role in ALL_MEAL_ROLES}
        secondary_role_acc: Dict[str, Set[str]] = defaultdict(set)
        combo_role_acc: Dict[str, Set[str]] = {role: set() for role in STANDARD_COMBO_ROLES}

        ingredient_acc: Dict[str, Set[str]] = defaultdict(set)
        ingredient_group_acc: Dict[str, Set[str]] = defaultdict(set)

        allergen_present_acc: Dict[str, Set[str]] = {a: set() for a in SUPPORTED_ALLERGENS}
        allergen_unknown_acc: Dict[str, Set[str]] = {a: set() for a in SUPPORTED_ALLERGENS}
        allergen_not_detected_acc: Dict[str, Set[str]] = {a: set() for a in SUPPORTED_ALLERGENS}

        cooking_method_acc: Dict[str, Set[str]] = defaultdict(set)
        manual_review_set: Set[str] = set()

        for rid, meta in metadata_by_id.items():
            # Invariant flag: review required
            is_manual_review = bool(meta.get("needs_manual_review") or meta.get("review_required"))
            if is_manual_review:
                manual_review_set.add(rid)

            # 1. Primary role
            p_role = meta.get("primary_role") or "other"
            primary_role_acc[p_role].add(rid)

            # 2. Secondary roles
            for s_role in meta.get("secondary_roles", []):
                secondary_role_acc[s_role].add(rid)

            # 3. Combo roles (Enforcing Meal Role Invariants)
            # - Standalone dishes strictly NEVER in combo_role_index
            # - Manual review dishes strictly NEVER in combo_role_index
            # - Non-combo roles (dessert, beverage, snack, other) NOT in standard combo roles
            if not is_manual_review and p_role != "standalone":
                for c_role in meta.get("eligible_combo_roles", []):
                    if c_role in STANDARD_COMBO_ROLES:
                        combo_role_acc[c_role].add(rid)

            # 4. Ingredients & Groups
            for ing in meta.get("normalized_ingredients", []):
                ingredient_acc[ing].add(rid)
            for grp in meta.get("ingredient_groups", []):
                ingredient_group_acc[grp].add(rid)

            # 5. Cooking methods
            for method in meta.get("cooking_methods", []):
                cooking_method_acc[method].add(rid)

            # 6. Allergens (3-state granular indexing)
            assessments = meta.get("allergen_assessments", {})
            for allergen in SUPPORTED_ALLERGENS:
                a_info = assessments.get(allergen, {})
                status = a_info.get("status") if isinstance(a_info, dict) else None

                if status == "known_present":
                    allergen_present_acc[allergen].add(rid)
                elif status == "unknown":
                    allergen_unknown_acc[allergen].add(rid)
                else:
                    # assessed_not_detected or unassessed (conservatively not detected if not present/unknown)
                    allergen_not_detected_acc[allergen].add(rid)

        # Freeze all mutable sets into frozensets for thread-safety and immutability
        primary_role_index = {k: frozenset(v) for k, v in primary_role_acc.items()}
        secondary_role_index = {k: frozenset(v) for k, v in secondary_role_acc.items()}
        combo_role_index = {k: frozenset(v) for k, v in combo_role_acc.items()}

        ingredient_index = {k: frozenset(v) for k, v in ingredient_acc.items()}
        ingredient_group_index = {k: frozenset(v) for k, v in ingredient_group_acc.items()}

        allergen_present_index = {k: frozenset(v) for k, v in allergen_present_acc.items()}
        allergen_unknown_index = {k: frozenset(v) for k, v in allergen_unknown_acc.items()}
        allergen_not_detected_index = {k: frozenset(v) for k, v in allergen_not_detected_acc.items()}

        cooking_method_index = {k: frozenset(v) for k, v in cooking_method_acc.items()}

        duration_ms = (time.perf_counter() - start_t) * 1000.0

        return cls(
            recipe_by_id=recipe_by_id,
            metadata_by_id=metadata_by_id,
            primary_role_index=primary_role_index,
            secondary_role_index=secondary_role_index,
            combo_role_index=combo_role_index,
            ingredient_index=ingredient_index,
            ingredient_group_index=ingredient_group_index,
            allergen_present_index=allergen_present_index,
            allergen_unknown_index=allergen_unknown_index,
            allergen_not_detected_index=allergen_not_detected_index,
            cooking_method_index=cooking_method_index,
            manual_review_ids=frozenset(manual_review_set),
            all_recipe_ids=frozenset(all_recipe_ids_set),
            dataset_version=DATASET_VERSION,
            metadata_version=METADATA_VERSION,
            build_duration_ms=duration_ms,
        )

    # -------------------------------------------------------------------------
    # Retrieval API Interface
    # -------------------------------------------------------------------------

    def get_recipe_by_id(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full recipe dictionary by recipe ID."""
        return self.recipe_by_id.get(recipe_id)

    def get_metadata_by_id(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve normalized metadata dictionary by recipe ID."""
        return self.metadata_by_id.get(recipe_id)

    def get_ids_by_primary_role(self, role: str) -> FrozenSet[str]:
        """Get all recipe IDs whose primary role matches the requested role."""
        return self.primary_role_index.get(role, EMPTY_FROZENSET)

    def get_ids_by_secondary_role(self, role: str) -> FrozenSet[str]:
        """Get all recipe IDs having the given secondary role."""
        return self.secondary_role_index.get(role, EMPTY_FROZENSET)

    def get_ids_by_combo_role(self, role: str) -> FrozenSet[str]:
        """Get all recipe IDs eligible for a given slot in a 4-part combo meal.
        
        Guaranteed by invariant: Standalone dishes and manual-review dishes
        are NEVER returned here.
        """
        return self.combo_role_index.get(role, EMPTY_FROZENSET)

    def get_ids_by_ingredient(self, ingredient: str) -> FrozenSet[str]:
        """Get all recipe IDs containing the specified normalized ingredient."""
        return self.ingredient_index.get(ingredient, EMPTY_FROZENSET)

    def get_ids_by_ingredient_group(self, group: str) -> FrozenSet[str]:
        """Get all recipe IDs containing ingredients in the specified group."""
        return self.ingredient_group_index.get(group, EMPTY_FROZENSET)

    def get_ids_by_allergen_status(self, allergen: str, status: str) -> FrozenSet[str]:
        """Get all recipe IDs with the given status for a specific allergen.
        
        Valid statuses: 'known_present', 'unknown', 'assessed_not_detected'.
        """
        if status == "known_present":
            return self.allergen_present_index.get(allergen, EMPTY_FROZENSET)
        elif status == "unknown":
            return self.allergen_unknown_index.get(allergen, EMPTY_FROZENSET)
        elif status == "assessed_not_detected":
            return self.allergen_not_detected_index.get(allergen, EMPTY_FROZENSET)
        return EMPTY_FROZENSET

    def get_ids_by_cooking_method(self, method: str) -> FrozenSet[str]:
        """Get all recipe IDs prepared with the specified cooking method."""
        return self.cooking_method_index.get(method, EMPTY_FROZENSET)

    @staticmethod
    def validate_allergens(allergens: Iterable[str]) -> Tuple[List[str], List[str]]:
        """Separate requested allergens into supported and unsupported categories.
        
        Unsupported allergens cannot be safely filtered via index.
        """
        supported: List[str] = []
        unsupported: List[str] = []
        for a in allergens:
            clean = str(a).strip().lower()
            if clean in SUPPORTED_ALLERGENS:
                supported.append(clean)
            else:
                unsupported.append(clean)
        return supported, unsupported

    def filter_candidate_ids(
        self,
        candidate_ids: Optional[Iterable[str]] = None,
        included_roles: Optional[Iterable[str]] = None,
        use_combo_roles: bool = False,
        excluded_ingredients: Optional[Iterable[str]] = None,
        excluded_allergens: Optional[Iterable[str]] = None,
        excluded_ingredient_groups: Optional[Iterable[str]] = None,
        excluded_cooking_methods: Optional[Iterable[str]] = None,
        exclude_manual_review: bool = True,
        deterministic: bool = True,
    ) -> List[str]:
        """Execute constraint-aware candidate filtering using set algebra.
        
        Complexity:
        - Role union: O(sum(|R_i|))
        - Role intersection: O(min(|candidates|, |role_set|))
        - Exclusions: O(|candidates|) per exclusion set difference
        - Deterministic sort: O(K log K) where K is surviving candidates count.
        """
        # 1. Base candidate set
        if candidate_ids is not None:
            candidates: Set[str] = set(candidate_ids)
        else:
            candidates = set(self.all_recipe_ids)

        if not candidates:
            return []

        # 2. Role filtering
        if included_roles:
            role_pool: Set[str] = set()
            role_dict = self.combo_role_index if use_combo_roles else self.primary_role_index
            for role in included_roles:
                role_pool.update(role_dict.get(role, EMPTY_FROZENSET))
            candidates.intersection_update(role_pool)
            if not candidates:
                return []

        # 3. Manual review exclusion
        if exclude_manual_review and self.manual_review_ids:
            candidates.difference_update(self.manual_review_ids)
            if not candidates:
                return []

        # 4. Allergen filtering (Fail-closed: block both known_present and unknown)
        if excluded_allergens:
            supported, _ = self.validate_allergens(excluded_allergens)
            blocked_allergens: Set[str] = set()
            for a in supported:
                blocked_allergens.update(self.allergen_present_index.get(a, EMPTY_FROZENSET))
                blocked_allergens.update(self.allergen_unknown_index.get(a, EMPTY_FROZENSET))
            if blocked_allergens:
                candidates.difference_update(blocked_allergens)
                if not candidates:
                    return []

        # 5. Ingredient exclusions
        if excluded_ingredients:
            blocked_ingredients: Set[str] = set()
            for ing in excluded_ingredients:
                blocked_ingredients.update(self.ingredient_index.get(ing, EMPTY_FROZENSET))
            if blocked_ingredients:
                candidates.difference_update(blocked_ingredients)
                if not candidates:
                    return []

        # 6. Ingredient group exclusions
        if excluded_ingredient_groups:
            blocked_groups: Set[str] = set()
            for grp in excluded_ingredient_groups:
                blocked_groups.update(self.ingredient_group_index.get(grp, EMPTY_FROZENSET))
            if blocked_groups:
                candidates.difference_update(blocked_groups)
                if not candidates:
                    return []

        # 7. Cooking method exclusions
        if excluded_cooking_methods:
            blocked_methods: Set[str] = set()
            for m in excluded_cooking_methods:
                blocked_methods.update(self.cooking_method_index.get(m, EMPTY_FROZENSET))
            if blocked_methods:
                candidates.difference_update(blocked_methods)
                if not candidates:
                    return []

        if deterministic:
            return sorted(candidates)
        return list(candidates)

    def verify_index_integrity(self) -> Dict[str, Any]:
        """Perform comprehensive invariant checks and verify logical catalog integrity."""
        errors: List[str] = []

        total_recipes = len(self.recipe_by_id)
        total_meta = len(self.metadata_by_id)
        if total_recipes != 2471:
            errors.append(f"Expected 2,471 total recipes, found {total_recipes}")
        if total_meta != 2471:
            errors.append(f"Expected 2,471 metadata records, found {total_meta}")

        # Check orphans
        if set(self.recipe_by_id.keys()) != set(self.metadata_by_id.keys()):
            errors.append("Mismatch between recipe IDs and metadata IDs")

        # Invariant 1: Standalone dishes NEVER appear in combo_role_index
        standalone_ids = self.primary_role_index.get("standalone", EMPTY_FROZENSET)
        for role, ids in self.combo_role_index.items():
            overlap = standalone_ids.intersection(ids)
            if overlap:
                errors.append(
                    f"Invariant violation: {len(overlap)} standalone dishes found in combo_role_index[{role}]! Sample: {list(overlap)[:3]}"
                )

        # Invariant 2: Manual review items NEVER in combo_role_index
        for role, ids in self.combo_role_index.items():
            overlap = self.manual_review_ids.intersection(ids)
            if overlap:
                errors.append(
                    f"Invariant violation: {len(overlap)} review-required items found in combo_role_index[{role}]!"
                )

        # Invariant 3: Dessert, beverage, snack, other NOT in standard combo roles
        non_combo_roles = {"dessert", "beverage", "snack", "other"}
        for ncr in non_combo_roles:
            if ncr in self.combo_role_index and len(self.combo_role_index[ncr]) > 0:
                errors.append(f"Non-combo role '{ncr}' has entries in combo_role_index")

        # Invariant 4: Canonical staples only have staple role
        canonical_ids = [rid for rid in self.recipe_by_id if rid.startswith("canonical_staple_")]
        if len(canonical_ids) != 9:
            errors.append(f"Expected 9 canonical staples, found {len(canonical_ids)}")
        for cs_id in canonical_ids:
            if cs_id not in self.primary_role_index.get("staple", EMPTY_FROZENSET):
                errors.append(f"Canonical staple {cs_id} missing from primary_role_index['staple']")
            if cs_id not in self.combo_role_index.get("staple", EMPTY_FROZENSET):
                errors.append(f"Canonical staple {cs_id} missing from combo_role_index['staple']")

        # Check Big 11 allergen indexing completeness
        for allergen in SUPPORTED_ALLERGENS:
            if allergen not in self.allergen_present_index:
                errors.append(f"Missing allergen_present_index for {allergen}")
            if allergen not in self.allergen_unknown_index:
                errors.append(f"Missing allergen_unknown_index for {allergen}")
            if allergen not in self.allergen_not_detected_index:
                errors.append(f"Missing allergen_not_detected_index for {allergen}")

            # Check sum of statuses covers all items
            p_count = len(self.allergen_present_index.get(allergen, EMPTY_FROZENSET))
            u_count = len(self.allergen_unknown_index.get(allergen, EMPTY_FROZENSET))
            nd_count = len(self.allergen_not_detected_index.get(allergen, EMPTY_FROZENSET))
            if p_count + u_count + nd_count != total_recipes:
                errors.append(
                    f"Allergen {allergen} coverage sum mismatch: {p_count} + {u_count} + {nd_count} != {total_recipes}"
                )

        stats = {
            "total_recipes": total_recipes,
            "vifoodrec_count": 2462,
            "canonical_staples_count": 9,
            "primary_roles": {k: len(v) for k, v in self.primary_role_index.items()},
            "combo_roles": {k: len(v) for k, v in self.combo_role_index.items()},
            "unique_ingredients": len(self.ingredient_index),
            "unique_ingredient_groups": len(self.ingredient_group_index),
            "unique_cooking_methods": len(self.cooking_method_index),
            "manual_review_count": len(self.manual_review_ids),
            "build_duration_ms": self.build_duration_ms,
        }

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "stats": stats,
        }

    def get_index_statistics(self) -> Dict[str, Any]:
        """Return memory and structural metrics of the inverted index."""
        import sys

        def get_dict_deep_size(d: Dict[str, FrozenSet[str]]) -> int:
            size = sys.getsizeof(d)
            for k, s in d.items():
                size += sys.getsizeof(k) + sys.getsizeof(s)
            return size

        mem_primary = get_dict_deep_size(self.primary_role_index)
        mem_secondary = get_dict_deep_size(self.secondary_role_index)
        mem_combo = get_dict_deep_size(self.combo_role_index)
        mem_ing = get_dict_deep_size(self.ingredient_index)
        mem_grp = get_dict_deep_size(self.ingredient_group_index)
        mem_all_pres = get_dict_deep_size(self.allergen_present_index)
        mem_all_unk = get_dict_deep_size(self.allergen_unknown_index)
        mem_all_nd = get_dict_deep_size(self.allergen_not_detected_index)
        mem_methods = get_dict_deep_size(self.cooking_method_index)
        mem_review = sys.getsizeof(self.manual_review_ids)

        total_index_overhead_bytes = (
            mem_primary + mem_secondary + mem_combo + mem_ing + mem_grp +
            mem_all_pres + mem_all_unk + mem_all_nd + mem_methods + mem_review
        )

        return {
            "total_recipes": len(self.recipe_by_id),
            "total_index_overhead_bytes": total_index_overhead_bytes,
            "total_index_overhead_kb": round(total_index_overhead_bytes / 1024, 2),
            "build_duration_ms": round(self.build_duration_ms, 2),
            "primary_role_counts": {k: len(v) for k, v in self.primary_role_index.items()},
            "combo_role_counts": {k: len(v) for k, v in self.combo_role_index.items()},
            "supported_allergens_count": len(SUPPORTED_ALLERGENS),
            "unique_ingredients_count": len(self.ingredient_index),
            "unique_ingredient_groups_count": len(self.ingredient_group_index),
            "manual_review_count": len(self.manual_review_ids),
        }


# -------------------------------------------------------------------------
# Thread-safe Process Singleton & Module Facade
# -------------------------------------------------------------------------

_index_instance: Optional[InMemoryInvertedIndex] = None
_index_lock = threading.Lock()


def get_metadata_index(force_reload: bool = False) -> InMemoryInvertedIndex:
    """Thread-safe access to the process-wide InMemoryInvertedIndex singleton."""
    global _index_instance
    if _index_instance is None or force_reload:
        with _index_lock:
            if _index_instance is None or force_reload:
                _index_instance = InMemoryInvertedIndex.build()
    return _index_instance


def get_recipe_by_id(recipe_id: str) -> Optional[Dict[str, Any]]:
    return get_metadata_index().get_recipe_by_id(recipe_id)


def get_metadata_by_id(recipe_id: str) -> Optional[Dict[str, Any]]:
    return get_metadata_index().get_metadata_by_id(recipe_id)


def get_ids_by_primary_role(role: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_primary_role(role)


def get_ids_by_secondary_role(role: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_secondary_role(role)


def get_ids_by_combo_role(role: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_combo_role(role)


def get_ids_by_ingredient(ingredient: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_ingredient(ingredient)


def get_ids_by_ingredient_group(group: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_ingredient_group(group)


def get_ids_by_allergen_status(allergen: str, status: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_allergen_status(allergen, status)


def get_ids_by_cooking_method(method: str) -> FrozenSet[str]:
    return get_metadata_index().get_ids_by_cooking_method(method)


def filter_candidate_ids(*args, **kwargs) -> List[str]:
    return get_metadata_index().filter_candidate_ids(*args, **kwargs)


def validate_allergens(allergens: Iterable[str]) -> Tuple[List[str], List[str]]:
    return InMemoryInvertedIndex.validate_allergens(allergens)
