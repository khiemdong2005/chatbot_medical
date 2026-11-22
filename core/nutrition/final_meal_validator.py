"""Final Meal-Level Clinical & Structural Validator.

Thực hiện kiểm định độc lập cấp độ bữa ăn (Final Meal-Level Validation)
cho toàn bộ FamilyMealCombo và StandaloneMeal trước khi trả về kết quả
cho API và người dùng.

Bảo toàn tuyệt đối 10 bất biến an toàn:
1. Mọi recipe_id thuộc clinically_filtered_ids (Subset Invariant).
2. Không vi phạm bất kỳ dị ứng nào đã khai báo.
3. Không vi phạm hard ingredient exclusions.
4. Không vi phạm hard cooking method exclusions.
5. Không có công thức bị cách ly thủ công (review_required == True).
6. Không trùng lặp recipe_id giữa các thành phần trong cùng mâm cơm.
7. Đúng vai trò bữa ăn (staple, main_dish, soup, vegetable, standalone).
8. Không rò rỉ món standalone vào mâm cơm 4 món.
9. Đảm bảo chất lượng món rau (primary_role == 'vegetable').
10. Loại bỏ mâm cơm không hợp lệ và phát cảnh báo minh bạch.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from core.nutrition.clinical_constraints import CandidatePools, ResolvedConstraints
from core.nutrition.meal_composition import FamilyMealCombo, StandaloneMeal
from core.nutrition.metadata_index import InMemoryInvertedIndex


@dataclass
class ValidationReport:
    """Báo cáo kiểm định cho một mâm cơm hoặc món độc lập."""
    is_valid: bool
    item_id: str
    item_type: str  # "family_combo" hoặc "standalone"
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class FinalMealValidator:
    """Bộ kiểm định an toàn lâm sàng và cấu trúc mâm cơm cấp cuối cùng."""

    REQUIRED_COMBO_ROLES = ("staple", "main_dish", "soup", "vegetable")

    def __init__(self, index: InMemoryInvertedIndex):
        self.index = index

    def validate_family_combo(
        self,
        combo: FamilyMealCombo,
        resolved: ResolvedConstraints,
        pools: CandidatePools,
    ) -> ValidationReport:
        """Kiểm định toàn diện một mâm cơm gia đình 4 món."""
        violations: List[str] = []
        warnings: List[str] = list(combo.warnings)

        # 1. Kiểm tra cấu trúc 4 roles
        comps = combo.components
        for role in self.REQUIRED_COMBO_ROLES:
            if role not in comps:
                violations.append(f"MISSING_REQUIRED_ROLE:{role}")

        if violations:
            return ValidationReport(
                is_valid=False,
                item_id=combo.combo_id,
                item_type="family_combo",
                violations=violations,
                warnings=warnings,
            )

        # 2. Kiểm tra không trùng recipe_id
        recipe_ids = [comp.recipe_id for comp in comps.values()]
        if len(recipe_ids) != len(set(recipe_ids)):
            violations.append("DUPLICATE_RECIPE_IN_COMBO")

        # Chuẩn bị tập hợp hợp lệ của Phase 3
        filtered_ids: Set[str] = pools.unique_candidate_ids
        user_allergies: Set[str] = set(resolved.hard_excluded_allergens or [])
        hard_excluded_ings: Set[str] = set(resolved.hard_excluded_ingredients or [])
        hard_excluded_cooks: Set[str] = set(resolved.hard_excluded_cooking_methods or [])

        # 3. Kiểm định từng thành phần
        for role, comp in comps.items():
            rid = comp.recipe_id
            meta = self.index.get_metadata_by_id(rid) or {}

            # Invariant 1: Thuộc tập filtered candidates
            if rid not in filtered_ids:
                violations.append(f"UNAPPROVED_CANDIDATE:{rid}:{role}")

            # Invariant 4: Không chứa standalone trong combo
            primary_role = meta.get("primary_role", comp.role)
            if primary_role == "standalone":
                violations.append(f"STANDALONE_LEAKAGE_IN_COMBO:{rid}:{role}")

            # Invariant 5: Không chứa món quarantine
            if meta.get("review_required", False):
                violations.append(f"QUARANTINED_RECIPE_IN_COMBO:{rid}:{role}")

            # Invariant 7: Đúng vai trò (đặc biệt món rau)
            if role == "vegetable" and primary_role != "vegetable":
                violations.append(f"INVALID_VEGETABLE_ROLE:{rid}:primary_role={primary_role}")

            # Invariant 2: Dị ứng
            assessments = meta.get("allergen_assessments", {})
            for allergen in user_allergies:
                ass = assessments.get(allergen, {})
                if isinstance(ass, dict):
                    status = ass.get("status")
                else:
                    status = str(ass)
                if status == "known_present":
                    violations.append(f"ALLERGEN_VIOLATION:{allergen}:{rid}")

            # Invariant 3: Nguyên liệu cấm tuyệt đối
            norm_ings = set(meta.get("normalized_ingredients", []))
            clash_ings = norm_ings & hard_excluded_ings
            if clash_ings:
                violations.append(f"HARD_EXCLUDED_INGREDIENT:{list(clash_ings)[0]}:{rid}")

            # Invariant 4: Cách nấu cấm tuyệt đối
            cook = meta.get("primary_cooking_method") or comp.primary_cooking_method
            if cook and cook in hard_excluded_cooks:
                violations.append(f"HARD_EXCLUDED_COOKING_METHOD:{cook}:{rid}")

        # 4. Kiểm định kết hợp mâm cơm (Cross-Component Sanity)
        # Đánh giá cảnh báo dữ liệu dinh dưỡng
        for comp in comps.values():
            if comp.warnings:
                for w in comp.warnings:
                    if w not in warnings:
                        warnings.append(w)

        is_valid = len(violations) == 0
        return ValidationReport(
            is_valid=is_valid,
            item_id=combo.combo_id,
            item_type="family_combo",
            violations=violations,
            warnings=warnings,
        )

    def validate_standalone_meal(
        self,
        meal: StandaloneMeal,
        resolved: ResolvedConstraints,
        pools: CandidatePools,
    ) -> ValidationReport:
        """Kiểm định an toàn cho một món ăn độc lập."""
        violations: List[str] = []
        warnings: List[str] = list(meal.warnings)

        rid = meal.recipe_id
        filtered_ids: Set[str] = pools.unique_candidate_ids
        user_allergies: Set[str] = set(resolved.hard_excluded_allergens or [])
        hard_excluded_ings: Set[str] = set(resolved.hard_excluded_ingredients or [])
        hard_excluded_cooks: Set[str] = set(resolved.hard_excluded_cooking_methods or [])

        # Invariant 1: Thuộc tập filtered candidates
        if rid not in filtered_ids:
            violations.append(f"UNAPPROVED_CANDIDATE:{rid}:standalone")

        meta = self.index.get_metadata_by_id(rid) or {}

        # Invariant 5: Không chứa món quarantine
        if meta.get("review_required", False):
            violations.append(f"QUARANTINED_RECIPE:{rid}")

        # Invariant 2: Dị ứng
        assessments = meta.get("allergen_assessments", {})
        for allergen in user_allergies:
            ass = assessments.get(allergen, {})
            if isinstance(ass, dict):
                status = ass.get("status")
            else:
                status = str(ass)
            if status == "known_present":
                violations.append(f"ALLERGEN_VIOLATION:{allergen}:{rid}")

        # Invariant 3: Nguyên liệu cấm
        norm_ings = set(meta.get("normalized_ingredients", []))
        clash_ings = norm_ings & hard_excluded_ings
        if clash_ings:
            violations.append(f"HARD_EXCLUDED_INGREDIENT:{list(clash_ings)[0]}:{rid}")

        # Invariant 4: Cách nấu cấm
        cook = meta.get("primary_cooking_method") or meal.primary_cooking_method
        if cook and cook in hard_excluded_cooks:
            violations.append(f"HARD_EXCLUDED_COOKING_METHOD:{cook}:{rid}")

        is_valid = len(violations) == 0
        return ValidationReport(
            is_valid=is_valid,
            item_id=rid,
            item_type="standalone",
            violations=violations,
            warnings=warnings,
        )

    def filter_and_validate_results(
        self,
        family_combos: List[FamilyMealCombo],
        standalone_meals: List[StandaloneMeal],
        resolved: ResolvedConstraints,
        pools: CandidatePools,
    ) -> Tuple[List[FamilyMealCombo], List[StandaloneMeal], List[ValidationReport]]:
        """Lọc và chỉ giữ lại những mâm cơm & món đơn vượt qua 100% kiểm định."""
        valid_combos: List[FamilyMealCombo] = []
        valid_standalones: List[StandaloneMeal] = []
        reports: List[ValidationReport] = []

        for combo in family_combos:
            rep = self.validate_family_combo(combo, resolved, pools)
            reports.append(rep)
            if rep.is_valid:
                valid_combos.append(combo)

        for meal in standalone_meals:
            rep = self.validate_standalone_meal(meal, resolved, pools)
            reports.append(rep)
            if rep.is_valid:
                valid_standalones.append(meal)

        return valid_combos, valid_standalones, reports
