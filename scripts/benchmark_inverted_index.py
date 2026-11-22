"""Comprehensive Benchmark Suite for Phase 2: In-Memory Inverted Index.

Compares:
Method A — Legacy linear scan + regex
Method B — Precomputed metadata linear scan
Method C — In-Memory Inverted Index

Measures:
- Latencies: Mean, P50, P95, P99
- Throughput (ops/sec)
- Speedup ratio (A/C, B/C)
- Result candidate counts and parity
- Memory overhead
- Concurrent reads (20, 50, 100 threads)
"""

from collections import defaultdict
import concurrent.futures
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any, Callable, Dict, List, Set, Tuple
import unicodedata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.nutrition.metadata_index import (
    get_metadata_index,
    InMemoryInvertedIndex,
    SUPPORTED_ALLERGENS,
    STANDARD_COMBO_ROLES,
)

RECIPES_PATH = PROJECT_ROOT / "data" / "recipes" / "vifoodrec" / "recipes.json"
METADATA_PATH = PROJECT_ROOT / "data" / "recipes" / "vifoodrec" / "recipes_metadata.json"
CANONICAL_STAPLES_PATH = PROJECT_ROOT / "data" / "recipes" / "canonical_staples.json"

NUM_WARMUP = 15
NUM_ITERATIONS = 120

def normalize(text: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(text).lower())
                             if unicodedata.category(c) != "Mn").replace("đ", "d").split())

# -----------------------------------------------------------------------------
# Setup raw data for Methods A and B
# -----------------------------------------------------------------------------
with open(RECIPES_PATH, "r", encoding="utf-8") as f:
    raw_recipes = json.load(f)
with open(CANONICAL_STAPLES_PATH, "r", encoding="utf-8") as f:
    raw_staples = json.load(f)
catalog_2471 = raw_recipes + raw_staples

with open(METADATA_PATH, "r", encoding="utf-8") as f:
    raw_metadata = json.load(f)

# Build metadata map for B
meta_map_2471 = {m["id"]: m for m in raw_metadata}
for s in raw_staples:
    meta_map_2471[s["id"]] = {
        "id": s["id"],
        "primary_role": "staple",
        "eligible_combo_roles": ["staple"],
        "normalized_ingredients": s.get("normalized_ingredients", []),
        "ingredient_groups": s.get("ingredient_groups", []),
        "cooking_methods": s.get("cooking_methods", []),
        "allergen_assessments": s.get("allergen_assessments", {}),
        "needs_manual_review": False,
        "review_required": False
    }

index_inst = get_metadata_index()

# -----------------------------------------------------------------------------
# Method Implementations
# -----------------------------------------------------------------------------

# Method A: Legacy linear scan with Regex
def legacy_filter_scenario(scenario_key: str, catalog: List[Dict[str, Any]]) -> List[str]:
    results = []
    
    # Regex patterns
    shrimp_pat = re.compile(r"\btôm\b|\btép(?!\s+tỏi)\b", re.I)
    fish_pat = re.compile(r"\bcá\b|\bnước mắm\b", re.I)
    milk_pat = re.compile(r"\bsữa\b|\bphô mai\b|\bbơ\b", re.I)
    egg_pat = re.compile(r"\btrứng\b|\bmayonnaise\b", re.I)
    peanut_pat = re.compile(r"\bđậu phộng\b|\blạc\b", re.I)
    beef_pat = re.compile(r"\bbò\b|\bbê\b", re.I)
    fry_pat = re.compile(r"chiên|rán", re.I)
    dessert_pat = re.compile(r"chè|bánh ngọt|kem|thạch", re.I)
    
    for r in catalog:
        title = r.get("title", "")
        ing_text = " ".join(str(i.get("name", "")) for i in r.get("ingredients", []))
        full_text = f"{title} {ing_text}"
        
        if scenario_key == "healthy":
            if r.get("recipe_type", "food") == "food":
                results.append(r["id"])
        elif scenario_key == "gout":
            # Exclude seafood, beef
            if not (shrimp_pat.search(full_text) or fish_pat.search(full_text) or beef_pat.search(full_text)):
                results.append(r["id"])
        elif scenario_key == "diabetes":
            # Exclude desserts and sugary recipes
            if not dessert_pat.search(title):
                results.append(r["id"])
        elif scenario_key == "fatty_liver":
            # Exclude fried dishes
            if not fry_pat.search(title):
                results.append(r["id"])
        elif scenario_key == "shrimp_allergy":
            if not shrimp_pat.search(full_text):
                results.append(r["id"])
        elif scenario_key == "cow_milk_allergy":
            if not milk_pat.search(full_text):
                results.append(r["id"])
        elif scenario_key == "multiple_allergens":
            # Exclude shrimp, egg, peanut, cow_milk
            if not (shrimp_pat.search(full_text) or egg_pat.search(full_text) or 
                    peanut_pat.search(full_text) or milk_pat.search(full_text)):
                results.append(r["id"])
        elif scenario_key == "multiple_constraints":
            # Exclude shrimp, beef, dessert
            if not (shrimp_pat.search(full_text) or beef_pat.search(full_text) or dessert_pat.search(title)):
                results.append(r["id"])
        elif scenario_key == "unsupported_allergen":
            # Unknown allergen like tree nuts - legacy does full string scan
            tree_pat = re.compile(r"hạt điều|hạnh nhân|óc chó|hạt dẻ", re.I)
            if not tree_pat.search(full_text):
                results.append(r["id"])
        elif scenario_key == "combo_role_main":
            # Heuristic check for main dish
            if r.get("dish_role") == "main" or (not r.get("title", "").lower().startswith("canh") and not dessert_pat.search(title)):
                results.append(r["id"])
        elif scenario_key == "empty_pool":
            # Impossible combination: must be drink and must have beef and no beef
            if r.get("recipe_type") == "drink" and beef_pat.search(full_text) and not beef_pat.search(full_text):
                results.append(r["id"])
                
    return results


