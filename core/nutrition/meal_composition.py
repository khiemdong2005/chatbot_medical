"""Phase 5: Dynamic Meal Composition Engine.

Constraint-Aware Hybrid Meal Recommendation Engine.
Composes 4-component family meal combos (staple + main_dish + soup + vegetable)
and diverse standalone meals from Phase 4 ranked candidate pools.

Core Design Invariants:
1. Dynamic Assembly:
   - Meals are assembled dynamically based on user profile and clinical context.
   - Zero hardcoded meal menus, zero fixed combos, zero LLM dependencies.
2. Hard Safety Preservation:
   - selected_recipe_ids ⊆ clinically_filtered_ids
   - If Phase 3 Clinical Constraint Engine halts (unsupported allergen / refusal),
     Phase 5 halts immediately and returns 0 meals.
3. Family Meal Composition Invariants:
   - Exactly 4 components: staple, main_dish, soup, vegetable.
   - Zero duplicate recipe IDs within the same combo.
   - Zero standalone dishes inside combos.
   - Zero manual-review / quarantined dishes in combos.
   - Vegetable slot requires an authentic vegetable dish (primary_role == 'vegetable').
4. Bounded Search & Determinism:
   - Bounded exhaustive search over Top-K: staple (5) x main (15) x soup (10) x veg (10) <= 7,500.
   - High-throughput two-stage evaluation: P95 latency < 15 ms.
   - Deterministic iteration and stable tie-breaking by combo signature.
5. Multi-Objective Meal-Level Scoring:
   - Component relevance (normalized Phase 4 score).
   - Ingredient diversity (penalizes repeated primary proteins or identical ingredients).
   - Cooking diversity (penalizes monotonous cooking methods like all-fried).
   - Clinical soft compatibility (aggregates soft preferences).
6. Cross-Combo Diversity:
   - Diversity-aware selection (main dish rotation, penalty for >= 3/4 component overlap).
7. Standalone Diversity:
   - Selects up to 6 standalone meals across dish categories (phở, bún, cháo, cơm đĩa, hủ tiếu, mì).
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from core.nutrition.candidate_ranker import (
    CandidateRanker,
    RankedResults,
    RankingExplanation,
    ScoringConfig,
)
from core.nutrition.clinical_constraints import (
    CandidatePools,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.metadata_index import (
    get_metadata_index,
    InMemoryInvertedIndex,
    STANDARD_COMBO_ROLES,
)

logger = logging.getLogger(__name__)

# Common aromatics and seasoning ingredients to ignore during cross-component duplicate checks
PANTRY_COMMON_INGREDIENTS: FrozenSet[str] = frozenset([
    "water", "salt", "sugar", "black_pepper", "onion", "garlic",
    "chili", "ginger", "lemongrass", "fish_sauce", "soy_sauce",
    "cooking_oil", "butter", "scallion", "shallot"
])

# Protein groups where repetition across dishes is nutritionally redundant
PROTEIN_GROUPS: FrozenSet[str] = frozenset([
    "meat", "poultry", "seafood", "fish", "egg"
])


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

@dataclass
class MealComponent:
    """Individual dish component in a 4-piece family meal combo."""
    recipe_id: str
    title: str
    role: str
    score: float
    primary_cooking_method: Optional[str] = None
    cooking_methods: List[str] = field(default_factory=list)
    normalized_ingredients: List[str] = field(default_factory=list)
    ingredient_groups: List[str] = field(default_factory=list)
    nutrition_quality: str = "estimated"
    reason_codes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class FamilyMealCombo:
    """Four-component balanced family meal combo (staple + main_dish + soup + vegetable)."""
    combo_id: str
    meal_type: str = "family_combo"
    components: Dict[str, MealComponent] = field(default_factory=dict)
    meal_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    diversity_penalty: float = 0.0
    reason_codes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    signature: str = ""
    nutrition_disclaimer: str = (
        "Thông tin dinh dưỡng mang tính ước tính và tham khảo; hệ thống không đưa ra chẩn đoán hay cam kết điều trị y khoa."
    )


@dataclass
class StandaloneMeal:
    """Standalone complete one-dish meal (e.g. Phở, Bún, Cháo, Hủ tiếu, Cơm đĩa)."""
    recipe_id: str
    title: str
    meal_type: str = "standalone"
    score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    dish_category: str = "other"  # pho, bun, chao, hu_tieu, com_dia, mien_my, other
    primary_cooking_method: Optional[str] = None
    cooking_methods: List[str] = field(default_factory=list)
    normalized_ingredients: List[str] = field(default_factory=list)
    ingredient_groups: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    nutrition_disclaimer: str = (
        "Món ăn độc lập một đĩa/tô; thành phần dinh dưỡng ước tính theo công thức nguồn."
    )


@dataclass
class MealCompositionConfig:
    """Configurable weights, bounds, and thresholds for Phase 5."""
    max_family_combos: int = 6
    max_standalone_meals: int = 6

    # Bounded Top-K candidate slices per role (Max theoretical: 5 * 15 * 10 * 10 = 7,500)
    top_k_staple: int = 5
    top_k_main: int = 15
    top_k_soup: int = 10
    top_k_vegetable: int = 10

    # Composite meal-level score weights (sum to 1.0)
    weight_component_relevance: float = 0.40
    weight_ingredient_diversity: float = 0.30
    weight_cooking_diversity: float = 0.20
    weight_clinical_compatibility: float = 0.10

    # Component relevance sub-weights across 4 roles (sum to 1.0)
    role_weight_main: float = 0.35
    role_weight_vegetable: float = 0.25
    role_weight_soup: float = 0.20
    role_weight_staple: float = 0.20

    # Intra-combo penalties
    penalty_duplicate_primary_ingredient: float = 0.15
    penalty_duplicate_protein_group: float = 0.10
    penalty_monotonous_cooking: float = 0.15

    # Inter-combo diversity penalties (across returned combos)
    penalty_same_main_dish: float = 0.30
    penalty_three_identical_components: float = 0.35
    penalty_same_protein_group_main: float = 0.05
    penalty_same_soup: float = 0.08
    penalty_same_staple: float = 0.05


@dataclass
class MealCompositionResult:
    """Comprehensive output of Phase 5 Meal Composition Engine."""
    family_combos: List[FamilyMealCombo] = field(default_factory=list)
    standalone_meals: List[StandaloneMeal] = field(default_factory=list)
    safety_status: str = "PASSED_KNOWN_CONSTRAINTS"
    is_safe_to_proceed: bool = True
    halt_reason: Optional[str] = None
    missing_roles: List[str] = field(default_factory=list)
    total_combos_evaluated: int = 0
    valid_combos_generated: int = 0
    warnings: List[str] = field(default_factory=list)
    execution_metrics: Dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Standalone Dish Categorization
# -----------------------------------------------------------------------------

def classify_standalone_dish_category(title: str) -> str:
    """Classify standalone dishes into categories for diversity-aware selection."""
    t_low = title.lower()
    if "phở" in t_low:
        return "pho"
    elif "bún" in t_low:
        return "bun"
    elif "cháo" in t_low:
        return "chao"
    elif "hủ tiếu" in t_low or "hủ tíu" in t_low:
        return "hu_tieu"
    elif "cơm" in t_low:
        return "com_dia"
    elif any(k in t_low for k in ["miến", "mì", "mỳ", "nui"]):
        return "mien_my"
    elif any(k in t_low for k in ["bánh canh", "hoành thánh", "sủi cảo"]):
        return "noodle_soup"
    return "other"


# Internal lightweight candidate feature container for high-throughput search
@dataclass
class _CandidateFastFeat:
    recipe_id: str
    item: RankingExplanation
    meta: Dict[str, Any]
    score: float
    clin_score: float
    ings_set: FrozenSet[str]
    protein_set: FrozenSet[str]
    primary_cook: Optional[str]
    is_valid_role: bool


# -----------------------------------------------------------------------------
# Dynamic Meal Composer Engine
# -----------------------------------------------------------------------------

class DynamicMealComposer:
    """Assembles 4-component family combos and standalone meals from ranked pools."""

    def __init__(
        self,
        index: Optional[InMemoryInvertedIndex] = None,
        config: Optional[MealCompositionConfig] = None,
    ):
        self.index = index or get_metadata_index()
        self.config = config or MealCompositionConfig()

    def compose_meals(
        self,
        ranked_results: RankedResults,
        resolved: Optional[ResolvedConstraints] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
    ) -> MealCompositionResult:
        """Compose family combos and standalone meals following deterministic rules."""
        t_start = time.perf_counter()
        cfg = self.config
        if config_overrides:
            cfg = MealCompositionConfig(**{**cfg.__dict__, **config_overrides})

        result = MealCompositionResult()

        # ---------------------------------------------------------------------
        # 1. Safety Halt Guard: If Clinical Engine halted, stop immediately
        # ---------------------------------------------------------------------
        if resolved and not resolved.is_safe_to_proceed:
            result.is_safe_to_proceed = False
            result.safety_status = resolved.safety_status.value if hasattr(resolved.safety_status, "value") else str(resolved.safety_status)
            result.halt_reason = resolved.refusal_notice or resolved.safety_halt_reason or "Safety halt triggered by Clinical Engine"
            result.warnings.append(result.halt_reason)
            result.execution_metrics = {"duration_ms": round((time.perf_counter() - t_start) * 1000.0, 3)}
            return result

        if not ranked_results.is_safe_to_proceed:
            result.is_safe_to_proceed = False
            result.safety_status = ranked_results.safety_status
            result.halt_reason = "Safety halt triggered by Ranked Results"
            result.warnings.append(result.halt_reason)
            result.execution_metrics = {"duration_ms": round((time.perf_counter() - t_start) * 1000.0, 3)}
            return result

        result.safety_status = ranked_results.safety_status

        # ---------------------------------------------------------------------
        # 2. Extract Slices for Combo Roles
        # ---------------------------------------------------------------------
        staple_items = ranked_results.ranked_by_role.get("staple", [])[:cfg.top_k_staple]
        main_items = ranked_results.ranked_by_role.get("main_dish", [])[:cfg.top_k_main]
        soup_items = ranked_results.ranked_by_role.get("soup", [])[:cfg.top_k_soup]
        veg_items = ranked_results.ranked_by_role.get("vegetable", [])[:cfg.top_k_vegetable]

        missing = []
        if not staple_items:
            missing.append("staple")
        if not main_items:
            missing.append("main_dish")
        if not soup_items:
            missing.append("soup")
        if not veg_items:
            missing.append("vegetable")
        result.missing_roles = missing

        # ---------------------------------------------------------------------
        # 3. Two-Stage Ultra-Low Latency Combo Search
        # ---------------------------------------------------------------------
        t_combos_start = time.perf_counter()
        raw_combo_count = 0
        scored_combos: List[Tuple[float, str, _CandidateFastFeat, _CandidateFastFeat, _CandidateFastFeat, _CandidateFastFeat, float, float, float, float, List[str]]] = []

        if not missing:
            raw_combo_count = len(staple_items) * len(main_items) * len(soup_items) * len(veg_items)

            # Pre-extract fast feature structs for candidate slices
            s_feats = [self._extract_fast_feat(it, "staple") for it in staple_items]
            m_feats = [self._extract_fast_feat(it, "main_dish") for it in main_items]
            p_feats = [self._extract_fast_feat(it, "soup") for it in soup_items]
            v_feats = [self._extract_fast_feat(it, "vegetable") for it in veg_items]

            # Filter out invalid role members upfront
            s_feats = [f for f in s_feats if f.is_valid_role]
            m_feats = [f for f in m_feats if f.is_valid_role]
            p_feats = [f for f in p_feats if f.is_valid_role]
            v_feats = [f for f in v_feats if f.is_valid_role]

            user_loves_fried = bool(resolved and ("deep_frying" in resolved.user_preferred_cooking_methods))

            w_comp = cfg.weight_component_relevance
            w_ing = cfg.weight_ingredient_diversity
            w_cook = cfg.weight_cooking_diversity
            w_clin = cfg.weight_clinical_compatibility

            rm = cfg.role_weight_main
            rv = cfg.role_weight_vegetable
            rp = cfg.role_weight_soup
            rs = cfg.role_weight_staple

            pen_dup_ing = cfg.penalty_duplicate_primary_ingredient
            pen_dup_prot = cfg.penalty_duplicate_protein_group
            pen_mon_cook = cfg.penalty_monotonous_cooking

            # High-speed Cartesian loop over pre-computed tuples
            for s in s_feats:
                s_id = s.recipe_id
                s_sc = s.score
                s_clin = s.clin_score

                for m in m_feats:
                    m_id = m.recipe_id
                    if m_id == s_id:
                        continue  # Invariant: No duplicate IDs

                    m_sc = m.score
                    m_clin = m.clin_score
                    m_ings = m.ings_set
                    m_prot = m.protein_set
                    m_cook = m.primary_cook

                    for p in p_feats:
                        p_id = p.recipe_id
                        if p_id == s_id or p_id == m_id:
                            continue  # Invariant: No duplicate IDs

                        p_sc = p.score
                        p_clin = p.clin_score
                        p_ings = p.ings_set
                        p_prot = p.protein_set

                        # Precompute main-soup penalties
                        pen_ing_mp = 0.0
                        overlap_reasons_base = []
                        if m_ings and p_ings and (m_ings & p_ings):
                            pen_ing_mp += pen_dup_ing
                            overlap_reasons_base.append(f"overlap_ing:main_soup:{sorted(list(m_ings & p_ings))[0]}")
                        if m_prot and p_prot and (m_prot & p_prot):
                            pen_ing_mp += pen_dup_prot
                            overlap_reasons_base.append(f"duplicate_protein_group:{sorted(list(m_prot & p_prot))[0]}")

                        for v in v_feats:
                            v_id = v.recipe_id
                            if v_id == s_id or v_id == m_id or v_id == p_id:
                                continue  # Invariant: No duplicate IDs

                            v_sc = v.score
                            v_clin = v.clin_score
                            v_ings = v.ings_set
                            v_cook = v.primary_cook

                            # 1. Component Relevance
                            comp_rel = rm * m_sc + rv * v_sc + rp * p_sc + rs * s_sc

                            # 2. Ingredient Diversity
                            pen_ing = pen_ing_mp
                            overlap_reasons = list(overlap_reasons_base)
                            if m_ings and v_ings and (m_ings & v_ings):
                                pen_ing += pen_dup_ing
                                overlap_reasons.append(f"overlap_ing:main_veg:{sorted(list(m_ings & v_ings))[0]}")
                            if p_ings and v_ings and (p_ings & v_ings):
                                pen_ing += (pen_dup_ing * 0.5)
                            ing_div = max(0.0, 1.0 - pen_ing)

                            # 3. Cooking Diversity
                            cook_div = 1.0
                            if not user_loves_fried:
                                if m_cook == "deep_frying" and v_cook == "deep_frying":
                                    cook_div -= pen_mon_cook
                                elif m_cook == "stir_frying" and v_cook == "stir_frying":
                                    cook_div -= (pen_mon_cook * 0.35)

                            # 4. Clinical Soft Compatibility
                            clin_comp = (m_clin + v_clin + p_clin + s_clin) * 0.25

                            # 5. Composite Score
                            total_score = (
                                w_comp * comp_rel +
                                w_ing * ing_div +
                                w_cook * cook_div +
                                w_clin * clin_comp
                            )
                            total_score = round(max(0.0, min(1.0, total_score)), 4)

                            sig = f"{s_id}:{m_id}:{p_id}:{v_id}"
                            scored_combos.append((
                                total_score, sig, s, m, p, v,
                                comp_rel, ing_div, cook_div, clin_comp, overlap_reasons
                            ))

        result.total_combos_evaluated = raw_combo_count
        result.valid_combos_generated = len(scored_combos)
        t_combos_end = time.perf_counter()

        # ---------------------------------------------------------------------
        # 4. Across-Combo Diversity-Aware Selection (Greedy Top-6)
        # ---------------------------------------------------------------------
        t_div_start = time.perf_counter()
        if scored_combos:
            selected_combos = self._select_diverse_combos_fast(scored_combos, max_combos=cfg.max_family_combos, cfg=cfg)
            result.family_combos = selected_combos
        else:
            result.family_combos = []
            if missing:
                result.warnings.append(f"Không thể tạo mâm cơm 4 món do thiếu ứng viên đạt chuẩn cho các vai trò: {', '.join(missing)}")
        t_div_end = time.perf_counter()

        # ---------------------------------------------------------------------
        # 5. Standalone Meal Selection (Diverse Top-6)
        # ---------------------------------------------------------------------
        t_sta_start = time.perf_counter()
        standalone_ranked = ranked_results.ranked_by_role.get("standalone", [])
        if standalone_ranked:
            selected_standalone = self._select_diverse_standalone(standalone_ranked, max_standalone=cfg.max_standalone_meals)
            result.standalone_meals = selected_standalone
        else:
            result.standalone_meals = []
        t_sta_end = time.perf_counter()

        # ---------------------------------------------------------------------
        # 6. Aggregate Execution Metrics
        # ---------------------------------------------------------------------
        t_total_end = time.perf_counter()
        result.execution_metrics = {
            "raw_combos_evaluated": raw_combo_count,
            "valid_combos_generated": len(scored_combos),
            "family_combos_returned": len(result.family_combos),
            "standalone_meals_returned": len(result.standalone_meals),
            "combo_search_and_score_ms": round((t_combos_end - t_combos_start) * 1000.0, 3),
            "diversity_selection_ms": round((t_div_end - t_div_start) * 1000.0, 3),
            "standalone_selection_ms": round((t_sta_end - t_sta_start) * 1000.0, 3),
            "total_phase5_latency_ms": round((t_total_end - t_start) * 1000.0, 3),
        }

        return result

    # -------------------------------------------------------------------------
    # Helper: Pre-Extract Fast Features
    # -------------------------------------------------------------------------
    def _extract_fast_feat(self, item: RankingExplanation, expected_role: str) -> _CandidateFastFeat:
        """Precompute candidate features for high-throughput inner Cartesian loops."""
        meta = self.index.get_metadata_by_id(item.recipe_id) or {}
        p_role = meta.get("primary_role", item.primary_role)

        # Invariant checks
        is_valid = True
        if p_role == "standalone":
            is_valid = False
        if meta.get("review_required") or item.recipe_id in self.index.manual_review_ids:
            is_valid = False
        if expected_role == "vegetable" and p_role != "vegetable":
            is_valid = False

        ings = frozenset(set(meta.get("normalized_ingredients", [])) - PANTRY_COMMON_INGREDIENTS)
        prots = frozenset(set(meta.get("ingredient_groups", [])) & PROTEIN_GROUPS)
        pri_cook = meta.get("primary_cooking_method")
        clin_score = item.score_breakdown.get("clinical_preferences", 0.50)

        return _CandidateFastFeat(
            recipe_id=item.recipe_id,
            item=item,
            meta=meta,
            score=item.total_score,
            clin_score=clin_score,
            ings_set=ings,
            protein_set=prots,
            primary_cook=pri_cook,
            is_valid_role=is_valid,
        )

    # -------------------------------------------------------------------------
    # Helper: Fast Across-Combo Diversity Selection
    # -------------------------------------------------------------------------
    def _select_diverse_combos_fast(
        self,
        scored_combos: List[Tuple[float, str, _CandidateFastFeat, _CandidateFastFeat, _CandidateFastFeat, _CandidateFastFeat, float, float, float, float, List[str]]],
        max_combos: int,
        cfg: MealCompositionConfig,
    ) -> List[FamilyMealCombo]:
        """Greedy diversity-aware selection: maximizes score while rotating main dishes and recipes."""
        if not scored_combos:
            return []

        # Deterministic sorting: meal_score DESC, signature ASC
        sorted_candidates = sorted(scored_combos, key=lambda c: (-c[0], c[1]))

        # Ensure representation across all available main dishes:
        # Group combos by main dish and keep top 10 combos per main dish
        from collections import defaultdict
        by_main: Dict[str, List[Any]] = defaultdict(list)
        for cand in sorted_candidates:
            m_id = cand[3].recipe_id
            if len(by_main[m_id]) < 10:
                by_main[m_id].append(cand)
            if len(by_main) >= 15 and all(len(v) >= 10 for v in by_main.values()):
                break

        candidate_pool: List[Any] = []
        for cand_list in by_main.values():
            candidate_pool.extend(cand_list)
        candidate_pool.sort(key=lambda c: (-c[0], c[1]))

        selected_tuples = [candidate_pool[0]]
        remaining = candidate_pool[1:]

        pen_same_main = cfg.penalty_same_main_dish
        pen_three_ident = cfg.penalty_three_identical_components
        pen_prot = cfg.penalty_same_protein_group_main
        pen_same_soup = cfg.penalty_same_soup
        pen_same_staple = cfg.penalty_same_staple

        while len(selected_tuples) < max_combos and remaining:
            best_idx = -1
            best_adj_score = -999.0
            best_penalty = 0.0

            for idx, cand in enumerate(remaining):
                c_score, c_sig, c_s, c_m, c_p, c_v = cand[0], cand[1], cand[2], cand[3], cand[4], cand[5]
                cand_m_id = c_m.recipe_id
                cand_s_id = c_s.recipe_id
                cand_p_id = c_p.recipe_id
                cand_m_prots = c_m.protein_set
                cand_set = {cand_s_id, cand_m_id, cand_p_id, c_v.recipe_id}

                max_pen = 0.0
                for sel in selected_tuples:
                    pen = 0.0
                    sel_s_id = sel[2].recipe_id
                    sel_m_id = sel[3].recipe_id
                    sel_p_id = sel[4].recipe_id
                    sel_set = {sel_s_id, sel_m_id, sel_p_id, sel[5].recipe_id}

                    # Penalty 1: Same main dish
                    if cand_m_id == sel_m_id:
                        pen += pen_same_main

                    # Penalty 2: >= 3 components identical
                    if len(cand_set & sel_set) >= 3:
                        pen += pen_three_ident

                    # Penalty 3: Same protein group in main dish
                    sel_m_prots = sel[3].protein_set
                    if cand_m_prots and sel_m_prots and (cand_m_prots & sel_m_prots):
                        pen += pen_prot

                    # Penalty 4: Same soup
                    if cand_p_id == sel_p_id:
                        pen += pen_same_soup

                    # Penalty 5: Same staple
                    if cand_s_id == sel_s_id:
                        pen += pen_same_staple

                    if pen > max_pen:
                        max_pen = pen

                adj_score = c_score - max_pen

                if adj_score > best_adj_score:
                    best_adj_score = adj_score
                    best_idx = idx
                    best_penalty = max_pen
                elif adj_score == best_adj_score:
                    if c_score > remaining[best_idx][0]:
                        best_adj_score = adj_score
                        best_idx = idx
                        best_penalty = max_pen
                    elif c_score == remaining[best_idx][0] and c_sig < remaining[best_idx][1]:
                        best_adj_score = adj_score
                        best_idx = idx
                        best_penalty = max_pen

            if best_idx >= 0:
                chosen = remaining.pop(best_idx)
                selected_tuples.append(chosen)
            else:
                break

        # Construct rich FamilyMealCombo objects ONLY for the selected combos
        final_combos: List[FamilyMealCombo] = []
        for rank_pos, tup in enumerate(selected_tuples, 1):
            tot_sc, sig, s_f, m_f, p_f, v_f, comp_rel, ing_div, cook_div, clin_comp, ov_reasons = tup

            # Calculate penalty relative to previously selected combos in the final list
            cur_penalty = 0.0
            if rank_pos > 1:
                for prev in final_combos:
                    pen = 0.0
                    if m_f.recipe_id == prev.components["main_dish"].recipe_id:
                        pen += pen_same_main
                    cur_set = {s_f.recipe_id, m_f.recipe_id, p_f.recipe_id, v_f.recipe_id}
                    prev_set = {c.recipe_id for c in prev.components.values()}
                    if len(cur_set & prev_set) >= 3:
                        pen += pen_three_ident
                    if m_f.protein_set and (m_f.protein_set & set(prev.components["main_dish"].ingredient_groups)):
                        pen += pen_prot
                    if pen > cur_penalty:
                        cur_penalty = pen

            reason_codes = ["FOUR_COMPONENT_BALANCED_MEAL"]
            if ing_div >= 0.85:
                reason_codes.append("DIVERSE_PROTEIN_AND_VEG")
            if cook_div >= 0.90:
                reason_codes.append("BALANCED_COOKING_METHODS")
            if clin_comp >= 0.65:
                reason_codes.append("CLINICALLY_FAVORED_COMBO")
            for r_code in ov_reasons:
                reason_codes.append(f"INGREDIENT_OVERLAP_PENALTY:{r_code}")
            if cur_penalty > 0:
                reason_codes.append(f"DIVERSITY_ADJUSTED_SCORE:{round(tot_sc - cur_penalty, 4)}")

            warnings = []
            if any(
                meta.get("nutrition_verified") is False
                for meta in (s_f.meta, m_f.meta, p_f.meta, v_f.meta)
            ):
                warnings.append("NUTRITION_DATA_ESTIMATED: Một số món sử dụng số liệu dinh dưỡng ước tính")

            components = {
                "staple": MealComponent(
                    recipe_id=s_f.recipe_id,
                    title=s_f.item.title,
                    role="staple",
                    score=s_f.score,
                    primary_cooking_method=s_f.primary_cook,
                    cooking_methods=s_f.meta.get("cooking_methods", []),
                    normalized_ingredients=s_f.meta.get("normalized_ingredients", []),
                    ingredient_groups=s_f.meta.get("ingredient_groups", []),
                    nutrition_quality=s_f.item.nutrition_quality,
                    reason_codes=s_f.item.reason_codes,
                ),
                "main_dish": MealComponent(
                    recipe_id=m_f.recipe_id,
                    title=m_f.item.title,
                    role="main_dish",
                    score=m_f.score,
                    primary_cooking_method=m_f.primary_cook,
                    cooking_methods=m_f.meta.get("cooking_methods", []),
                    normalized_ingredients=m_f.meta.get("normalized_ingredients", []),
                    ingredient_groups=m_f.meta.get("ingredient_groups", []),
                    nutrition_quality=m_f.item.nutrition_quality,
                    reason_codes=m_f.item.reason_codes,
                ),
                "soup": MealComponent(
                    recipe_id=p_f.recipe_id,
                    title=p_f.item.title,
                    role="soup",
                    score=p_f.score,
                    primary_cooking_method=p_f.primary_cook,
                    cooking_methods=p_f.meta.get("cooking_methods", []),
                    normalized_ingredients=p_f.meta.get("normalized_ingredients", []),
                    ingredient_groups=p_f.meta.get("ingredient_groups", []),
                    nutrition_quality=p_f.item.nutrition_quality,
                    reason_codes=p_f.item.reason_codes,
                ),
                "vegetable": MealComponent(
                    recipe_id=v_f.recipe_id,
                    title=v_f.item.title,
                    role="vegetable",
                    score=v_f.score,
                    primary_cooking_method=v_f.primary_cook,
                    cooking_methods=v_f.meta.get("cooking_methods", []),
                    normalized_ingredients=v_f.meta.get("normalized_ingredients", []),
                    ingredient_groups=v_f.meta.get("ingredient_groups", []),
                    nutrition_quality=v_f.item.nutrition_quality,
                    reason_codes=v_f.item.reason_codes,
                ),
            }

            final_combos.append(FamilyMealCombo(
                combo_id=f"combo_{sig}",
                components=components,
                meal_score=tot_sc,
                score_breakdown={
                    "component_relevance": round(comp_rel, 4),
                    "ingredient_diversity": round(ing_div, 4),
                    "cooking_diversity": round(cook_div, 4),
                    "clinical_compatibility": round(clin_comp, 4),
                },
                diversity_penalty=round(cur_penalty, 4),
                reason_codes=reason_codes,
                warnings=warnings,
                signature=sig,
            ))

        return final_combos

    # -------------------------------------------------------------------------
    # Helper: Standalone Meal Diversity Selection
    # -------------------------------------------------------------------------
    def _select_diverse_standalone(
        self,
        ranked_standalone: List[RankingExplanation],
        max_standalone: int,
    ) -> List[StandaloneMeal]:
        """Select up to max_standalone meals with dish category diversity."""
        if not ranked_standalone:
            return []

        sorted_candidates = sorted(ranked_standalone, key=lambda it: (-it.total_score, it.recipe_id))
        selected: List[StandaloneMeal] = []
        category_counts: Dict[str, int] = {}

        unselected: List[RankingExplanation] = []
        for item in sorted_candidates:
            cat = classify_standalone_dish_category(item.title)
            count = category_counts.get(cat, 0)

            if len(selected) < max_standalone and count < 2:
                category_counts[cat] = count + 1
                meta = self.index.get_metadata_by_id(item.recipe_id) or {}
                selected.append(StandaloneMeal(
                    recipe_id=item.recipe_id,
                    title=item.title,
                    meal_type="standalone",
                    score=item.total_score,
                    score_breakdown=item.score_breakdown,
                    dish_category=cat,
                    primary_cooking_method=meta.get("primary_cooking_method"),
                    cooking_methods=meta.get("cooking_methods", []),
                    normalized_ingredients=meta.get("normalized_ingredients", []),
                    ingredient_groups=meta.get("ingredient_groups", []),
                    reason_codes=item.reason_codes,
                    warnings=item.warnings,
                ))
            else:
                unselected.append(item)

        for item in unselected:
            if len(selected) >= max_standalone:
                break
            cat = classify_standalone_dish_category(item.title)
            meta = self.index.get_metadata_by_id(item.recipe_id) or {}
            selected.append(StandaloneMeal(
                recipe_id=item.recipe_id,
                title=item.title,
                meal_type="standalone",
                score=item.total_score,
                score_breakdown=item.score_breakdown,
                dish_category=cat,
                primary_cooking_method=meta.get("primary_cooking_method"),
                cooking_methods=meta.get("cooking_methods", []),
                normalized_ingredients=meta.get("normalized_ingredients", []),
                ingredient_groups=meta.get("ingredient_groups", []),
                reason_codes=item.reason_codes,
                warnings=item.warnings,
            ))

        return selected

    def evaluate_single_combo(
        self,
        staple_id: str,
        main_dish_id: str,
        soup_id: str,
        vegetable_id: str,
        resolved: Optional[ResolvedConstraints] = None,
        staple_score: float = 0.80,
        main_score: float = 0.80,
        soup_score: float = 0.80,
        vegetable_score: float = 0.80,
    ) -> FamilyMealCombo:
        """Directly score and evaluate a specific 4-dish combo."""
        cfg = self.config
        s_item = RankingExplanation(staple_id, staple_id, "staple", staple_score, 1, {}, [], [], [], 1.0, "verified", [])
        m_item = RankingExplanation(main_dish_id, main_dish_id, "main_dish", main_score, 1, {}, [], [], [], 0.9, "estimated", [])
        p_item = RankingExplanation(soup_id, soup_id, "soup", soup_score, 1, {}, [], [], [], 0.9, "estimated", [])
        v_item = RankingExplanation(vegetable_id, vegetable_id, "vegetable", vegetable_score, 1, {}, [], [], [], 0.9, "estimated", [])

        s = self._extract_fast_feat(s_item, "staple")
        m = self._extract_fast_feat(m_item, "main_dish")
        p = self._extract_fast_feat(p_item, "soup")
        v = self._extract_fast_feat(v_item, "vegetable")

        # 1. Component Relevance
        comp_rel = (
            cfg.role_weight_main * m.score +
            cfg.role_weight_vegetable * v.score +
            cfg.role_weight_soup * p.score +
            cfg.role_weight_staple * s.score
        )

        # 2. Ingredient Diversity
        pen_ing = 0.0
        overlap_reasons = []
        if m.ings_set and p.ings_set and (m.ings_set & p.ings_set):
            pen_ing += cfg.penalty_duplicate_primary_ingredient
            overlap_reasons.append(f"overlap_ing:main_soup:{sorted(list(m.ings_set & p.ings_set))[0]}")
        if m.ings_set and v.ings_set and (m.ings_set & v.ings_set):
            pen_ing += cfg.penalty_duplicate_primary_ingredient
            overlap_reasons.append(f"overlap_ing:main_veg:{sorted(list(m.ings_set & v.ings_set))[0]}")
        if p.ings_set and v.ings_set and (p.ings_set & v.ings_set):
            pen_ing += (cfg.penalty_duplicate_primary_ingredient * 0.5)
        if m.protein_set and p.protein_set and (m.protein_set & p.protein_set):
            pen_ing += cfg.penalty_duplicate_protein_group
            overlap_reasons.append(f"duplicate_protein_group:{sorted(list(m.protein_set & p.protein_set))[0]}")
        ing_div = max(0.0, 1.0 - pen_ing)

        # 3. Cooking Diversity
        cook_div = 1.0
        user_loves_fried = bool(resolved and ("deep_frying" in resolved.user_preferred_cooking_methods))
        if not user_loves_fried:
            if m.primary_cook == "deep_frying" and v.primary_cook == "deep_frying":
                cook_div -= cfg.penalty_monotonous_cooking
            elif m.primary_cook == "stir_frying" and v.primary_cook == "stir_frying":
                cook_div -= (cfg.penalty_monotonous_cooking * 0.35)

        # 4. Clinical Soft
        clin_comp = (m.clin_score + v.clin_score + p.clin_score + s.clin_score) * 0.25

        # 5. Composite Score
        tot_score = (
            cfg.weight_component_relevance * comp_rel +
            cfg.weight_ingredient_diversity * ing_div +
            cfg.weight_cooking_diversity * cook_div +
            cfg.weight_clinical_compatibility * clin_comp
        )
        tot_score = round(max(0.0, min(1.0, tot_score)), 4)

        sig = f"{s.recipe_id}:{m.recipe_id}:{p.recipe_id}:{v.recipe_id}"
        reason_codes = ["FOUR_COMPONENT_BALANCED_MEAL"]
        if ing_div >= 0.85:
            reason_codes.append("DIVERSE_PROTEIN_AND_VEG")
        if cook_div >= 0.90:
            reason_codes.append("BALANCED_COOKING_METHODS")
        for r_code in overlap_reasons:
            reason_codes.append(f"INGREDIENT_OVERLAP_PENALTY:{r_code}")

        components = {
            "staple": MealComponent(s.recipe_id, s.item.title, "staple", s.score, s.primary_cook, s.meta.get("cooking_methods", []), list(s.ings_set), list(s.protein_set)),
            "main_dish": MealComponent(m.recipe_id, m.item.title, "main_dish", m.score, m.primary_cook, m.meta.get("cooking_methods", []), list(m.ings_set), list(m.protein_set)),
            "soup": MealComponent(p.recipe_id, p.item.title, "soup", p.score, p.primary_cook, p.meta.get("cooking_methods", []), list(p.ings_set), list(p.protein_set)),
            "vegetable": MealComponent(v.recipe_id, v.item.title, "vegetable", v.score, v.primary_cook, v.meta.get("cooking_methods", []), list(v.ings_set), list(v.protein_set)),
        }

        return FamilyMealCombo(
            combo_id=f"combo_{sig}",
            components=components,
            meal_score=tot_score,
            score_breakdown={
                "component_relevance": round(comp_rel, 4),
                "ingredient_diversity": round(ing_div, 4),
                "cooking_diversity": round(cook_div, 4),
                "clinical_compatibility": round(clin_comp, 4),
            },
            diversity_penalty=0.0,
            reason_codes=reason_codes,
            warnings=[],
            signature=sig,
        )
