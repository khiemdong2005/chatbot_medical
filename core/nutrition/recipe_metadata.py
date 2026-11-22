"""Recipe Metadata Management and Canonical Staples Provider.

Provides normalized metadata sidecar for ViFoodRec recipes and Canonical Staples.
Maintains zero mutations on the raw dataset files.
"""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "recipes"
METADATA_PATH = DATA_ROOT / "vifoodrec" / "recipes_metadata.json"
CANONICAL_STAPLES_PATH = DATA_ROOT / "canonical_staples.json"

METADATA_VERSION = "1.1.0"
DATASET_VERSION = "vifoodrec_clean_paclic2024"


@lru_cache(maxsize=2)
def load_canonical_staples() -> List[Dict[str, Any]]:
    """Load verified plain staple recipes (e.g. steamed rice, brown rice, boiled sweet potato)."""
    if not CANONICAL_STAPLES_PATH.exists():
        return []
    with open(CANONICAL_STAPLES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=2)
def load_recipe_metadata_map() -> Dict[str, Dict[str, Any]]:
    """Load normalized metadata sidecar mapped by recipe ID."""
    if not METADATA_PATH.exists():
        return {}
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {item["id"]: item for item in raw if isinstance(item, dict) and "id" in item}
    return {}


def get_recipe_metadata(recipe_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve metadata entry for a given recipe ID."""
    meta_map = load_recipe_metadata_map()
    if recipe_id in meta_map:
        return meta_map[recipe_id]

    # Check canonical staples
    for staple in load_canonical_staples():
        if staple.get("id") == recipe_id:
            role = staple.get("primary_role") or staple.get("meal_role", "staple")
            return {
                "id": staple["id"],
                "title": staple.get("title", ""),
                "meal_role": role,
                "primary_role": role,
                "secondary_roles": staple.get("secondary_roles", []),
                "eligible_combo_roles": staple.get("eligible_combo_roles", ["staple"]),
                "classification_confidence": 1.0,
                "classification_source": "canonical_staple_seed",
                "review_required": False,
                "normalized_ingredients": staple.get("normalized_ingredients", []),
                "ingredient_groups": staple.get("ingredient_groups", ["grain"]),
                "allergen_tags": staple.get("allergen_tags", []),
                "allergen_unknown_tags": [],
                "allergen_status": staple.get("allergen_status", "assessed_not_detected"),
                "allergen_assessments": staple.get("allergen_assessments", {}),
                "cooking_methods": staple.get("cooking_methods", []),
                "servings_numeric": staple.get("servings_numeric", 1.0),
                "calories_per_serving": staple.get("calories", 0),
                "macro_consistency": True,
                "nutrition_verified": staple.get("nutrition_verified", True),
                "nutrition_basis": staple.get("nutrition_basis", "per_reference_serving_150g"),
                "has_carbohydrate_data": True,
                "image_link": staple.get("image_link", ""),
                "source_image_url": staple.get("source_image_url", ""),
                "metadata_version": METADATA_VERSION,
                "dataset_version": "canonical_staples_v1"
            }
    return None


def get_all_canonical_staples() -> List[Dict[str, Any]]:
    """Get all canonical staples for dynamic meal composition."""
    return load_canonical_staples()


def clear_metadata_cache():
    """Clear memory caches (useful for testing or after data re-generation)."""
    load_canonical_staples.cache_clear()
    load_recipe_metadata_map.cache_clear()