# Method B: Precomputed metadata linear scan (iterating dicts in memory)
def metadata_linear_scan_scenario(scenario_key: str, meta_list: List[Dict[str, Any]]) -> List[str]:
    results = []
    for m in meta_list:
        if m.get("needs_manual_review") or m.get("review_required"):
            continue
            
        assessments = m.get("allergen_assessments", {})
        
        if scenario_key == "healthy":
            if m.get("primary_role") != "other":
                results.append(m["id"])
        elif scenario_key == "gout":
            # Check groups for seafood and beef
            groups = set(m.get("ingredient_groups", []))
            if "seafood" not in groups and "beef" not in groups:
                results.append(m["id"])
        elif scenario_key == "diabetes":
            if m.get("primary_role") not in ("dessert", "beverage"):
                results.append(m["id"])
        elif scenario_key == "fatty_liver":
            methods = set(m.get("cooking_methods", []))
            if "deep_frying" not in methods and "frying" not in methods:
                results.append(m["id"])
        elif scenario_key == "shrimp_allergy":
            status = assessments.get("shrimp", {}).get("status")
            if status != "known_present" and status != "unknown":
                results.append(m["id"])
        elif scenario_key == "cow_milk_allergy":
            status = assessments.get("cow_milk", {}).get("status")
            if status != "known_present" and status != "unknown":
                results.append(m["id"])
        elif scenario_key == "multiple_allergens":
            blocked = False
            for ag in ("shrimp", "egg", "peanut", "cow_milk"):
                st = assessments.get(ag, {}).get("status")
                if st == "known_present" or st == "unknown":
                    blocked = True
                    break
            if not blocked:
                results.append(m["id"])
        elif scenario_key == "multiple_constraints":
            # Exclude shrimp, beef group, and primary_role not dessert
            shrimp_st = assessments.get("shrimp", {}).get("status")
            groups = set(m.get("ingredient_groups", []))
            if (shrimp_st not in ("known_present", "unknown")) and ("beef" not in groups) and (m.get("primary_role") != "dessert"):
                results.append(m["id"])
        elif scenario_key == "unsupported_allergen":
            # Unsupported allergen - cannot safely filter, returns empty or all
            results.append(m["id"])
        elif scenario_key == "combo_role_main":
            if "main_dish" in m.get("eligible_combo_roles", []):
                results.append(m["id"])
        elif scenario_key == "empty_pool":
            if m.get("primary_role") == "beverage" and "beef" in m.get("ingredient_groups", []):
                results.append(m["id"])
                
    return results


