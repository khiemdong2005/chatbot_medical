"""Microbenchmark Suite for Phase 3.1: Clinical Constraint Engine.

Measures:
- Resolution latency (Constraint compilation)
- Indexed filtering latency
- Residual safety validation latency
- Total clinical processing latency (Mean, P50, P95, P99)
- Candidate pool counts & ID correctness
- Concurrent throughput and execution across 20, 50, 100 threads
"""

import concurrent.futures
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.nutrition.clinical_constraints import CandidatePools, ResolvedConstraints, SafetyStatus
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index

NUM_WARMUP = 15
NUM_ITERATIONS = 120

idx = get_metadata_index()

SCENARIOS = [
    ("healthy", "1. Ăn lành mạnh (Healthy Eating)", {"profile": {}, "query": "ăn lành mạnh"}),
    ("single_condition", "2. Bệnh lý đơn (Gút - Gout)", {"profile": {"conditions": ["gout"]}, "query": "bệnh gút"}),
    ("single_allergy", "3. Dị ứng đơn (Dị ứng tôm - Shrimp)", {"profile": {"allergies": ["shrimp"]}, "query": "dị ứng tôm"}),
    ("multiple_allergens", "4. Nhiều dị ứng (Tôm + Trứng + Sữa bò)", {"profile": {"allergies": ["shrimp", "egg", "cow_milk"]}, "query": "dị ứng tôm và trứng"}),
    ("multiple_conditions", "5. Nhiều bệnh lý (Gút + Tiểu đường)", {"profile": {"conditions": ["gout", "diabetes"]}, "query": "gút và tiểu đường"}),
    ("condition_allergy_pref", "6. Đa ràng buộc (Tiểu đường + Dị ứng tôm + Không chiên)", {"profile": {"conditions": ["diabetes"], "allergies": ["shrimp"]}, "query": "tiểu đường, dị ứng tôm, không ăn đồ chiên"}),
    ("unsupported_allergy", "7. Dị ứng chưa hỗ trợ (Hạt cây - Tree Nuts)", {"profile": {"allergies": ["tree_nuts"]}, "query": "dị ứng hạt điều và óc chó"}),
    ("missing_metadata", "8. Xử lý thiếu metadata (Lọc fail-closed)", {"profile": {"allergies": ["wheat_gluten"]}, "query": "kiêng gluten"}),
    ("empty_pool", "9. Tập rỗng (Mâu thuẫn không thể đáp ứng)", {"profile": {"disliked_ingredients": ["tat ca cac mon"]}, "query": "không ăn bất kỳ món nào"}),
]


def run_benchmark():
    print("=" * 95)
    print("PHASE 3.1: CLINICAL CONSTRAINT ENGINE BENCHMARK SUITE")
    print(f"Iterations per scenario: {NUM_ITERATIONS} | Warm-up: {NUM_WARMUP}")
    print("=" * 95)

    # Warm-up run
    for _, _, config in SCENARIOS:
        for _ in range(NUM_WARMUP):
            r = ConstraintResolver.resolve_constraints(profile=config["profile"], condition_query=config["query"])
            ConstraintFilter.filter_candidates(r, index=idx)

    # Scenario latency benchmark
    header = (
        f"{'Scenario':<42} | {'Resolve (ms)':<12} | {'Index (ms)':<10} | {'Residual (ms)':<13} | "
        f"{'Total Mean (ms)':<15} | {'P95 (ms)':<9} | {'Surviving':<9} | {'Status':<12}"
    )
    print(header)
    print("-" * len(header))

    scenario_metrics = {}

    for key, name, config in SCENARIOS:
        resolve_times = []
        index_times = []
        residual_times = []
        total_times = []
        last_pools = None

        for _ in range(NUM_ITERATIONS):
            t0 = time.perf_counter()
            r = ConstraintResolver.resolve_constraints(profile=config["profile"], condition_query=config["query"])
            t1 = time.perf_counter()
            pools = ConstraintFilter.filter_candidates(r, index=idx)
            t2 = time.perf_counter()

            resolve_times.append((t1 - t0) * 1000.0)
            total_times.append((t2 - t0) * 1000.0)
            index_times.append(pools.execution_metrics.get("indexed_filtering_ms", 0.0))
            residual_times.append(pools.execution_metrics.get("residual_validation_ms", 0.0))
            last_pools = pools

        mean_res = statistics.mean(resolve_times)
        mean_idx = statistics.mean(index_times)
        mean_res_chk = statistics.mean(residual_times)
        mean_tot = statistics.mean(total_times)
        p50_tot = statistics.median(total_times)
        p95_tot = statistics.quantiles(total_times, n=20)[18]
        p99_tot = statistics.quantiles(total_times, n=100)[98] if len(total_times) >= 100 else max(total_times)

        surviving = last_pools.execution_metrics.get("surviving_count", 0)

        print(
            f"{name:<42} | {mean_res:>10.3f}   | {mean_idx:>8.3f} | {mean_res_chk:>11.3f}   | "
            f"{mean_tot:>13.3f}   | {p95_tot:>7.3f} | {surviving:<9} | {last_pools.safety_status:<12}"
        )

        scenario_metrics[key] = {
            "name": name,
            "mean_resolve": mean_res,
            "mean_index": mean_idx,
            "mean_residual": mean_res_chk,
            "mean_total": mean_tot,
            "p50_total": p50_tot,
            "p95_total": p95_tot,
            "p99_total": p99_tot,
            "surviving": surviving,
            "status": last_pools.safety_status
        }

    # -------------------------------------------------------------------------
    # Concurrent Execution Benchmark (20, 50, 100 concurrent workers)
    # -------------------------------------------------------------------------
    print("\n--- CONCURRENT CLINICAL PROCESSING BENCHMARK ---")
    concurrency_levels = [20, 50, 100]
    total_requests = 1000

    for workers in concurrency_levels:
        requests = [SCENARIOS[i % len(SCENARIOS)][2] for i in range(total_requests)]
        latencies = []

        def worker_task(cfg):
            t0 = time.perf_counter()
            r = ConstraintResolver.resolve_constraints(profile=cfg["profile"], condition_query=cfg["query"])
            pools = ConstraintFilter.filter_candidates(r, index=idx)
            return (time.perf_counter() - t0) * 1000.0

        t_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            latencies = list(executor.map(worker_task, requests))
        total_time = time.perf_counter() - t_start

        c_mean = statistics.mean(latencies)
        c_p50 = statistics.median(latencies)
        c_p95 = statistics.quantiles(latencies, n=20)[18]
        c_p99 = statistics.quantiles(latencies, n=100)[98]
        tps = total_requests / total_time

        print(
            f"Workers: {workers:<3} | Total: {total_requests} reqs in {total_time:.3f}s | "
            f"Mean: {c_mean:.3f}ms | P50: {c_p50:.3f}ms | P95: {c_p95:.3f}ms | P99: {c_p99:.3f}ms | "
            f"Throughput: {tps:.1f} req/s"
        )


if __name__ == "__main__":
    run_benchmark()
