"""Unified Meal Recommendation Engine Service.

Đóng vai trò điều phối trung tâm (Central Orchestrator) cho toàn bộ
phân hệ Dinh dưỡng Lâm sàng & Khuyến nghị Bữa ăn Động (Phases 3 - 6):
1. Nhận yêu cầu từ API (query, điều kiện bệnh lý, dị ứng, exclude_ids).
2. Gọi ConstraintResolver (Phase 3) để giải quyết ràng buộc lâm sàng.
3. Kích hoạt rào chắn an toàn (Clinical Safeguard Refusal) nếu có dị ứng chưa hỗ trợ
   hoặc bệnh lý chưa có phác đồ đã kiểm duyệt.
4. Gọi ConstraintFilter (Phase 3) với In-Memory Inverted Index.
5. Gọi CandidateRanker (Phase 4) tính điểm Content-Based Deterministic Scoring.
6. Hỗ trợ xoay vòng / loại trừ (Refresh rotation) từ danh sách món đã xem.
7. Gọi DynamicMealComposer (Phase 5) tạo mâm cơm 4 món và chọn món độc lập.
8. Gọi FinalMealValidator (Phase 6) kiểm định 100% bất biến an toàn mâm cơm.
9. Đóng gói payload tương thích cả API mới (/api/nutrition/meals)
   và API hiện hữu (/api/nutrition/options).
10. KHÔNG SỬ DỤNG BẤT KỲ LLM HOẶC EXTERNAL API NÀO (llm_calls = 0).
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

from core.nutrition.candidate_ranker import CandidateRanker, RankedResults, RankingExplanation
from core.nutrition.clinical_constraints import CandidatePools, ResolvedConstraints, SafetyStatus
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.final_meal_validator import FinalMealValidator
from core.nutrition.meal_composition import (
    DynamicMealComposer,
    FamilyMealCombo,
    MealCompositionConfig,
    MealCompositionResult,
    StandaloneMeal,
)
from core.nutrition.metadata_index import InMemoryInvertedIndex, get_metadata_index
from core.recipe_catalog import imported_recipes

logger = logging.getLogger("medimind.nutrition_engine")

_CANONICAL_STAPLES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "recipes", "canonical_staples.json"
)

# Role display labels in Vietnamese & English
ROLE_LABELS_VI = {
    "staple": "Tinh bột chủ lực",
    "main_dish": "Món mặn / đạm chính",
    "soup": "Món canh",
    "vegetable": "Món rau thanh đạm",
    "standalone": "Món độc lập (Một tô / đĩa)",
}


class MealEngineService:
    """Singleton / Unified Service cho Dynamic Meal Recommendation Engine."""

    _instance: Optional["MealEngineService"] = None

    def __init__(self, index: Optional[InMemoryInvertedIndex] = None):
        self.index = index or get_metadata_index()
        self.resolver = ConstraintResolver()
        self.ranker = CandidateRanker(index=self.index)
        self.composer = DynamicMealComposer(index=self.index)
        self.validator = FinalMealValidator(index=self.index)
        self._catalog_recipes: Dict[str, Dict[str, Any]] = {}
        self._load_catalog_cache()

    @classmethod
    def get_instance(cls) -> "MealEngineService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_catalog_cache(self) -> None:
        """Cache recipes từ ViFoodRec và Canonical Staples để sinh chi tiết món."""
        # 1. ViFoodRec recipes
        try:
            for r in imported_recipes():
                self._catalog_recipes[r["id"]] = r
        except Exception as e:
            logger.warning(f"Không thể nạp imported_recipes: {e}")

        # 2. Canonical Staples
        if os.path.exists(_CANONICAL_STAPLES_PATH):
            try:
                with open(_CANONICAL_STAPLES_PATH, "r", encoding="utf-8") as f:
                    staples = json.load(f)
                    for s in staples:
                        self._catalog_recipes[s["id"]] = s
            except Exception as e:
                logger.warning(f"Không thể nạp canonical staples: {e}")

    def get_recipe_details(self, recipe_id: str) -> Dict[str, Any]:
        """Lấy chi tiết món ăn kèm hình ảnh, thời gian nấu và nguyên liệu."""
        raw = self._catalog_recipes.get(recipe_id) or {}
        meta = self.index.get_metadata_by_id(recipe_id) or {}

        title = raw.get("title") or meta.get("title") or recipe_id
        image_link = raw.get("image_link") or raw.get("source_image_url") or meta.get("image_link") or meta.get("source_image_url") or ""
        cooking_time = raw.get("cooking_time") or "20-30 phút"
        servings = raw.get("servings") or 1

        # Chuẩn hóa nguyên liệu
        ingredients = raw.get("ingredients")
        if not ingredients or not isinstance(ingredients, list):
            ingredients = [{"name": ing, "amount": "", "unit": ""} for ing in meta.get("normalized_ingredients", [])]

        return {
            "id": recipe_id,
            "title": title,
            "image_link": image_link,
            "cooking_time": cooking_time,
            "servings": servings,
            "ingredients": ingredients,
            "steps": raw.get("steps", []),
            "primary_cooking_method": meta.get("primary_cooking_method"),
            "cooking_methods": meta.get("cooking_methods", []),
            "calories": raw.get("calories"),
            "benefit": raw.get("benefit", ""),
            "avoid": raw.get("avoid", []),
        }

    def recommend_meals(
        self,
        condition: str,
        allergies: Optional[List[str]] = None,
        exclude_recipe_ids: Optional[List[str]] = None,
        rotation_offset: int = 0,
        profile: Optional[Dict[str, Any]] = None,
        config: Optional[MealCompositionConfig] = None,
    ) -> Dict[str, Any]:
        """Pipeline toàn trình đề xuất mâm cơm động và món ăn độc lập."""
        t_start = time.perf_counter()
        cfg = config or MealCompositionConfig()
        profile_dict = dict(profile or {})
        if allergies:
            profile_dict["allergies"] = list(allergies)

        # ---------------------------------------------------------------------
        # 1. Phase 3: Constraint Resolution
        # ---------------------------------------------------------------------
        resolved: ResolvedConstraints = self.resolver.resolve_constraints(
            condition_query=condition,
            profile=profile_dict
        )

        # Rào chắn an toàn lâm sàng: Dừng khẩn cấp nếu gặp vi phạm
        if not resolved.is_safe_to_proceed:
            raw_msg = resolved.safety_halt_reason or resolved.refusal_notice or ""
            if resolved.safety_status == SafetyStatus.UNSUPPORTED_ALLERGEN_HALT:
                refusal_msg = (
                    f"Yêu cầu của bạn chứa nhóm dị ứng ({', '.join(resolved.unsupported_allergens or ['chưa hỗ trợ'])}) "
                    "chưa có dữ liệu kiểm duyệt lâm sàng an toàn. Hệ thống tạm dừng tạo thực đơn tự động để tránh rủi ro sốc phản vệ."
                )
            elif resolved.safety_status == SafetyStatus.UNMAPPED_DISEASE_SAFEGUARD:
                refusal_msg = (
                    f"Tình trạng '{condition}' là bệnh lý cần chế độ dinh dưỡng lâm sàng chuyên biệt được bác sĩ chỉ định. "
                    "Hệ thống không tự ý đề xuất thực đơn khi chưa có phác đồ được phê duyệt."
                )
            else:
                refusal_msg = raw_msg or f"Hệ thống kích hoạt rào chắn an toàn lâm sàng cho yêu cầu '{condition}'."
            return {
                "status": "refusal",
                "safety_status": resolved.safety_status.value,
                "notice": refusal_msg,
                "selection_explanation": refusal_msg,
                "needs_clarification": True,
                "provider_status": "clinical_safeguard_refusal",
                "family_combos": [],
                "standalone_meals": [],
                "recipes": [],
                "full_meal_set": None,
                "meal_combos": [],
                "eligible_count": 0,
                "metadata": {
                    "engine": "deterministic",
                    "llm_calls": 0,
                    "latency_ms": round((time.perf_counter() - t_start) * 1000.0, 2),
                }
            }

        # ---------------------------------------------------------------------
        # 2. Phase 3: Clinical Filtering
        # ---------------------------------------------------------------------
        pools: CandidatePools = ConstraintFilter.filter_candidates(resolved, index=self.index)

        # ---------------------------------------------------------------------
        # 3. Phase 4: Candidate Ranking
        # ---------------------------------------------------------------------
        ranked: RankedResults = self.ranker.rank_candidates(pools, resolved)

        # ---------------------------------------------------------------------
        # 4. Refresh / Rotation Handling (Loại trừ món đã xem nếu còn pool)
        # ---------------------------------------------------------------------
        exclude_set = set(exclude_recipe_ids or [])
        adjusted_ranked = ranked
        if exclude_set:
            # Tạo bản sao xếp hạng đã lọc trừ các ID đã xem
            new_by_role: Dict[str, List[RankingExplanation]] = {}
            for role, cand_list in ranked.ranked_by_role.items():
                filtered_list = [c for c in cand_list if c.recipe_id not in exclude_set]
                # Nếu lọc xong còn ít hơn 2 ứng viên, giữ lại pool gốc để tránh crash
                new_by_role[role] = filtered_list if len(filtered_list) >= 2 else cand_list

            total_count = sum(len(v) for v in new_by_role.values())
            unique_ids = {c.recipe_id for v in new_by_role.values() for c in v}
            adjusted_ranked = RankedResults(
                ranked_by_role=new_by_role,
                total_ranked_count=total_count,
                unique_ranked_count=len(unique_ids),
                safety_status=ranked.safety_status,
                is_safe_to_proceed=ranked.is_safe_to_proceed,
                execution_metrics=ranked.execution_metrics,
                warnings=ranked.warnings,
            )

        # ---------------------------------------------------------------------
        # 5. Phase 5: Dynamic Meal Composition
        # ---------------------------------------------------------------------
        composed: MealCompositionResult = self.composer.compose_meals(
            adjusted_ranked,
            resolved=resolved,
            config_overrides={"max_family_combos": cfg.max_family_combos, "max_standalone_meals": cfg.max_standalone_meals}
        )

        # ---------------------------------------------------------------------
        # 6. Phase 6: Final Meal-Level Validation
        # ---------------------------------------------------------------------
        valid_combos, valid_standalones, val_reports = self.validator.filter_and_validate_results(
            composed.family_combos,
            composed.standalone_meals,
            resolved,
            pools
        )

        # ---------------------------------------------------------------------
        # 7. Payload Serialization & Enrichment
        # ---------------------------------------------------------------------
        serialized_combos = []
        for c in valid_combos:
            combo_dict = {
                "combo_id": c.combo_id,
                "meal_type": c.meal_type,
                "meal_score": c.meal_score,
                "score_breakdown": c.score_breakdown,
                "diversity_penalty": c.diversity_penalty,
                "reason_codes": c.reason_codes,
                "warnings": c.warnings,
                "signature": c.signature,
                "nutrition_disclaimer": c.nutrition_disclaimer,
                "components": {}
            }
            for role, comp in c.components.items():
                det = self.get_recipe_details(comp.recipe_id)
                combo_dict["components"][role] = {
                    "recipe_id": comp.recipe_id,
                    "title": det["title"],
                    "role": role,
                    "role_label": ROLE_LABELS_VI.get(role, role),
                    "score": comp.score,
                    "image_link": det["image_link"],
                    "cooking_time": det["cooking_time"],
                    "primary_cooking_method": comp.primary_cooking_method or det["primary_cooking_method"],
                    "ingredients": det["ingredients"],
                    "steps": det["steps"],
                    "calories": det["calories"],
                    "reason_codes": comp.reason_codes,
                    "warnings": comp.warnings,
                }
            serialized_combos.append(combo_dict)

        serialized_standalones = []
        for s in valid_standalones:
            det = self.get_recipe_details(s.recipe_id)
            serialized_standalones.append({
                "recipe_id": s.recipe_id,
                "title": det["title"],
                "meal_type": s.meal_type,
                "score": s.score,
                "score_breakdown": s.score_breakdown,
                "dish_category": s.dish_category,
                "image_link": det["image_link"],
                "cooking_time": det["cooking_time"],
                "primary_cooking_method": s.primary_cooking_method or det["primary_cooking_method"],
                "ingredients": det["ingredients"],
                "steps": det["steps"],
                "calories": det["calories"],
                "reason_codes": s.reason_codes,
                "warnings": s.warnings,
                "nutrition_disclaimer": s.nutrition_disclaimer,
            })

        # Xây dựng cấu trúc tương thích ngược cho giao diện nutrition-flow hiện hành
        legacy_full_meal_set = None
        legacy_meal_combos = []
        for i, c in enumerate(serialized_combos):
            staple = c["components"].get("staple", {})
            main = c["components"].get("main_dish", {})
            soup = c["components"].get("soup", {})
            veg = c["components"].get("vegetable", {})

            dishes = [
                {"role": "staple", "role_label": "Tinh bột chủ lực", "recipe": self._to_legacy_recipe(staple)},
                {"role": "main", "role_label": "Món mặn / đạm", "recipe": self._to_legacy_recipe(main)},
                {"role": "soup", "role_label": "Món canh", "recipe": self._to_legacy_recipe(soup)},
                {"role": "side", "role_label": "Món rau thanh đạm", "recipe": self._to_legacy_recipe(veg)},
            ]
            combo_obj = {
                "name": f"Mâm cơm #{i + 1}",
                "badge": f"Điểm: {int(c['meal_score'] * 100)}/100",
                "title": f"Mâm cơm gia đình #{i + 1}",
                "meal_time": "dinner",
                "meal_label": "Bữa cơm gia đình",
                "rationale": "Mâm cơm 4 món chuẩn vị: Tinh bột + Món đạm + Món canh + Món rau xanh tươi.",
                "staple_text": staple.get("title", "Cơm / Bánh phở"),
                "dishes": dishes,
            }
            legacy_meal_combos.append(combo_obj)
            if i == 0:
                legacy_full_meal_set = combo_obj

        # Danh sách món độc lập cho tab single_dishes
        legacy_recipes = [self._to_legacy_recipe(s) for s in serialized_standalones]

        t_end = time.perf_counter()
        elapsed_ms = round((t_end - t_start) * 1000.0, 2)

        return {
            "status": "success",
            "safety_status": "PASSED_KNOWN_CONSTRAINTS",
            "family_combos": serialized_combos,
            "standalone_meals": serialized_standalones,
            "eligible_count": len(pools.unique_candidate_ids),
            "recipes": legacy_recipes,
            "full_meal_set": legacy_full_meal_set,
            "meal_combos": legacy_meal_combos,
            "warnings": composed.warnings,
            "metadata": {
                "engine": "deterministic",
                "llm_calls": 0,
                "latency_ms": elapsed_ms,
                "total_combos_evaluated": composed.total_combos_evaluated,
                "valid_combos_generated": len(valid_combos),
                "standalone_meals_generated": len(valid_standalones),
            }
        }

    def _to_legacy_recipe(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Chuyển đổi sang format recipe mà nutrition-flow.js đang render."""
        rid = item.get("recipe_id") or item.get("id", "")
        title = item.get("title", "")
        image_link = item.get("image_link", "")
        cooking_time = item.get("cooking_time", "20 phút")
        calories = item.get("calories")

        # icon
        icon = "🍲"
        if "canh" in title.lower() or "súp" in title.lower():
            icon = "🥣"
        elif "cơm" in title.lower() or "xôi" in title.lower() or "bánh" in title.lower():
            icon = "🍚"
        elif "rau" in title.lower() or "gỏi" in title.lower() or "nấm" in title.lower():
            icon = "🥗"
        elif "cá" in title.lower():
            icon = "🐟"
        elif "gà" in title.lower():
            icon = "🍗"
        elif "bò" in title.lower():
            icon = "🥩"

        return {
            "id": rid,
            "title": title,
            "icon": icon,
            "image_link": image_link,
            "source_image_url": image_link,
            "subtitle": f"Cách nấu: {item.get('primary_cooking_method') or 'Truyền thống'}",
            "cooking_time": cooking_time,
            "benefit": "Cung cấp năng lượng và dưỡng chất cân bằng theo hồ sơ dinh dưỡng.",
            "ingredients": item.get("ingredients", []),
            "steps": item.get("steps", []),
            "calories": calories,
            "imported": True,
            "recommendation_reason": "Đạt chuẩn an toàn lâm sàng và phù hợp thể trạng.",
            "avoid": [],
        }