# Method C: In-Memory Inverted Index (Set operations)
def inverted_index_scenario(scenario_key: str, idx: InMemoryInvertedIndex) -> List[str]:
    if scenario_key == "healthy":
        return idx.filter_candidate_ids(included_roles=["main_dish", "soup", "vegetable", "staple", "standalone", "beverage", "snack"])
    elif scenario_key == "gout":
        return idx.filter_candidate_ids(excluded_ingredient_groups=["seafood", "beef"])
    elif scenario_key == "diabetes":
        return idx.filter_candidate_ids(included_roles=["main_dish", "soup", "vegetable", "staple"])
    elif scenario_key == "fatty_liver":
        return idx.filter_candidate_ids(excluded_cooking_methods=["deep_frying", "frying"])
    elif scenario_key == "shrimp_allergy":
        return idx.filter_candidate_ids(excluded_allergens=["shrimp"])
    elif scenario_key == "cow_milk_allergy":
        return idx.filter_candidate_ids(excluded_allergens=["cow_milk"])
    elif scenario_key == "multiple_allergens":
        return idx.filter_candidate_ids(excluded_allergens=["shrimp", "egg", "peanut", "cow_milk"])
    elif scenario_key == "multiple_constraints":
        return idx.filter_candidate_ids(
            included_roles=["main_dish", "soup", "vegetable", "staple"],
            excluded_allergens=["shrimp"],
            excluded_ingredient_groups=["beef"]
        )
    elif scenario_key == "unsupported_allergen":
        # Pass unsupported allergen -> returns candidates without claiming allergen filtering
        return idx.filter_candidate_ids(excluded_allergens=["tree_nuts"])
    elif scenario_key == "combo_role_main":
        return idx.filter_candidate_ids(included_roles=["main_dish"], use_combo_roles=True)
    elif scenario_key == "empty_pool":
        return idx.filter_candidate_ids(included_roles=["beverage"], excluded_ingredient_groups=["beverage"])


