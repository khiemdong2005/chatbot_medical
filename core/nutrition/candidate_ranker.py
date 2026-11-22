"""Phase 4: Content-Based Scoring & Candidate Ranking.

Constraint-Aware Hybrid Meal Recommendation Engine.
Scores and ranks surviving candidates deterministically based on:
1. Clinical soft preferences & portion guidance.
2. Cooking method preferences.
3. Ingredient preferences & soft dislikes.
4. Metadata confidence & classification certainty.
5. Nutrition data provenance & completeness.

Hard Constraint Isolation Invariant:
- ranked_ids ⊆ clinically_filtered_ids
- No score can bypass hard exclusions, medical contraindications, or allergies.
- Zero LLM invocation, zero embeddings, 100% deterministic execution.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from core.nutrition.clinical_constraints import (
    CandidatePools,
    ClinicalRuleDefinition,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.metadata_index import (
    get_metadata_index,
    InMemoryInvertedIndex,
    STANDARD_COMBO_ROLES,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Configuration & Data Models
# -----------------------------------------------------------------------------

@dataclass
class ScoringConfig:
    """Configurable weights and thresholds for multi-objective scoring."""
    # Additive weights (normalized to sum to 1.0)
    weight_clinical: float = 0.35           # Clinical soft preference & portion guidance
    weight_cooking: float = 0.20            # Cooking method preference
    weight_ingredient: float = 0.25         # User ingredient preferences & dislikes
    weight_metadata: float = 0.10           # Classification confidence & provenance
    weight_nutrition_quality: float = 0.10  # Nutrition data completeness & verification

    # Feature scaling increments
    bonus_clinical_match: float = 0.25
    penalty_clinical_avoid: float = 0.25
    bonus_cooking_match: float = 0.50
    bonus_secondary_cooking_match: float = 0.20
    penalty_cooking_avoid: float = 0.40
    penalty_secondary_cooking_avoid: float = 0.15
    bonus_user_ing_match: float = 0.25
    bonus_user_group_match: float = 0.15
    penalty_user_dislike: float = 0.25

    # Top-K limits per role (configurable defaults)
    top_k_per_role: Dict[str, int] = field(default_factory=lambda: {
        "staple": 20,
        "main_dish": 30,
        "soup": 20,
        "vegetable": 20,
        "standalone": 30,
        "beverage": 15,
        "dessert": 15,
        "snack": 15,
    })


@dataclass
class ScoringContext:
    """Consolidated preferences and guidelines for scoring candidate recipes."""
    # Clinical soft preferences (from Phase 3 ResolvedConstraints)
    clinical_preferred_ingredients: Set[str] = field(default_factory=set)
    clinical_preferred_ingredient_groups: Set[str] = field(default_factory=set)
    clinical_avoided_ingredients: Set[str] = field(default_factory=set)
    clinical_avoided_ingredient_groups: Set[str] = field(default_factory=set)
    clinical_preferred_cooking_methods: Set[str] = field(default_factory=set)
    clinical_avoided_cooking_methods: Set[str] = field(default_factory=set)
    nutrient_limits: Dict[str, Any] = field(default_factory=dict)

    # User personal preferences
    user_preferred_ingredients: Set[str] = field(default_factory=set)
    user_preferred_ingredient_groups: Set[str] = field(default_factory=set)
    user_avoided_ingredients: Set[str] = field(default_factory=set)
    user_preferred_cooking_methods: Set[str] = field(default_factory=set)
    user_avoided_cooking_methods: Set[str] = field(default_factory=set)

    # Pre-computed unions for ultra-low latency inner loops
    all_preferred_methods: Set[str] = field(default_factory=set)
    all_avoided_methods: Set[str] = field(default_factory=set)

    # Activated clinical rule IDs for audit traceability
    activated_rule_ids: List[str] = field(default_factory=list)

    @classmethod
    def from_resolved(
        cls,
        resolved: Optional[ResolvedConstraints] = None,
        pools: Optional[CandidatePools] = None,
    ) -> "ScoringContext":
        """Build scoring context from resolved constraints and candidate pools."""
        ctx = cls()
        if not resolved and not pools:
            return ctx

        if resolved:
            ctx.clinical_preferred_ingredients = set(resolved.soft_preferred_ingredients)
            ctx.clinical_preferred_ingredient_groups = set(resolved.soft_preferred_ingredient_groups)
            ctx.clinical_avoided_ingredients = set(resolved.soft_avoided_ingredients)
            ctx.clinical_avoided_ingredient_groups = set(resolved.soft_avoided_ingredient_groups)
            ctx.clinical_preferred_cooking_methods = set(resolved.soft_preferred_cooking_methods)
            ctx.clinical_avoided_cooking_methods = set(resolved.soft_avoided_cooking_methods)
            # Explicit user preferences (isolated from clinical guidelines)
            ctx.user_preferred_ingredients = set(resolved.user_preferred_ingredients)
            ctx.user_preferred_ingredient_groups = set(resolved.user_preferred_ingredient_groups)
            ctx.user_preferred_cooking_methods = set(resolved.user_preferred_cooking_methods)
            ctx.user_avoided_ingredients = set(resolved.user_avoided_ingredients)
            ctx.user_avoided_cooking_methods = set(resolved.user_avoided_cooking_methods)
            ctx.nutrient_limits = dict(resolved.nutrient_limits)
            ctx.activated_rule_ids = [r.rule_id for r in resolved.applied_rules]

        if pools and pools.soft_constraints:
            sc = pools.soft_constraints
            if "user_preferred_ingredients" in sc:
                ctx.user_preferred_ingredients.update(sc["user_preferred_ingredients"])
            if "user_preferred_ingredient_groups" in sc:
                ctx.user_preferred_ingredient_groups.update(sc["user_preferred_ingredient_groups"])
            if "user_preferred_cooking_methods" in sc:
                ctx.user_preferred_cooking_methods.update(sc["user_preferred_cooking_methods"])
            if "user_avoided_ingredients" in sc:
                ctx.user_avoided_ingredients.update(sc["user_avoided_ingredients"])
            if "user_avoided_cooking_methods" in sc:
                ctx.user_avoided_cooking_methods.update(sc["user_avoided_cooking_methods"])

        # Precompute unions and normalize canonical cooking method aliases
        method_alias_map = {
            "steaming": "steaming", "hap": "steaming", "do hap": "steaming", "mon hap": "steaming",
            "stir_frying": "stir_frying", "xao": "stir_frying", "do xao": "stir_frying", "mon xao": "stir_frying",
            "boiling": "boiling", "luoc": "boiling", "canh": "boiling",
            "grilling": "grilling", "nuong": "grilling", "do nuong": "grilling", "mon nuong": "grilling",
            "braising": "braising", "kho": "braising", "mon kho": "braising",
            "deep_frying": "deep_frying", "chien": "deep_frying", "ran": "deep_frying",
        }
        ctx.clinical_preferred_cooking_methods = {method_alias_map.get(m, m) for m in ctx.clinical_preferred_cooking_methods}
        ctx.user_preferred_cooking_methods = {method_alias_map.get(m, m) for m in ctx.user_preferred_cooking_methods}
        ctx.clinical_avoided_cooking_methods = {method_alias_map.get(m, m) for m in ctx.clinical_avoided_cooking_methods}
        ctx.user_avoided_cooking_methods = {method_alias_map.get(m, m) for m in ctx.user_avoided_cooking_methods}

        ctx.all_preferred_methods = ctx.clinical_preferred_cooking_methods | ctx.user_preferred_cooking_methods
        ctx.all_avoided_methods = ctx.clinical_avoided_cooking_methods | ctx.user_avoided_cooking_methods

        return ctx


@dataclass
class RankingExplanation:
    """Detailed explainable breakdown for a scored recipe."""
    recipe_id: str
    title: str
    primary_role: str
    total_score: float
    rank: int
    score_breakdown: Dict[str, float]
    matched_preferences: List[str]
    penalized_preferences: List[str]
    reason_codes: List[str]
    metadata_confidence: float
    nutrition_quality: str
    warnings: List[str]

    @property
    def score(self) -> float:
        return self.total_score


@dataclass
class RankedResults:
    """Segregated ranked candidate lists per meal role."""
    ranked_by_role: Dict[str, List[RankingExplanation]] = field(default_factory=lambda: {
        "staple": [],
        "main_dish": [],
        "soup": [],
        "vegetable": [],
        "standalone": [],
        "beverage": [],
        "dessert": [],
        "snack": [],
    })
    total_ranked_count: int = 0
    unique_ranked_count: int = 0
    safety_status: str = "PASSED_KNOWN_CONSTRAINTS"
    is_safe_to_proceed: bool = True
    execution_metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Feature Extractor & Scorer
# -----------------------------------------------------------------------------

class RecipeFeatureExtractor:
    """Extracts normalized feature vectors and metadata flags for candidate scoring."""

    @staticmethod
    def extract_features(
        recipe_id: str,
        index: InMemoryInvertedIndex,
    ) -> Dict[str, Any]:
        """Extract all scoring-relevant attributes from metadata sidecar."""
        meta = index.get_metadata_by_id(recipe_id) or {}
        recipe = index.get_recipe_by_id(recipe_id) or {}

        title = recipe.get("title") or meta.get("title") or recipe_id
        primary_role = meta.get("primary_role", "other")

        # Use cached frozensets for high-throughput performance
        norm_ingredients = meta.get("_norm_ing_set")
        if norm_ingredients is None:
            norm_ingredients = meta["_norm_ing_set"] = frozenset(meta.get("normalized_ingredients") or [])

        ingredient_groups = meta.get("_ing_grp_set")
        if ingredient_groups is None:
            ingredient_groups = meta["_ing_grp_set"] = frozenset(meta.get("ingredient_groups") or [])

        cooking_methods = meta.get("_methods_set")
        if cooking_methods is None:
            cooking_methods = meta["_methods_set"] = frozenset(meta.get("cooking_methods") or [])

        primary_cooking_method = meta.get("primary_cooking_method")
        secondary_cooking_methods = meta.get("_sec_methods_set")
        if secondary_cooking_methods is None:
            secondary_cooking_methods = meta["_sec_methods_set"] = frozenset(meta.get("secondary_cooking_methods") or [])

        # Metadata quality attributes
        confidence = float(meta.get("classification_confidence", 0.85))
        review_required = bool(meta.get("review_required", False) or meta.get("needs_manual_review", False))
        uncertainty = bool(meta.get("classification_uncertainty", False))

        # Nutrition completeness attributes
        nutrition_verified = bool(meta.get("nutrition_verified", False))
        macro_consistency = bool(meta.get("macro_consistency", False))
        has_carbohydrate = bool(meta.get("has_carbohydrate_data", False))
        has_calories = meta.get("calories_per_serving") is not None
        servings = meta.get("servings_numeric")

        # Static metadata component score
        meta_score = confidence
        if review_required:
            meta_score -= 0.30
        if uncertainty:
            meta_score -= 0.10
        meta_score = max(0.0, min(1.0, meta_score))

        # Static nutrition component score
        if nutrition_verified:
            nutrition_score = 1.00
            nutrition_label = "verified"
        elif macro_consistency and has_carbohydrate:
            nutrition_score = 0.75
            nutrition_label = "consistent"
        elif has_calories:
            nutrition_score = 0.50
            nutrition_label = "estimated"
        else:
            nutrition_score = 0.30
            nutrition_label = "incomplete"

        return {
            "recipe_id": recipe_id,
            "title": title,
            "primary_role": primary_role,
            "normalized_ingredients": norm_ingredients,
            "ingredient_groups": ingredient_groups,
            "primary_cooking_method": primary_cooking_method,
            "secondary_cooking_methods": secondary_cooking_methods,
            "cooking_methods": cooking_methods,
            "classification_confidence": confidence,
            "review_required": review_required,
            "classification_uncertainty": uncertainty,
            "nutrition_verified": nutrition_verified,
            "macro_consistency": macro_consistency,
            "has_carbohydrate_data": has_carbohydrate,
            "has_calories": has_calories,
            "servings_numeric": servings,
            "static_meta_score": meta_score,
            "static_nutrition_score": nutrition_score,
            "nutrition_quality_label": nutrition_label,
        }


class ContentBasedScorer:
    """Computes weighted multi-objective scores and explainable reason codes."""

    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or ScoringConfig()

    def score_raw(
        self,
        features: Dict[str, Any],
        context: ScoringContext,
    ) -> float:
        """Fast scalar score calculation for high-throughput ranking."""
        cfg = self.config
        norm_ings = features["normalized_ingredients"]
        ing_groups = features["ingredient_groups"]
        methods = features["cooking_methods"]

        # 1. Clinical (bounded bonus to avoid saturation)
        clinical_score = 0.50
        clin_bonus = 0.0
        if context.clinical_preferred_ingredients and (norm_ings & context.clinical_preferred_ingredients):
            clin_bonus += cfg.bonus_clinical_match
        if context.clinical_preferred_ingredient_groups and (ing_groups & context.clinical_preferred_ingredient_groups):
            clin_bonus += cfg.bonus_clinical_match
        clinical_score += min(0.35, clin_bonus)

        if context.clinical_avoided_ingredients and (norm_ings & context.clinical_avoided_ingredients):
            clinical_score -= cfg.penalty_clinical_avoid * len(norm_ings & context.clinical_avoided_ingredients)
        if context.clinical_avoided_ingredient_groups and (ing_groups & context.clinical_avoided_ingredient_groups):
            clinical_score -= cfg.penalty_clinical_avoid * len(ing_groups & context.clinical_avoided_ingredient_groups)
        clinical_score = max(0.0, min(1.0, clinical_score))

        # 2. Cooking (neutral 0.50 if no methods found)
        cooking_score = 0.50
        pri_method = features.get("primary_cooking_method")
        sec_methods = features.get("secondary_cooking_methods") or frozenset()
        if methods:
            if context.all_preferred_methods:
                if pri_method and pri_method in context.all_preferred_methods:
                    cooking_score += cfg.bonus_cooking_match
                elif sec_methods & context.all_preferred_methods:
                    cooking_score += cfg.bonus_secondary_cooking_match
                elif methods & context.all_preferred_methods:
                    cooking_score += cfg.bonus_cooking_match

            if context.all_avoided_methods:
                if pri_method and pri_method in context.all_avoided_methods:
                    cooking_score -= cfg.penalty_cooking_avoid
                elif sec_methods & context.all_avoided_methods:
                    cooking_score -= cfg.penalty_secondary_cooking_avoid
                elif methods & context.all_avoided_methods:
                    cooking_score -= cfg.penalty_cooking_avoid

            cooking_score = max(0.0, min(1.0, cooking_score))

        # 3. User Ingredient Preferences (neutral 0.50 if user declared no preferences)
        ingredient_score = 0.50
        if context.user_preferred_ingredients or context.user_preferred_ingredient_groups or context.user_avoided_ingredients:
            if context.user_preferred_ingredients and (norm_ings & context.user_preferred_ingredients):
                ingredient_score += cfg.bonus_user_ing_match * len(norm_ings & context.user_preferred_ingredients)
            if context.user_preferred_ingredient_groups and (ing_groups & context.user_preferred_ingredient_groups):
                ingredient_score += cfg.bonus_user_group_match * len(ing_groups & context.user_preferred_ingredient_groups)
            if context.user_avoided_ingredients and (norm_ings & context.user_avoided_ingredients):
                ingredient_score -= cfg.penalty_user_dislike * len(norm_ings & context.user_avoided_ingredients)
            ingredient_score = max(0.0, min(1.0, ingredient_score))

        # 4. Metadata Confidence (Static pre-computed or dynamic fallback)
        meta_score = features.get("static_meta_score")
        if meta_score is None:
            confidence = float(features.get("classification_confidence", 0.85))
            review_required = bool(features.get("review_required", False) or features.get("needs_manual_review", False))
            uncertainty = bool(features.get("classification_uncertainty", False))
            meta_score = confidence
            if review_required:
                meta_score -= 0.30
            if uncertainty:
                meta_score -= 0.10
            meta_score = max(0.0, min(1.0, meta_score))

        # 5. Nutrition Quality (Static pre-computed or dynamic fallback)
        nutrition_score = features.get("static_nutrition_score")
        if nutrition_score is None:
            nutrition_verified = bool(features.get("nutrition_verified", False))
            macro_consistency = bool(features.get("macro_consistency", False))
            has_carbohydrate = bool(features.get("has_carbohydrate_data", False))
            has_calories = features.get("has_calories", False) or features.get("calories_per_serving") is not None
            if nutrition_verified:
                nutrition_score = 1.00
            elif macro_consistency and has_carbohydrate:
                nutrition_score = 0.75
            elif has_calories:
                nutrition_score = 0.50
            else:
                nutrition_score = 0.30

        # Total
        total_score = (
            cfg.weight_clinical * clinical_score +
            cfg.weight_cooking * cooking_score +
            cfg.weight_ingredient * ingredient_score +
            cfg.weight_metadata * meta_score +
            cfg.weight_nutrition_quality * nutrition_score
        )
        return round(max(0.0, min(1.0, total_score)), 4)

    def score_recipe(
        self,
        features: Dict[str, Any],
        context: ScoringContext,
    ) -> Tuple[float, Dict[str, float], List[str], List[str], List[str], str]:
        """Full explainable evaluation with breakdowns and reason codes for Top-K items."""
        cfg = self.config
        matched_prefs: List[str] = []
        penalized_prefs: List[str] = []
        reason_codes: List[str] = []

        norm_ings = features["normalized_ingredients"]
        ing_groups = features["ingredient_groups"]
        methods = features["cooking_methods"]

        # 1. Clinical Soft Preference Alignment (Bounded bonus to avoid saturation)
        clinical_score = 0.50
        clin_bonus = 0.0
        if context.clinical_preferred_ingredients:
            matched_clin_ings = norm_ings & context.clinical_preferred_ingredients
            for ing in matched_clin_ings:
                clin_bonus += cfg.bonus_clinical_match
                matched_prefs.append(f"clinical_pref_ing:{ing}")
                reason_codes.append("CLINICAL_PREFERRED_INGREDIENT")

        if context.clinical_preferred_ingredient_groups:
            matched_clin_groups = ing_groups & context.clinical_preferred_ingredient_groups
            for grp in matched_clin_groups:
                clin_bonus += cfg.bonus_clinical_match
                matched_prefs.append(f"clinical_pref_group:{grp}")
                reason_codes.append("CLINICAL_PREFERRED_GROUP")

        clinical_score += min(0.35, clin_bonus)

        if context.clinical_avoided_ingredients:
            penalized_clin_ings = norm_ings & context.clinical_avoided_ingredients
            for ing in penalized_clin_ings:
                clinical_score -= cfg.penalty_clinical_avoid
                penalized_prefs.append(f"clinical_avoid_ing:{ing}")
                reason_codes.append("CLINICAL_AVOIDED_INGREDIENT")

        if context.clinical_avoided_ingredient_groups:
            penalized_clin_groups = ing_groups & context.clinical_avoided_ingredient_groups
            for grp in penalized_clin_groups:
                clinical_score -= cfg.penalty_clinical_avoid
                penalized_prefs.append(f"clinical_avoid_group:{grp}")
                reason_codes.append("CLINICAL_AVOIDED_GROUP")

        clinical_score = max(0.0, min(1.0, clinical_score))

        # 2. Cooking Method Suitability (Neutral 0.50 if no methods found)
        cooking_score = 0.50
        pri_method = features.get("primary_cooking_method")
        sec_methods = features.get("secondary_cooking_methods") or frozenset()
        if methods:
            if context.all_preferred_methods:
                if pri_method and pri_method in context.all_preferred_methods:
                    cooking_score += cfg.bonus_cooking_match
                    matched_prefs.append(f"primary_pref_method:{pri_method}")
                    reason_codes.append("PREFERRED_COOKING_METHOD")
                elif sec_methods & context.all_preferred_methods:
                    matched_sec = sec_methods & context.all_preferred_methods
                    cooking_score += cfg.bonus_secondary_cooking_match
                    for m in matched_sec:
                        matched_prefs.append(f"secondary_pref_method:{m}")
                    reason_codes.append("SECONDARY_PREFERRED_COOKING_METHOD")
                elif methods & context.all_preferred_methods:
                    matched_methods = methods & context.all_preferred_methods
                    for m in matched_methods:
                        cooking_score += cfg.bonus_cooking_match
                        matched_prefs.append(f"pref_method:{m}")
                        reason_codes.append("PREFERRED_COOKING_METHOD")

            if context.all_avoided_methods:
                if pri_method and pri_method in context.all_avoided_methods:
                    cooking_score -= cfg.penalty_cooking_avoid
                    penalized_prefs.append(f"avoid_primary_method:{pri_method}")
                    reason_codes.append("AVOIDED_COOKING_METHOD")
                elif sec_methods & context.all_avoided_methods:
                    matched_sec_avoid = sec_methods & context.all_avoided_methods
                    cooking_score -= cfg.penalty_secondary_cooking_avoid
                    for m in matched_sec_avoid:
                        penalized_prefs.append(f"avoid_secondary_method:{m}")
                    reason_codes.append("SECONDARY_AVOIDED_COOKING_METHOD")
                elif methods & context.all_avoided_methods:
                    penalized_methods = methods & context.all_avoided_methods
                    for m in penalized_methods:
                        cooking_score -= cfg.penalty_cooking_avoid
                        penalized_prefs.append(f"avoid_method:{m}")
                        reason_codes.append("AVOIDED_COOKING_METHOD")

            cooking_score = max(0.0, min(1.0, cooking_score))

        # 3. User Ingredient Preferences & Dislikes (Strictly User, neutral 0.50 if no user preferences)
        ingredient_score = 0.50
        if context.user_preferred_ingredients or context.user_preferred_ingredient_groups or context.user_avoided_ingredients:
            if context.user_preferred_ingredients:
                matched_user_ings = norm_ings & context.user_preferred_ingredients
                for ing in matched_user_ings:
                    ingredient_score += cfg.bonus_user_ing_match
                    matched_prefs.append(f"user_pref_ing:{ing}")
                    reason_codes.append("USER_PREFERRED_INGREDIENT")

            if context.user_preferred_ingredient_groups:
                matched_user_groups = ing_groups & context.user_preferred_ingredient_groups
                for grp in matched_user_groups:
                    ingredient_score += cfg.bonus_user_group_match
                    matched_prefs.append(f"user_pref_group:{grp}")
                    reason_codes.append("USER_PREFERRED_GROUP")

            if context.user_avoided_ingredients:
                matched_user_dislikes = norm_ings & context.user_avoided_ingredients
                for ing in matched_user_dislikes:
                    ingredient_score -= cfg.penalty_user_dislike
                    penalized_prefs.append(f"user_dislike_ing:{ing}")
                    reason_codes.append("USER_DISLIKED_INGREDIENT")

            ingredient_score = max(0.0, min(1.0, ingredient_score))

        # 4. Metadata Confidence (Static pre-computed or dynamic fallback)
        meta_score = features.get("static_meta_score")
        if meta_score is None:
            confidence = float(features.get("classification_confidence", 0.85))
            review_required = bool(features.get("review_required", False) or features.get("needs_manual_review", False))
            uncertainty = bool(features.get("classification_uncertainty", False))
            meta_score = confidence
            if review_required:
                meta_score -= 0.30
            if uncertainty:
                meta_score -= 0.10
            meta_score = max(0.0, min(1.0, meta_score))

        if meta_score >= 0.90:
            reason_codes.append("HIGH_METADATA_CONFIDENCE")
        else:
            reason_codes.append("METADATA_UNCERTAINTY")

        # 5. Nutrition Quality (Static pre-computed or dynamic fallback)
        nutrition_score = features.get("static_nutrition_score")
        nutrition_quality_label = features.get("nutrition_quality_label")
        if nutrition_score is None or nutrition_quality_label is None:
            nutrition_verified = bool(features.get("nutrition_verified", False))
            macro_consistency = bool(features.get("macro_consistency", False))
            has_carbohydrate = bool(features.get("has_carbohydrate_data", False))
            has_calories = features.get("has_calories", False) or features.get("calories_per_serving") is not None
            if nutrition_verified:
                nutrition_score = 1.00
                nutrition_quality_label = "verified"
            elif macro_consistency and has_carbohydrate:
                nutrition_score = 0.75
                nutrition_quality_label = "consistent"
            elif has_calories:
                nutrition_score = 0.50
                nutrition_quality_label = "estimated"
            else:
                nutrition_score = 0.30
                nutrition_quality_label = "incomplete"

        if nutrition_quality_label == "verified":
            reason_codes.append("VERIFIED_NUTRITION_DATA")
        elif nutrition_quality_label == "consistent":
            reason_codes.append("CONSISTENT_NUTRITION_DATA")
        elif nutrition_quality_label == "estimated":
            reason_codes.append("ESTIMATED_NUTRITION_DATA")
        else:
            reason_codes.append("INCOMPLETE_NUTRITION_DATA")

        # Weighted Total Score Compilation
        total_score = (
            cfg.weight_clinical * clinical_score +
            cfg.weight_cooking * cooking_score +
            cfg.weight_ingredient * ingredient_score +
            cfg.weight_metadata * meta_score +
            cfg.weight_nutrition_quality * nutrition_score
        )
        total_score = round(max(0.0, min(1.0, total_score)), 4)

        breakdown = {
            "clinical_preferences": round(clinical_score, 4),
            "cooking_method": round(cooking_score, 4),
            "ingredient_preferences": round(ingredient_score, 4),
            "metadata_quality": round(meta_score, 4),
            "nutrition_quality": round(nutrition_score, 4),
        }

        # Deduplicate reason codes
        seen_codes = set()
        dedup_codes = []
        for rc in reason_codes:
            if rc not in seen_codes:
                seen_codes.add(rc)
                dedup_codes.append(rc)

        return (
            total_score,
            breakdown,
            matched_prefs,
            penalized_prefs,
            dedup_codes,
            nutrition_quality_label,
        )


# -----------------------------------------------------------------------------
# Candidate Ranker Engine
# -----------------------------------------------------------------------------

class CandidateRanker:
    """Executes deterministic role-segregated candidate ranking."""

    def __init__(
        self,
        index: Optional[InMemoryInvertedIndex] = None,
        config: Optional[ScoringConfig] = None,
    ):
        self.index = index or get_metadata_index()
        self.config = config or ScoringConfig()
        self.feature_extractor = RecipeFeatureExtractor()
        self.scorer = ContentBasedScorer(config=self.config)
        # Precompute static catalog features for O(1) ultra-low latency access
        self.features_by_id: Dict[str, Dict[str, Any]] = {
            rid: self.feature_extractor.extract_features(rid, index=self.index)
            for rid in self.index.all_recipe_ids
        }

    def rank_candidates(
        self,
        pools: CandidatePools,
        resolved: Optional[ResolvedConstraints] = None,
        top_k_overrides: Optional[Dict[str, int]] = None,
    ) -> RankedResults:
        """Score and sort candidates within their segregated meal pools."""
        t_start = time.perf_counter()
        results = RankedResults()
        results.safety_status = pools.safety_status
        results.warnings = list(pools.warnings)

        # ---------------------------------------------------------------------
        # 1. Hard Constraint Isolation Gate
        # ---------------------------------------------------------------------
        if pools.safety_status not in ("PASSED_KNOWN_CONSTRAINTS", "SAFE"):
            results.is_safe_to_proceed = False
            total_duration_ms = (time.perf_counter() - t_start) * 1000.0
            results.execution_metrics = {
                "total_candidates_evaluated": 0,
                "total_ranked_count": 0,
                "unique_ranked_count": 0,
                "safety_halt": True,
                "safety_status": pools.safety_status,
                "ranking_latency_ms": round(total_duration_ms, 3),
            }
            return results

        # ---------------------------------------------------------------------
        # 2. Build Scoring Context
        # ---------------------------------------------------------------------
        context = ScoringContext.from_resolved(resolved=resolved, pools=pools)

        # ---------------------------------------------------------------------
        # 3. Two-Stage Ultra-Low Latency Role Ranking
        # ---------------------------------------------------------------------
        k_limits = dict(self.config.top_k_per_role)
        if top_k_overrides:
            k_limits.update(top_k_overrides)

        t_feature_extract = 0.0
        t_scoring = 0.0
        t_sorting = 0.0

        all_unique_ranked_ids: Set[str] = set()
        total_ranked_items = 0

        # Stage 1: Fast raw scalar scoring for all unique surviving candidates
        t_sc0 = time.perf_counter()
        scores: Dict[str, float] = {}
        for rid in pools.unique_candidate_ids:
            feats = self.features_by_id.get(rid)
            if feats is None:
                feats = self.features_by_id[rid] = self.feature_extractor.extract_features(rid, index=self.index)
            scores[rid] = self.scorer.score_raw(feats, context)
        t_scoring += (time.perf_counter() - t_sc0)

        target_pools: Dict[str, List[str]] = {
            "staple": pools.combo_candidates.get("staple", []),
            "main_dish": pools.combo_candidates.get("main_dish", []),
            "soup": pools.combo_candidates.get("soup", []),
            "vegetable": pools.combo_candidates.get("vegetable", []),
            "standalone": pools.standalone_candidates,
            "beverage": pools.beverage_candidates,
            "dessert": pools.dessert_candidates,
            "snack": pools.snack_candidates,
        }

        # Stage 2: Role sort & Top-K explanation generation
        for role_name, candidate_id_list in target_pools.items():
            if not candidate_id_list:
                continue

            # Deterministic sorting: Score DESC, recipe_id ASC (Tie-break invariant)
            t_sort0 = time.perf_counter()
            role_scored: List[Tuple[float, str]] = [
                (scores[rid], rid) for rid in candidate_id_list if rid in scores
            ]
            role_scored.sort(key=lambda item: (-item[0], item[1]))
            t_sorting += (time.perf_counter() - t_sort0)

            # Apply Top-K slice
            k_val = k_limits.get(role_name, 20)
            top_k_scored = role_scored[:k_val]

            # Generate full explanations ONLY for top-k candidates
            ranked_explanations: List[RankingExplanation] = []
            for rank_idx, (tot_score, rid) in enumerate(top_k_scored, start=1):
                feats = self.features_by_id[rid]
                _, breakdown, matched, penalized, reasons, nutr_qual = self.scorer.score_recipe(feats, context)

                expl = RankingExplanation(
                    recipe_id=rid,
                    title=feats["title"],
                    primary_role=feats["primary_role"],
                    total_score=tot_score,
                    rank=rank_idx,
                    score_breakdown=breakdown,
                    matched_preferences=matched,
                    penalized_preferences=penalized,
                    reason_codes=reasons,
                    metadata_confidence=feats["classification_confidence"],
                    nutrition_quality=nutr_qual,
                    warnings=[],
                )
                ranked_explanations.append(expl)
                all_unique_ranked_ids.add(rid)

            results.ranked_by_role[role_name] = ranked_explanations
            total_ranked_items += len(ranked_explanations)

        t_total_end = time.perf_counter()
        ranking_duration_ms = (t_total_end - t_start) * 1000.0

        results.total_ranked_count = total_ranked_items
        results.unique_ranked_count = len(all_unique_ranked_ids)
        results.execution_metrics = {
            "total_candidates_evaluated": len(pools.unique_candidate_ids),
            "total_ranked_count": total_ranked_items,
            "unique_ranked_count": len(all_unique_ranked_ids),
            "feature_extraction_ms": round(t_feature_extract * 1000.0, 3),
            "scoring_ms": round(t_scoring * 1000.0, 3),
            "sorting_ms": round(t_sorting * 1000.0, 3),
            "ranking_latency_ms": round(ranking_duration_ms, 3),
        }

        return results
