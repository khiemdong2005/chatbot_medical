"""Clinical Constraint Resolver.

Consolidates, parses, and resolves medical conditions, allergies, dietary constraints,
and personal preferences from User Profiles and request queries.
Enforces the clinical priority hierarchy and conflict resolution rules.
"""

from copy import deepcopy
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import unicodedata

from core.nutrition.clinical_constraints import (
    CLINICAL_RULES,
    ClinicalRuleDefinition,
    ConstraintSeverity,
    ConstraintType,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.metadata_index import SUPPORTED_ALLERGENS

logger = logging.getLogger(__name__)


def _normal(text: str) -> str:
    """Normalize text without accents, lowercased, single spaces."""
    norm = unicodedata.normalize("NFD", str(text).lower().replace("_", " "))
    return " ".join("".join(c for c in norm if unicodedata.category(c) != "Mn").replace("đ", "d").split())


# Allergen alias mapping for Vietnamese culinary phrases and canonical codes
ALLERGEN_ALIASES_VI: Dict[str, str] = {
    # Canonical IDs
    "shrimp": "shrimp", "crab": "crab", "squid_octopus": "squid_octopus", "squid octopus": "squid_octopus",
    "fish": "fish", "mollusk": "mollusk", "peanut": "peanut", "sesame": "sesame", "egg": "egg",
    "cow_milk": "cow_milk", "cow milk": "cow_milk", "milk": "cow_milk",
    "soy": "soy", "wheat_gluten": "wheat_gluten", "wheat gluten": "wheat_gluten", "gluten": "wheat_gluten",

    # Vietnamese aliases
    "tom": "shrimp", "tep": "shrimp", "prawn": "shrimp",
    "cua": "crab", "ghe": "crab",
    "muc": "squid_octopus", "bach tuoc": "squid_octopus", "squid": "squid_octopus", "octopus": "squid_octopus",
    "ca": "fish", "nuoc mam": "fish",
    "ngheu": "mollusk", "so": "mollusk", "oc": "mollusk", "hau": "mollusk", "hen": "mollusk",
    "dau hao": "mollusk",
    "dau phong": "peanut", "lac": "peanut", "groundnut": "peanut",
    "me": "sesame", "vung": "sesame",
    "trung": "egg", "trung ga": "egg", "trung vit": "egg", "mayonnaise": "egg",
    "sua": "cow_milk", "sua bo": "cow_milk", "sua tuoi": "cow_milk", "pho mai": "cow_milk", "bo": "cow_milk",
    "dau nanh": "soy", "dau hu": "soy", "tau hu": "soy", "nuoc tuong": "soy", "xi dau": "soy",
    "bot mi": "wheat_gluten", "banh mi": "wheat_gluten", "mi soi": "wheat_gluten", "wheat": "wheat_gluten"
}

# Expand broad allergy declarations into groups that the catalog tracks
# individually. The index filters both known and uncertain matches.
_SHELLFISH_ALLERGENS = frozenset({"shrimp", "crab", "squid_octopus", "mollusk"})
ALLERGEN_GROUPS = {
    "hai san": _SHELLFISH_ALLERGENS | {"fish"},
    "seafood": _SHELLFISH_ALLERGENS | {"fish"},
    "hai san co vo": _SHELLFISH_ALLERGENS,
    "shellfish": _SHELLFISH_ALLERGENS,
}

# Known unsupported allergens that require immediate fail-closed handling
UNSUPPORTED_ALLERGEN_ALIASES: Dict[str, str] = {
    "hat cay": "tree_nuts", "tree nuts": "tree_nuts", "tree nut": "tree_nuts",
    "hat dieu": "tree_nuts", "cashew": "tree_nuts",
    "hanh nhan": "tree_nuts", "almond": "tree_nuts",
    "oc cho": "tree_nuts", "walnut": "tree_nuts",
    "hat de": "tree_nuts", "chestnut": "tree_nuts",
    "macadamia": "tree_nuts", "hazelnut": "tree_nuts", "pecan": "tree_nuts",
    "kiwi": "kiwi", "sulfite": "sulfites", "sulfites": "sulfites",
    "lupin": "lupin", "mu tat": "mustard", "mustard": "mustard",
    "can tay": "celery", "celery": "celery"
}

# Medical conditions mapped to rules
CONDITION_ALIASES: Dict[str, str] = {
    # Acute / Clinical Gout
    "gut": "gout", "gout": "gout", "benh gut": "gout", "benh gout": "gout", "viem khop gut": "gout",

    # Hyperuricemia (asymptomatic elevated uric acid, portion-dependent management)
    "tang acid uric": "hyperuricemia", "acid uric cao": "hyperuricemia", "acid uric": "hyperuricemia",
    "tang axit uric": "hyperuricemia", "axit uric cao": "hyperuricemia", "axit uric": "hyperuricemia",

    # Diabetes
    "tieu duong": "diabetes", "dai thao duong": "diabetes", "duong huyet cao": "diabetes",
    "duong cao": "diabetes", "diabetes": "diabetes", "benh tieu duong": "diabetes",
    "tieu duong type 2": "diabetes", "dai thao duong type 2": "diabetes",

    # Fatty liver
    "gan nhiem mo": "fatty_liver", "benh gan nhiem mo": "fatty_liver",
    "fatty liver": "fatty_liver", "nafld": "fatty_liver", "masld": "fatty_liver",

    # Hypertension
    "huyet ap cao": "hypertension", "tang huyet ap": "hypertension",
    "cao huyet ap": "hypertension", "hypertension": "hypertension", "high blood pressure": "hypertension",

    # GERD / Reflux
    "trao nguoc": "gerd", "trao nguoc da day": "gerd", "gerd": "gerd",
    "acid reflux": "gerd", "viem thuc quan trao nguoc": "gerd",

    # Celiac / Gluten
    "celiac": "celiac", "coeliac": "celiac", "benh celiac": "celiac",
    "di ung gluten": "celiac", "kieng gluten": "celiac",

    # Chronic Kidney Disease
    "ckd": "ckd", "suy than": "ckd", "benh than man": "ckd", "than yeu": "ckd",
    "kidney disease": "ckd", "renal failure": "ckd",

    # Gastritis / Stomach
    "dau da day": "stomach", "viem da day": "stomach", "loet da day": "stomach",
    "gastritis": "stomach", "dau bao tu": "stomach",

    # General / Minor conditions
    "nhiet mieng": "mouth", "loet mieng": "mouth",
    "sot": "fever", "bi sot": "fever",
    "mat ngu": "sleep", "kho ngu": "sleep",
    "khoe manh": "healthy", "an lanh manh": "healthy", "healthy": "healthy"
}

# Food and cooking exclusion token mapping
FOOD_EXCLUSION_MAPPINGS: Dict[str, Tuple[str, Any]] = {
    "do chien": ("cooking_method", "deep_frying"),
    "mon chien": ("cooking_method", "deep_frying"),
    "chien": ("cooking_method", "deep_frying"),
    "do ran": ("cooking_method", "deep_frying"),
    "ran": ("cooking_method", "deep_frying"),

    "thit bo": ("ingredient_and_group", "beef"),
    "bo": ("ingredient_and_group", "beef"),
    "beef": ("ingredient_and_group", "beef"),

    "thit heo": ("ingredient", "pork"),
    "thit lon": ("ingredient", "pork"),
    "heo": ("ingredient", "pork"),
    "lon": ("ingredient", "pork"),
    "pork": ("ingredient", "pork"),

    "thit ga": ("ingredient", "chicken"),
    "ga": ("ingredient", "chicken"),
    "chicken": ("ingredient", "chicken"),
    "thit gia cam": ("ingredient_group", "poultry"),
    "gia cam": ("ingredient_group", "poultry"),
    "poultry": ("ingredient_group", "poultry"),

    "thit vit": ("ingredient", "duck"),
    "vit": ("ingredient", "duck"),
    "duck": ("ingredient", "duck"),

    "hai san": ("ingredient_group", "seafood"),
    "seafood": ("ingredient_group", "seafood"),

    "ca": ("ingredient_group", "fish"),
    "fish": ("ingredient_group", "fish"),

    "trung": ("ingredient_group", "egg"),
    "egg": ("ingredient_group", "egg"),
    "trung ga": ("ingredient", "chicken_egg"),
    "trung vit": ("ingredient", "duck_egg"),

    "com": ("ingredient", "rice"),
    "gao": ("ingredient", "rice"),
    "rice": ("ingredient", "rice"),

    "tinh bot": ("ingredient_group", "grain"),
    "grain": ("ingredient_group", "grain"),

    "dam": ("ingredient_groups_multi", ["meat", "poultry", "fish", "seafood", "egg", "legume"]),
    "thit": ("ingredient_groups_multi", ["meat", "poultry"]),

    "rau": ("ingredient_group", "vegetable"),
    "rau cu": ("ingredient_group", "vegetable"),
    "vegetable": ("ingredient_group", "vegetable"),

    "dau": ("ingredient_group", "legume"),
    "do": ("ingredient_group", "legume"),
    "legume": ("ingredient_group", "legume"),

    "dau hu": ("ingredient", "tofu"),
    "dau phu": ("ingredient", "tofu"),
    "tau hu": ("ingredient", "tofu"),

    "do ngot": ("role", "dessert"),
    "trang mieng": ("role", "dessert"),
    "che": ("role", "dessert"),
    "dessert": ("role", "dessert"),

    "nuoc": ("role", "beverage"),
    "do uong": ("role", "beverage"),
    "beverage": ("role", "beverage"),

    "an vat": ("role", "snack"),
    "do an vat": ("role", "snack"),
    "snack": ("role", "snack"),

    "mon mot dia": ("role", "standalone"),
    "mon an mot dia": ("role", "standalone"),
    "standalone": ("role", "standalone"),

    "mon man": ("role", "main_dish"),
    "canh": ("role", "soup"),
    "mon canh": ("role", "soup"),
    "mon rau": ("role", "vegetable"),
    "mon xao": ("role", "vegetable"),

    "tat ca cac mon": ("role_all", ["staple", "main_dish", "soup", "vegetable", "standalone", "beverage", "dessert", "snack", "other"]),
    "tat ca": ("role_all", ["staple", "main_dish", "soup", "vegetable", "standalone", "beverage", "dessert", "snack", "other"]),
    "all food": ("role_all", ["staple", "main_dish", "soup", "vegetable", "standalone", "beverage", "dessert", "snack", "other"]),
    "all": ("role_all", ["staple", "main_dish", "soup", "vegetable", "standalone", "beverage", "dessert", "snack", "other"]),
}

# Cooking method preference mapping
COOKING_METHOD_PREFERENCE_ALIASES: Dict[str, str] = {
    "steaming": "steaming",
    "hap": "steaming",
    "do hap": "steaming",
    "mon hap": "steaming",
    "stir_frying": "stir_frying",
    "xao": "stir_frying",
    "do xao": "stir_frying",
    "mon xao": "stir_frying",
    "boiling": "boiling",
    "luoc": "boiling",
    "canh": "boiling",
    "nau canh": "boiling",
    "grilling": "grilling",
    "nuong": "grilling",
    "do nuong": "grilling",
    "mon nuong": "grilling",
    "braising": "braising",
    "kho": "braising",
    "mon kho": "braising",
    "deep_frying": "deep_frying",
    "chien": "deep_frying",
    "ran": "deep_frying",
    "raw_fresh": "raw_fresh",
    "song": "raw_fresh",
    "goi": "raw_fresh",
    "salad": "raw_fresh",
}

# Dangerous / complex unmapped diseases that require clinical safeguard refusal
UNMAPPED_DISEASE_PATTERN = re.compile(
    r"\b(?:ung\s+thu|cancer|xo\s+gan|cirrhosis|suy\s+tim|heart\s+failure|tai\s+bien|dot\s+quy|stroke|"
    r"nhiem\s+trung\s+huyet|sepsis|tuy\s+cap|pancreatitis|mang\s+thai|thai\s+ky|pregnant|pregnancy|"
    r"suy\s+ho\s+hap|xuat\s+huyet|dong\s+kinh|epilepsy)\b",
    re.IGNORECASE
)


class ConstraintResolver:
    """Consolidates profile information and request parameters into strict ResolvedConstraints."""

    @classmethod
    def resolve_constraints(
        cls,
        profile: Optional[Dict[str, Any]] = None,
        condition_query: Optional[str] = None,
        recipe_type: str = "food",
        exclude_recipe_ids: Optional[Iterable[str]] = None,
        user_disliked_ingredients: Optional[Iterable[str]] = None,
        user_preferences: Optional[Iterable[str]] = None,
    ) -> ResolvedConstraints:
        """Resolve all constraints following the clinical priority hierarchy."""
        resolved = ResolvedConstraints()
        profile = profile or {}

        # 1. Parse and extract exclusions from exclude_recipe_ids
        if exclude_recipe_ids:
            resolved.hard_excluded_recipe_ids.update(exclude_recipe_ids)

        # 2. Extract conditions, allergies, negations, and food exclusions from condition_query
        query_text = str(condition_query or "").strip()
        parsed_conditions, parsed_allergies, unsupported_found, parsed_food_excl, is_unmapped = cls._parse_query_text(query_text)

        # 3. Check for unmapped severe diseases -> trigger safeguard refusal
        if is_unmapped:
            resolved.is_safe_to_proceed = False
            resolved.is_unmapped_disease = True
            resolved.safety_status = SafetyStatus.UNMAPPED_DISEASE_SAFEGUARD
            resolved.safety_halt_reason = SafetyStatus.UNMAPPED_DISEASE_SAFEGUARD.value
            resolved.refusal_notice = (
                "Tình trạng trong yêu cầu là bệnh lý phức tạp cần chế độ dinh dưỡng lâm sàng chuyên biệt "
                "được bác sĩ chỉ định. Hệ thống kích hoạt rào chắn an toàn (Clinical Safeguard), không tự ý đề xuất món."
            )
            resolved.warnings.append(resolved.refusal_notice)
            return resolved

        # 4. Integrate profile conditions & comorbidities
        profile_conditions = profile.get("conditions") or []
        if isinstance(profile_conditions, str):
            profile_conditions = [profile_conditions]

        all_conditions: Set[str] = set(parsed_conditions)
        for cond_str in profile_conditions:
            clean_c = _normal(cond_str)
            if clean_c in CONDITION_ALIASES:
                all_conditions.add(CONDITION_ALIASES[clean_c])

        # 5. Integrate profile allergies
        profile_allergies = profile.get("allergies") or []
        if isinstance(profile_allergies, str):
            profile_allergies = [a.strip() for a in profile_allergies.replace(";", ",").split(",") if a.strip()]

        for a_str in profile_allergies:
            norm_a = _normal(a_str)
            if norm_a in ("khong", "khong co", "none"):
                continue
            if norm_a in ALLERGEN_GROUPS:
                parsed_allergies.update(ALLERGEN_GROUPS[norm_a])
            elif norm_a in ALLERGEN_ALIASES_VI:
                parsed_allergies.add(ALLERGEN_ALIASES_VI[norm_a])
            elif norm_a in UNSUPPORTED_ALLERGEN_ALIASES:
                unsupported_found.append(UNSUPPORTED_ALLERGEN_ALIASES[norm_a])
            else:
                unsupported_found.append(a_str)

        # 6. Safety check for unsupported allergens (Fail-closed)
        if unsupported_found:
            resolved.unsupported_allergens.extend(sorted(list(set(unsupported_found))))
            resolved.is_safe_to_proceed = False
            resolved.safety_status = SafetyStatus.UNSUPPORTED_ALLERGEN_HALT
            resolved.safety_halt_reason = SafetyStatus.UNSUPPORTED_ALLERGEN_HALT.value
            warning_msg = (
                f"Chất dị ứng '{', '.join(resolved.unsupported_allergens)}' chưa có phân loại riêng trong cơ sở dữ liệu. "
                "Để đảm bảo an toàn y tế, hệ thống không tự động gợi ý món khi chưa kiểm định được dị nguyên này."
            )
            resolved.warnings.append(warning_msg)
            return resolved

        # 7. Apply Hard Safety Constraints: Allergens (Highest Priority)
        for allergen in parsed_allergies:
            if allergen in SUPPORTED_ALLERGENS:
                resolved.hard_excluded_allergens.add(allergen)
            else:
                resolved.unsupported_allergens.append(allergen)

        # Special distinction: Celiac Disease vs Wheat Allergy
        if "celiac" in all_conditions:
            resolved.hard_excluded_allergens.add("wheat_gluten")
            resolved.hard_excluded_ingredients.add("barley")
            resolved.hard_excluded_ingredients.add("oats")  # unverified oats in catalog must be excluded for Celiac
            resolved.applied_rules.append(CLINICAL_RULES["RULE_CELIAC_GLUTEN_FREE"])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_CELIAC_GLUTEN_FREE"].source_name,
                "source_url": CLINICAL_RULES["RULE_CELIAC_GLUTEN_FREE"].source_url
            })

        # 8. Check Chronic Kidney Disease (CKD) safeguard
        if "ckd" in all_conditions:
            resolved.is_safe_to_proceed = False
            resolved.safety_status = SafetyStatus.INSUFFICIENT_CLINICAL_DATA
            resolved.safety_halt_reason = "CKD_INSUFFICIENT_CLINICAL_DATA"
            ckd_msg = (
                "Bệnh thận mạn tính (CKD) yêu cầu đánh giá độ lọc cầu thận (eGFR), giai đoạn bệnh và chỉ định "
                "phân bổ protein/kali/phospho của bác sĩ chuyên khoa thận. Hệ thống kích hoạt rào chắn an toàn, không tự ý tạo thực đơn."
            )
            resolved.unresolved_constraints.append("ckd_stage_unspecified")
            resolved.warnings.append(ckd_msg)
            resolved.applied_rules.append(CLINICAL_RULES["RULE_CKD_SAFEGUARD"])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_CKD_SAFEGUARD"].source_name,
                "source_url": CLINICAL_RULES["RULE_CKD_SAFEGUARD"].source_url
            })
            return resolved

        # 9. Apply Disease-Specific Clinical Rules & Contraindications
        # --- GOUT (ACUTE CLINICAL GOUT) ---
        if "gout" in all_conditions:
            # Organ meat is a hard medical contraindication (>300mg purin/100g)
            resolved.hard_excluded_ingredient_groups.add("organ_meat")
            resolved.hard_excluded_ingredients.add("alcohol")
            # Red meat, sausage/processed meats & seafood are portion-dependent recommendations (soft restriction)
            resolved.soft_avoided_ingredients.update(["beef", "sausage"])
            resolved.soft_avoided_ingredient_groups.add("seafood")
            resolved.soft_preferred_ingredient_groups.add("vegetable")
            resolved.applied_rules.extend([
                CLINICAL_RULES["RULE_GOUT_ORGAN_MEATS"],
                CLINICAL_RULES["RULE_GOUT_ALCOHOL"],
                CLINICAL_RULES["RULE_GOUT_SEAFOOD_LIMIT"],
                CLINICAL_RULES["RULE_GOUT_RED_MEAT_LIMIT"],
            ])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_GOUT_ORGAN_MEATS"].source_name,
                "source_url": CLINICAL_RULES["RULE_GOUT_ORGAN_MEATS"].source_url
            })

        # --- HYPERURICEMIA (PORTION-DEPENDENT MANAGEMENT, NOT ACUTE GOUT) ---
        elif "hyperuricemia" in all_conditions:
            resolved.soft_avoided_ingredients.update(["beef", "sausage"])
            resolved.soft_avoided_ingredient_groups.add("seafood")
            resolved.soft_preferred_ingredient_groups.add("vegetable")
            resolved.applied_rules.extend([
                CLINICAL_RULES["RULE_GOUT_SEAFOOD_LIMIT"],
                CLINICAL_RULES["RULE_GOUT_RED_MEAT_LIMIT"],
            ])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_GOUT_SEAFOOD_LIMIT"].source_name,
                "source_url": CLINICAL_RULES["RULE_GOUT_SEAFOOD_LIMIT"].source_url
            })

        # --- DIABETES (TYPE 2) ---
        if "diabetes" in all_conditions:
            # Product-level conservative policy: exclude dessert role to avoid high added sugar
            resolved.hard_excluded_roles.add("dessert")
            resolved.nutrient_limits["sugar"] = "low"
            resolved.soft_avoided_ingredients.add("sausage")
            resolved.soft_preferred_ingredient_groups.add("vegetable")
            resolved.soft_preferred_ingredient_groups.add("grain")
            resolved.applied_rules.extend([
                CLINICAL_RULES["RULE_DIABETES_FREE_SUGARS"],
                CLINICAL_RULES["RULE_DIABETES_SUGAR_SWEETENED_BEV"],
                CLINICAL_RULES["RULE_DIABETES_FIBER_PREFERENCE"],
            ])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_DIABETES_FREE_SUGARS"].source_name,
                "source_url": CLINICAL_RULES["RULE_DIABETES_FREE_SUGARS"].source_url
            })

        # --- FATTY LIVER (MASLD / NAFLD) ---
        if "fatty_liver" in all_conditions:
            resolved.hard_excluded_ingredients.add("alcohol")
            resolved.hard_excluded_cooking_methods.add("deep_frying")
            resolved.soft_avoided_cooking_methods.add("frying")
            resolved.soft_preferred_cooking_methods.update(["steaming", "boiling"])
            resolved.applied_rules.extend([
                CLINICAL_RULES["RULE_FATTY_LIVER_ALCOHOL"],
                CLINICAL_RULES["RULE_FATTY_LIVER_DEEP_FRIED"],
            ])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_FATTY_LIVER_ALCOHOL"].source_name,
                "source_url": CLINICAL_RULES["RULE_FATTY_LIVER_ALCOHOL"].source_url
            })

        # --- HYPERTENSION ---
        if "hypertension" in all_conditions:
            resolved.hard_excluded_ingredients.add("alcohol")
            resolved.nutrient_limits["sodium"] = "low"
            resolved.soft_avoided_ingredients.update(["pickled_vegetables", "fish_sauce_heavy"])
            resolved.applied_rules.append(CLINICAL_RULES["RULE_HYPERTENSION_SALT_PRESERVED"])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_HYPERTENSION_SALT_PRESERVED"].source_name,
                "source_url": CLINICAL_RULES["RULE_HYPERTENSION_SALT_PRESERVED"].source_url
            })

        # --- GERD ---
        if "gerd" in all_conditions:
            resolved.soft_avoided_ingredients.update(["chili", "pepper", "mint", "caffeine", "alcohol"])
            resolved.soft_avoided_cooking_methods.add("deep_frying")
            resolved.applied_rules.append(CLINICAL_RULES["RULE_GERD_TRIGGER_EXCLUSION"])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_GERD_TRIGGER_EXCLUSION"].source_name,
                "source_url": CLINICAL_RULES["RULE_GERD_TRIGGER_EXCLUSION"].source_url
            })

        # --- HEALTHY EATING ---
        if "healthy" in all_conditions or not all_conditions:
            resolved.applied_rules.append(CLINICAL_RULES["RULE_HEALTHY_BALANCED"])
            resolved.source_references.append({
                "source_title": CLINICAL_RULES["RULE_HEALTHY_BALANCED"].source_name,
                "source_url": CLINICAL_RULES["RULE_HEALTHY_BALANCED"].source_url
            })

        # 10. Integrate User Dislikes & Mandatory Exclusions from profile and parsed query
        all_dislikes = list(user_disliked_ingredients or []) + list(profile.get("disliked_ingredients") or [])
        for d in all_dislikes:
            clean_d = _normal(d)
            if clean_d in FOOD_EXCLUSION_MAPPINGS:
                kind, token = FOOD_EXCLUSION_MAPPINGS[clean_d]
                if kind == "cooking_method":
                    resolved.hard_excluded_cooking_methods.add(token)
                elif kind == "ingredient":
                    resolved.hard_excluded_ingredients.add(token)
                elif kind == "ingredient_and_group":
                    resolved.hard_excluded_ingredients.add(token)
                    resolved.hard_excluded_ingredient_groups.add(token)
                elif kind == "ingredient_group":
                    resolved.hard_excluded_ingredient_groups.add(token)
                elif kind == "ingredient_groups_multi":
                    resolved.hard_excluded_ingredient_groups.update(token)
                elif kind == "role":
                    resolved.hard_excluded_roles.add(token)
                elif kind == "role_all":
                    resolved.hard_excluded_roles.update(token)
            else:
                resolved.hard_excluded_ingredients.add(clean_d)

        for kind, token in parsed_food_excl:
            if kind == "cooking_method":
                resolved.hard_excluded_cooking_methods.add(token)
            elif kind == "ingredient":
                resolved.hard_excluded_ingredients.add(token)
            elif kind == "ingredient_and_group":
                resolved.hard_excluded_ingredients.add(token)
                resolved.hard_excluded_ingredient_groups.add(token)
            elif kind == "ingredient_group":
                resolved.hard_excluded_ingredient_groups.add(token)
            elif kind == "ingredient_groups_multi":
                resolved.hard_excluded_ingredient_groups.update(token)
            elif kind == "role":
                resolved.hard_excluded_roles.add(token)
            elif kind == "role_all":
                resolved.hard_excluded_roles.update(token)

        # 11. Parse Query & Profile Preferences (Strictly User Preferences, isolated from clinical directives)
        prefs = list(user_preferences or []) + list(profile.get("preferences") or [])
        if query_text:
            for pref_match in re.finditer(r"\b(?:thich|khoai|chuong|me)\s+(?:an\s+)?([^;\n]+)", _normal(query_text)):
                pref_sub = pref_match.group(1).strip()
                for token in re.split(r"\s+(?:va|voi|cung)\s+|,", pref_sub):
                    token_c = token.strip()
                    if token_c:
                        prefs.append(token_c)

        for p in prefs:
            raw_p = _normal(str(p))
            # Clean possible leading "thich / khoai" if raw preference string had it
            clean_p = re.sub(r"^(?:thich|khoai|chuong|me)\s+(?:an\s+)?", "", raw_p).strip()
            # Split compound phrases if present (e.g. "hap luoc")
            sub_tokens = [clean_p] if clean_p in COOKING_METHOD_PREFERENCE_ALIASES or clean_p in FOOD_EXCLUSION_MAPPINGS else clean_p.split()

            for tok in sub_tokens:
                if tok in COOKING_METHOD_PREFERENCE_ALIASES:
                    resolved.user_preferred_cooking_methods.add(COOKING_METHOD_PREFERENCE_ALIASES[tok])
                elif tok in FOOD_EXCLUSION_MAPPINGS:
                    kind, token = FOOD_EXCLUSION_MAPPINGS[tok]
                    if kind == "cooking_method":
                        resolved.user_preferred_cooking_methods.add(token)
                    elif kind == "ingredient":
                        resolved.user_preferred_ingredients.add(token)
                    elif kind == "ingredient_and_group":
                        resolved.user_preferred_ingredients.add(token)
                        resolved.user_preferred_ingredient_groups.add(token)
                    elif kind == "ingredient_group":
                        resolved.user_preferred_ingredient_groups.add(token)
                    elif kind == "ingredient_groups_multi":
                        resolved.user_preferred_ingredient_groups.update(token)
                elif tok:
                    resolved.user_preferred_ingredients.add(tok)

        if re.search(r"\b(?:khong\s+chien|it\s+dau|it\s+beo|not\s+fried)\b", _normal(query_text)):
            resolved.hard_excluded_cooking_methods.add("deep_frying")
            resolved.soft_avoided_cooking_methods.add("frying")
        if re.search(r"\b(?:it\s+duong|khong\s+ngot|no\s+sugar)\b", _normal(query_text)):
            resolved.nutrient_limits["sugar"] = "low"
        if re.search(r"\b(?:it\s+muoi|khong\s+man|low\s+salt)\b", _normal(query_text)):
            resolved.nutrient_limits["sodium"] = "low"

        # Conflict resolution check: If user preference conflicts with hard exclusion, hard exclusion wins!
        for a in resolved.hard_excluded_allergens:
            if a in resolved.user_preferred_ingredients:
                resolved.user_preferred_ingredients.remove(a)
        for a in resolved.hard_excluded_allergens:
            if a in resolved.soft_preferred_ingredients:
                resolved.soft_preferred_ingredients.remove(a)

        resolved.safety_status = SafetyStatus.PASSED_KNOWN_CONSTRAINTS
        return resolved

    @classmethod
    def _parse_query_text(cls, query: str) -> Tuple[List[str], Set[str], List[str], List[Tuple[str, Any]], bool]:
        """Parse query string to identify conditions, allergies, food exclusions, and unmapped diseases."""
        if not query:
            return [], set(), [], [], False

        norm = _normal(query)

        # 1. Check unmapped severe diseases
        is_unmapped = bool(UNMAPPED_DISEASE_PATTERN.search(norm))

        conditions: List[str] = []
        allergies: Set[str] = set()
        unsupported: List[str] = []
        food_exclusions: List[Tuple[str, Any]] = []

        # Split into clauses
        clauses = re.split(r"[,;.\n]|\s+(?:nhung|va|con|kem)\s+", norm)

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            # Check disease or symptom negation ("không bị tiểu đường", "không sốt", "chưa từng mắc gút")
            is_negated_condition = bool(
                re.search(r"\b(?:khong|chua)\s+(?:bi|mac|he\s+bi|co\s+benh)\s+(\w+)", clause) or
                re.search(r"\bkhong\s+(?:sot|dau|met)\b", clause)
            )

            # Check condition aliases only if not negated
            if not is_negated_condition:
                for alias, cond_id in sorted(CONDITION_ALIASES.items(), key=lambda x: -len(x[0])):
                    if re.search(r"\b" + re.escape(alias) + r"\b", clause):
                        if cond_id not in conditions:
                            conditions.append(cond_id)

            # Check allergy patterns ("dị ứng tôm và cua", "bị dị ứng đậu phộng")
            allergy_match = re.search(r"\b(?:di\s+ung|bi\s+di\s+ung)\s+(.+)", clause)
            if allergy_match and not re.search(
                r"\b(?:khong|chua)(?:\s+(?:he|co|bi|con))*\s*$", clause[:allergy_match.start()]
            ):
                target_str = allergy_match.group(1).strip()
                sub_items = re.split(r"\s+(?:va|hoac|voi)\s+|,", target_str)
                for item in sub_items:
                    item_clean = item.strip()
                    if item_clean in ALLERGEN_GROUPS:
                        allergies.update(ALLERGEN_GROUPS[item_clean])
                    elif item_clean in ALLERGEN_ALIASES_VI:
                        allergies.add(ALLERGEN_ALIASES_VI[item_clean])
                    elif item_clean in UNSUPPORTED_ALLERGEN_ALIASES:
                        unsupported.append(UNSUPPORTED_ALLERGEN_ALIASES[item_clean])
                    elif item_clean in ("thuoc", "khang sinh", "penicillin"):
                        continue
                    elif item_clean:
                        unsupported.append(item_clean)

            # Check food & cooking exclusions ("không ăn đồ chiên", "kiêng thịt bò", "tránh hải sản")
            excl_match = re.search(r"\b(?:khong\s+an|kieng|tranh|khong\s+dung|khong\s+thich\s+an|khong)\s+(.+)", clause)
            if excl_match:
                target_str = excl_match.group(1).strip()
                matched_tokens = set()
                for token, mapping in sorted(FOOD_EXCLUSION_MAPPINGS.items(), key=lambda x: -len(x[0])):
                    if re.search(r"\b" + re.escape(token) + r"\b", target_str):
                        # Avoid duplicate sub-tokens (e.g. "bo" if "thit bo" already matched)
                        if not any(token in m for m in matched_tokens):
                            food_exclusions.append(mapping)
                            matched_tokens.add(token)

        return conditions, allergies, unsupported, food_exclusions, is_unmapped