def run_benchmark():
    print("=" * 80)
    print("PHASE 2: IN-MEMORY INVERTED INDEX BENCHMARK SUITE")
    print(f"Catalog size: {len(catalog_2471)} recipes | Iterations: {NUM_ITERATIONS}")
    print("=" * 80)

    scenarios = [
        ("healthy", "1. Ăn lành mạnh (General Food)"),
        ("gout", "2. Gút (Gout: Purine/Seafood/Beef)"),
        ("diabetes", "3. Tiểu đường (Diabetes: Low sugar)"),
        ("fatty_liver", "4. Gan nhiễm mỡ (Fatty Liver: Low Fat/Fried)"),
        ("shrimp_allergy", "5. Dị ứng tôm (Shrimp Allergy)"),
        ("cow_milk_allergy", "6. Dị ứng sữa bò (Cow Milk Allergy)"),
        ("multiple_allergens", "7. Nhiều dị ứng (Shrimp+Egg+Peanut+Milk)"),
        ("multiple_constraints", "8. Nhiều ràng buộc (Combo+No Shrimp+No Beef)"),
        ("unsupported_allergen", "9. Unsupported Allergen (Tree Nuts)"),
        ("combo_role_main", "10. Lọc theo Combo Role (Main Dish)"),
        ("empty_pool", "11. Không có ứng viên (Empty Pool)"),
    ]

    # Pre-warm all methods
    for key, _ in scenarios:
        for _ in range(NUM_WARMUP):
            legacy_filter_scenario(key, catalog_2471)
            metadata_linear_scan_scenario(key, list(meta_map_2471.values()))
            inverted_index_scenario(key, index_inst)

    results_table = []

    print("\n--- PURE FILTERING BENCHMARK (ms) ---")
    header = f"{'Scenario':<38} | {'Method A (Legacy)':<16} | {'Method B (Meta Scan)':<18} | {'Method C (Index)':<15} | {'Speedup (A/C)':<12} | {'Count C':<8}"
    print(header)
    print("-" * len(header))

    scenario_summaries = {}

    for key, name in scenarios:
        # Benchmark Method A
        times_a = []
        for _ in range(NUM_ITERATIONS):
            t0 = time.perf_counter()
            res_a = legacy_filter_scenario(key, catalog_2471)
            times_a.append((time.perf_counter() - t0) * 1000.0)

        # Benchmark Method B
        meta_list = list(meta_map_2471.values())
        times_b = []
        for _ in range(NUM_ITERATIONS):
            t0 = time.perf_counter()
            res_b = metadata_linear_scan_scenario(key, meta_list)
            times_b.append((time.perf_counter() - t0) * 1000.0)

        # Benchmark Method C
        times_c = []
        for _ in range(NUM_ITERATIONS):
            t0 = time.perf_counter()
            res_c = inverted_index_scenario(key, index_inst)
            times_c.append((time.perf_counter() - t0) * 1000.0)

        mean_a, p95_a = statistics.mean(times_a), statistics.quantiles(times_a, n=20)[18]
        mean_b, p95_b = statistics.mean(times_b), statistics.quantiles(times_b, n=20)[18]
        mean_c, p50_c, p95_c, p99_c = (
            statistics.mean(times_c),
            statistics.median(times_c),
            statistics.quantiles(times_c, n=20)[18],
            statistics.quantiles(times_c, n=100)[98] if len(times_c) >= 100 else max(times_c)
        )
        speedup = mean_a / mean_c if mean_c > 0 else float("inf")

        print(f"{name:<38} | {mean_a:>6.2f} (P95:{p95_a:>5.2f}) | {mean_b:>6.2f} (P95:{p95_b:>5.2f})   | {mean_c:>6.3f} (P95:{p95_c:>5.3f}) | {speedup:>9.1f}x   | {len(res_c):<8}")

        scenario_summaries[key] = {
            "name": name,
            "mean_a": mean_a, "p95_a": p95_a,
            "mean_b": mean_b, "p95_b": p95_b,
            "mean_c": mean_c, "p50_c": p50_c, "p95_c": p95_c, "p99_c": p99_c,
            "speedup_a_c": speedup,
            "count_c": len(res_c),
            "count_b": len(res_b),
            "count_a": len(res_a),
        }

    # -------------------------------------------------------------------------
    # Full Retrieval & Hydration Benchmark (Hydrating full recipe objects)
    # -------------------------------------------------------------------------
    print("\n--- FULL RETRIEVAL + HYDRATION BENCHMARK (ms) ---")
    print(f"{'Scenario':<38} | {'Pure Index (ms)':<15} | {'Hydrated (ms)':<15} | {'Throughput (ops/s)':<18}")
    print("-" * 90)

    for key, name in scenarios[:6]:
        times_pure = []
        times_hydrated = []
        for _ in range(NUM_ITERATIONS):
            t0 = time.perf_counter()
            ids = inverted_index_scenario(key, index_inst)
            t1 = time.perf_counter()
            hydrated = [index_inst.get_recipe_by_id(rid) for rid in ids]
            t2 = time.perf_counter()
            times_pure.append((t1 - t0) * 1000.0)
            times_hydrated.append((t2 - t0) * 1000.0)

        mean_pure = statistics.mean(times_pure)
        mean_hyd = statistics.mean(times_hydrated)
        ops = 1000.0 / mean_hyd if mean_hyd > 0 else 0
        print(f"{name:<38} | {mean_pure:>13.3f}   | {mean_hyd:>13.3f}   | {ops:>16.1f}")

    # -------------------------------------------------------------------------
    # Concurrent Read Benchmark
    # -------------------------------------------------------------------------
    print("\n--- CONCURRENT READ BENCHMARK (In-Memory Inverted Index) ---")
    concurrency_levels = [20, 50, 100]
    total_queries_per_run = 1000

    for workers in concurrency_levels:
        queries = [scenarios[i % len(scenarios)][0] for i in range(total_queries_per_run)]
        latencies = []

        def worker_task(q_key):
            t0 = time.perf_counter()
            res = inverted_index_scenario(q_key, index_inst)
            lat = (time.perf_counter() - t0) * 1000.0
            return lat

        t_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            latencies = list(executor.map(worker_task, queries))
        total_time = time.perf_counter() - t_start

        c_mean = statistics.mean(latencies)
        c_p50 = statistics.median(latencies)
        c_p95 = statistics.quantiles(latencies, n=20)[18]
        c_p99 = statistics.quantiles(latencies, n=100)[98]
        tps = total_queries_per_run / total_time

        print(f"Workers: {workers:<3} | Total: {total_queries_per_run} reqs in {total_time:.3f}s | Mean: {c_mean:.3f}ms | P50: {c_p50:.3f}ms | P95: {c_p95:.3f}ms | P99: {c_p99:.3f}ms | Throughput: {tps:.1f} req/s")

    # -------------------------------------------------------------------------
    # Index Lifecycle & Memory Overhead
    # -------------------------------------------------------------------------
    stats = index_inst.get_index_statistics()
    print("\n--- INDEX METRICS & MEMORY STATS ---")
    print(f"  - Total Indexed Recipes: {stats['total_recipes']}")
    print(f"  - Index Build Duration: {stats['build_duration_ms']} ms")
    print(f"  - Deep Index Overhead: {stats['total_index_overhead_kb']} KB ({stats['total_index_overhead_bytes']} bytes)")
    print(f"  - Unique Ingredients: {stats['unique_ingredients_count']}")
    print(f"  - Unique Ingredient Groups: {stats['unique_ingredient_groups_count']}")
    print(f"  - Manual Review Items: {stats['manual_review_count']}")

if __name__ == "__main__":
    run_benchmark()
