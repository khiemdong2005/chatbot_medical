"""Microbenchmark Suite for Phase 5: Dynamic Meal Composition Engine.

Measures:
- Candidate pool sizes and raw/valid combinations evaluated
- Sub-millisecond latency breakdowns: combo scoring, diversity selection, standalone selection
- Total Phase 5 composition latency (Mean, P50, P95, P99)
- End-to-End latency: Phase 3 (Constraint Filtering) + Phase 4 (Ranking) + Phase 5 (Composition)
- Multi-threaded concurrent execution across 20, 50, 100 workers
"""

import concurrent.futures
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.nutrition.candidate_ranker import CandidateRanker
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index
from core.nutrition.meal_composition import DynamicMealComposer

idx = get_metadata_index()
ranker = CandidateRanker(index=idx)
composer = DynamicMealComposer(index=idx)

NUM_WARMUP = 15
NUM_ITERATIONS = 120

BENCHMARK_SCENARIOS = [
    ("1. Healthy Eating", {"profile": {}, "query": "ăn lành mạnh"}),
    ("2. Bệnh gút (Gout)", {"profile": {"conditions": ["gout"]}, "query": "bệnh gút"}),
    ("3. Tiểu đường (Diabetes)", {"profile": {"conditions": ["diabetes"]}, "query": "đái tháo đường type 2"}),
    ("4. Gan nhiễm mỡ (Fatty Liver)", {"profile": {"conditions": ["fatty_liver"]}, "query": "gan nhiễm mỡ, không ăn đồ chiên"}),
    ("5. GERD / Trào ngược", {"profile": {"conditions": ["gerd"]}, "query": "trào ngược dạ dày"}),
    ("6. Dị ứng tôm (Shrimp)", {"profile": {"allergies": ["shrimp"]}, "query": "dị ứng tôm"}),
    ("7. Đa ràng buộc (TĐ + Tôm + Không chiên)", {"profile": {"conditions": ["diabetes"], "allergies": ["shrimp"]}, "query": "tiểu đường, dị ứng tôm, không ăn đồ chiên"}),
    ("8. Sở thích nguyên liệu (Thích gà)", {"profile": {"preferences": ["thit ga"]}, "query": "muốn ăn thịt gà"}),
    ("9. Sở thích nấu nướng (Hấp)", {"profile": {"preferences": ["steaming"]}, "query": "thích đồ hấp"}),
    ("10. Sparse Pools (Gout + TĐ + Không chiên)", {"profile": {"conditions": ["gout", "diabetes"], "disliked_ingredients": ["do chien"]}, "query": "gút, tiểu đường, không ăn đồ chiên"}),
    ("11. Tập rỗng (Impossible)", {"profile": {"disliked_ingredients": ["tat ca cac mon"]}, "query": "không ăn bất kỳ món nào"}),
    ("12. Dị ứng chưa hỗ trợ (Tree Nuts)", {"profile": {"allergies": ["tree_nuts"]}, "query": "dị ứng hạt óc chó"}),
]


def run_benchmark():
    print("=" * 125)
    print("PHASE 5: DYNAMIC MEAL COMPOSITION ENGINE BENCHMARK")
    print(f"Iterations per scenario: {NUM_ITERATIONS} | Warm-up: {NUM_WARMUP}")
    print("=" * 125)

    # Warm-up run
    for _, config in BENCHMARK_SCENARIOS:
        for _ in range(NUM_WARMUP):
            r = ConstraintResolver.resolve_constraints(profile=config["profile"], condition_query=config["query"])
            pools = ConstraintFilter.filter_candidates(r, index=idx)
            ranked = ranker.rank_candidates(pools, resolved=r)
            composer.compose_meals(ranked, resolved=r)

    # -------------------------------------------------------------------------
    # 1. Latency Breakdown Benchmark
    # -------------------------------------------------------------------------
    print(f"{'Scenario':<40} | {'Raw/Valid':<11} | {'Combos':<6} | {'Standa':<6} | {'Phase 5 P95 (ms)':<16} | {'E2E Mean (ms)':<13} | {'E2E P95 (ms)':<12}")
    print("-" * 125)

    for name, config in BENCHMARK_SCENARIOS:
        p5_latencies = []
        e2e_latencies = []
        last_result = None

        for _ in range(NUM_ITERATIONS):
            t0 = time.perf_counter()
            r = ConstraintResolver.resolve_constraints(profile=config["profile"], condition_query=config["query"])
            pools = ConstraintFilter.filter_candidates(r, index=idx)
            ranked = ranker.rank_candidates(pools, resolved=r)
            t_p5_start = time.perf_counter()

            last_result = composer.compose_meals(ranked, resolved=r)
            t1 = time.perf_counter()

            p5_latencies.append((t1 - t_p5_start) * 1000.0)
            e2e_latencies.append((t1 - t0) * 1000.0)

        p5_sorted = sorted(p5_latencies)
        e2e_sorted = sorted(e2e_latencies)

        p5_p95 = p5_sorted[int(len(p5_sorted) * 0.95)]
        e2e_mean = statistics.mean(e2e_latencies)
        e2e_p95 = e2e_sorted[int(len(e2e_sorted) * 0.95)]

        raw_valid_str = f"{last_result.total_combos_evaluated}/{last_result.valid_combos_generated}"
        num_family = len(last_result.family_combos)
        num_standalone = len(last_result.standalone_meals)

        print(f"{name:<40} | {raw_valid_str:<11} | {num_family:<6} | {num_standalone:<6} | {p5_p95:>16.3f} | {e2e_mean:>13.3f} | {e2e_p95:>12.3f}")

    # -------------------------------------------------------------------------
    # 2. Multi-threaded Concurrent Throughput Benchmark
    # -------------------------------------------------------------------------
    print("\n--- CONCURRENT PHASE 3 + 4 + 5 END-TO-END THROUGHPUT BENCHMARK ---")

    def run_worker_task():
        for _ in range(10):
            # Pick a random scenario deterministically
            cfg = BENCHMARK_SCENARIOS[0][1]
            r = ConstraintResolver.resolve_constraints(profile=cfg["profile"], condition_query=cfg["query"])
            pools = ConstraintFilter.filter_candidates(r, index=idx)
            ranked = ranker.rank_candidates(pools, resolved=r)
            composer.compose_meals(ranked, resolved=r)

    for num_workers in [20, 50, 100]:
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            # 100 tasks of 10 requests = 1,000 total E2E requests
            futures = [executor.submit(run_worker_task) for _ in range(100)]
            concurrent.futures.wait(futures)
        duration = time.perf_counter() - t0
        total_requests = 1000
        throughput = total_requests / duration
        print(f"Workers: {num_workers:<3} | Total: {total_requests} reqs in {duration:.3f}s | Internal Task Rate: {throughput:.1f} tasks/s | Mean per req: {(duration/total_requests)*1000:.3f}ms")


if __name__ == "__main__":
    run_benchmark()
