"""Microbenchmark Suite for Phase 4: Content-Based Scoring & Candidate Ranking.

Measures:
- Feature extraction latency
- Scoring latency
- Sorting & Top-K latency
- Total Phase 4 ranking latency (Mean, P50, P95, P99)
- End-to-End latency: Phase 3 (Constraint Filtering) + Phase 4 (Scoring & Ranking)
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

from core.nutrition.candidate_ranker import CandidateRanker, ScoringConfig
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index

idx = get_metadata_index()
ranker = CandidateRanker(index=idx)

NUM_WARMUP = 15
NUM_ITERATIONS = 120

BENCHMARK_SCENARIOS = [
    ("1. Healthy Eating", {"profile": {}, "query": "ăn lành mạnh"}),
    ("2. Bệnh gút (Gout)", {"profile": {"conditions": ["gout"]}, "query": "bệnh gút"}),
    ("3. Tiểu đường (Diabetes)", {"profile": {"conditions": ["diabetes"]}, "query": "đái tháo đường type 2"}),
    ("4. Gan nhiễm mỡ (Fatty Liver)", {"profile": {"conditions": ["fatty_liver"]}, "query": "gan nhiễm mỡ, không ăn đồ chiên"}),
    ("5. Dị ứng tôm (Shrimp)", {"profile": {"allergies": ["shrimp"]}, "query": "dị ứng tôm"}),
    ("6. Đa ràng buộc (TĐ + Tôm + Không chiên)", {"profile": {"conditions": ["diabetes"], "allergies": ["shrimp"]}, "query": "tiểu đường, dị ứng tôm, không ăn đồ chiên"}),
    ("7. Sở thích cá nhân (Thích gà, hấp)", {"profile": {"preferences": ["thit ga", "steaming"]}, "query": "muốn ăn thịt gà, đồ hấp"}),
    ("8. Dị ứng chưa hỗ trợ (Tree Nuts)", {"profile": {"allergies": ["tree_nuts"]}, "query": "dị ứng hạt điều và óc chó"}),
    ("9. Tập rỗng (Impossible)", {"profile": {"disliked_ingredients": ["tat ca cac mon"]}, "query": "không ăn bất kỳ món nào"}),
]


def run_benchmark():
    print("=" * 115)
    print("PHASE 4: CONTENT-BASED SCORING & CANDIDATE RANKING BENCHMARK")
    print(f"Iterations per scenario: {NUM_ITERATIONS} | Warm-up: {NUM_WARMUP}")
    print("=" * 115)

    # Warm-up run
    for _, config in BENCHMARK_SCENARIOS:
        for _ in range(NUM_WARMUP):
            r = ConstraintResolver.resolve_constraints(profile=config["profile"], condition_query=config["query"])
            pools = ConstraintFilter.filter_candidates(r, index=idx)
            ranker.rank_candidates(pools, resolved=r)

    # -------------------------------------------------------------------------
    # 1. Latency Breakdown Benchmark
    # -------------------------------------------------------------------------
    header = (
        f"{'Scenario':<40} | {'Candidates':<10} | {'Ranked':<6} | "
        f"{'Score (ms)':<10} | {'Rank P95 (ms)':<12} | {'E2E Mean (ms)':<12} | {'E2E P95 (ms)':<11}"
    )
    print(header)
    print("-" * len(header))

    scenario_metrics = {}

    for name, config in BENCHMARK_SCENARIOS:
        fe_times = []
        score_times = []
        sort_times = []
        rank_times = []
        e2e_times = []
        last_ranked = None

        for _ in range(NUM_ITERATIONS):
            t_e2e_start = time.perf_counter()
            r = ConstraintResolver.resolve_constraints(profile=config["profile"], condition_query=config["query"])
            pools = ConstraintFilter.filter_candidates(r, index=idx)

            t_rank_start = time.perf_counter()
            ranked = ranker.rank_candidates(pools, resolved=r)
            t_rank_end = time.perf_counter()
            t_e2e_end = time.perf_counter()

            rank_times.append((t_rank_end - t_rank_start) * 1000.0)
            e2e_times.append((t_e2e_end - t_e2e_start) * 1000.0)
            fe_times.append(ranked.execution_metrics.get("feature_extraction_ms", 0.0))
            score_times.append(ranked.execution_metrics.get("scoring_ms", 0.0))
            sort_times.append(ranked.execution_metrics.get("sorting_ms", 0.0))
            last_ranked = ranked

        cands = last_ranked.execution_metrics.get("total_candidates_evaluated", 0)
        tot_ranked = last_ranked.total_ranked_count
        mean_score = statistics.mean(score_times)
        p95_rank = statistics.quantiles(rank_times, n=20)[18] if len(rank_times) >= 20 else max(rank_times)
        mean_e2e = statistics.mean(e2e_times)
        p95_e2e = statistics.quantiles(e2e_times, n=20)[18] if len(e2e_times) >= 20 else max(e2e_times)

        print(
            f"{name:<40} | {cands:>10} | {tot_ranked:>6} | "
            f"{mean_score:>10.3f} | {p95_rank:>12.3f} | {mean_e2e:>12.3f} | {p95_e2e:>11.3f}"
        )

        scenario_metrics[name] = {
            "candidates": cands,
            "ranked": tot_ranked,
            "p95_rank": p95_rank,
            "mean_e2e": mean_e2e,
            "p95_e2e": p95_e2e,
        }

    # -------------------------------------------------------------------------
    # 2. Concurrent Processing Benchmark (20, 50, 100 workers)
    # -------------------------------------------------------------------------
    print("\n--- CONCURRENT PHASE 3 + PHASE 4 END-TO-END THROUGHPUT ---")
    concurrency_levels = [20, 50, 100]
    total_requests = 1000

    for workers in concurrency_levels:
        requests = [BENCHMARK_SCENARIOS[i % len(BENCHMARK_SCENARIOS)][1] for i in range(total_requests)]
        latencies = []

        def worker_task(cfg):
            t0 = time.perf_counter()
            r = ConstraintResolver.resolve_constraints(profile=cfg["profile"], condition_query=cfg["query"])
            p = ConstraintFilter.filter_candidates(r, index=idx)
            ranker.rank_candidates(p, resolved=r)
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
