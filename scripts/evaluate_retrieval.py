"""Offline, document-level paired retrieval benchmark. No answer generation.

Run: python scripts/evaluate_retrieval.py
"""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import statistics
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
DEFAULT_DATASET = ROOT / 'evaluation' / 'rag_eval_dataset.json'
DEFAULT_OUTPUT = ROOT / 'evaluation' / 'results' / 'rag_eval_latest.json'
KS = (1, 3, 5)


def metrics(ranking, relevant):
    """Binary relevance, unique document IDs; MRR within returned candidates."""
    relevant = set(relevant)
    if not relevant:
        raise ValueError('At least one relevant document is required')
    ranking = list(dict.fromkeys(ranking))
    result = {}
    for k in KS:
        found = len(set(ranking[:k]) & relevant)
        result[f'hit@{k}'] = float(found > 0)
        result[f'recall@{k}'] = found / len(relevant)
    result['mrr'] = next((1 / rank for rank, doc in enumerate(ranking, 1) if doc in relevant), 0.0)
    dcg = sum(1 / math.log2(rank + 1) for rank, doc in enumerate(ranking[:5], 1) if doc in relevant)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(5, len(relevant)) + 1))
    result['ndcg@5'] = dcg / ideal
    return result


def validate_dataset(cases, known):
    if not isinstance(cases, list) or not cases:
        raise ValueError('Dataset must be a non-empty list')
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('Each case must be an object')
        for field in ('id', 'query', 'category', 'language'):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f'Missing {field}')
        if case['id'] in ids:
            raise ValueError(f"Duplicate query id: {case['id']}")
        ids.add(case['id'])
        if case['language'] not in ('vi', 'en') or not isinstance(case.get('cross_language'), bool):
            raise ValueError(f"Invalid language metadata: {case['id']}")
        rel = case.get('relevant_documents')
        if not isinstance(rel, list) or not rel or any(not isinstance(x, str) or not x for x in rel) or len(set(rel)) != len(rel):
            raise ValueError(f"Invalid relevant documents: {case['id']}")
        missing = set(rel) - known
        if missing:
            raise ValueError(f"Unknown document(s) for {case['id']}: {sorted(missing)}")


def ranking(candidates):
    result, seen = [], set()
    for candidate in candidates:
        meta = candidate.get('metadata') or {}
        identity = meta.get('source_url')
        if not identity:
            raise ValueError('Retrieved chunk lacks stable metadata.source_url')
        if identity in seen:
            continue
        seen.add(identity)
        result.append({'id': identity, 'title': meta.get('title'), 'source_url': meta.get('source_url'),
                       'fusion_score': candidate.get('fusion_score'), 'rerank_score': candidate.get('rerank_score')})
    return result


def average(rows):
    if not rows:
        return {}
    return {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]}


def percentile(values, p):
    if not values:
        return None
    v = sorted(values)
    pos = (len(v) - 1) * p
    lower, upper = math.floor(pos), math.ceil(pos)
    return v[lower] + (v[upper] - v[lower]) * (pos - lower)


def summarize_latency(values):
    return {'mean_ms': statistics.mean(values), 'p50_ms': percentile(values, .5), 'p95_ms': percentile(values, .95)} if values else {}


def compare(cases, rag, reranker):
    per_query = []
    for idx, case in enumerate(cases, 1):
        start = time.perf_counter()
        candidates = rag.retrieve_candidates(case['query'], 20)
        baseline_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        reranked = reranker.rerank(case['query'], candidates, len(candidates)) if candidates else []
        rerank_ms = (time.perf_counter() - start) * 1000
        if len(reranked) != len(candidates) or any(not isinstance(c.get('rerank_score'), (int, float)) or not math.isfinite(c['rerank_score']) for c in reranked):
            raise RuntimeError(f"Reranker failed or returned fallback for {case['id']}; benchmark aborted")
        b, r = ranking(candidates), ranking(reranked)
        bm, rm = metrics([x['id'] for x in b], case['relevant_documents']), metrics([x['id'] for x in r], case['relevant_documents'])
        outcome = ('regression' if bm['hit@5'] > rm['hit@5'] else 'improvement' if rm['hit@5'] > bm['hit@5'] else 'both_hit' if bm['hit@5'] else 'both_miss')
        per_query.append({**case, 'reranker_applied': bool(candidates), 'baseline_ranking': b, 'reranker_ranking': r, 'baseline_metrics': bm, 'reranker_metrics': rm,
                          'outcome_at_5': outcome, 'latency_ms': {'baseline': baseline_ms, 'reranker_incremental': rerank_ms, 'reranked_total': baseline_ms + rerank_ms}})
        print(f"[{idx}/{len(cases)}] {case['id']} {outcome}", flush=True)
    return per_query


def build_report(cases, per_query, metadata):
    baseline = average([p['baseline_metrics'] for p in per_query])
    reranker = average([p['reranker_metrics'] for p in per_query])
    groups = {}
    for field in ('category', 'language', 'cross_language'):
        groups[field] = {}
        for value in sorted({str(c[field]) for c in cases}):
            selected = [p for p in per_query if str(p[field]) == value]
            groups[field][value] = {'count': len(selected), 'baseline': average([p['baseline_metrics'] for p in selected]), 'reranker': average([p['reranker_metrics'] for p in selected])}
    failures = {}
    for k in KS:
        failures[f'top_{k}'] = {}
        for outcome in ('regression', 'improvement', 'both_hit', 'both_miss'):
            def classification(row):
                b, r = row['baseline_metrics'][f'hit@{k}'], row['reranker_metrics'][f'hit@{k}']
                return 'regression' if b > r else 'improvement' if r > b else 'both_hit' if b else 'both_miss'
            failures[f'top_{k}'][outcome] = [p['id'] for p in per_query if classification(p) == outcome]
    applied = [p for p in per_query if p['reranker_applied']]
    return {'metadata': metadata, 'baseline': baseline, 'reranker': reranker,
            'delta': {k: reranker[k] - baseline[k] for k in baseline}, 'breakdown': groups,
            'failure_analysis': failures,
            'candidate_coverage': {'no_candidates': len(per_query) - len(applied),
                                   'relevant_not_in_candidate_pool': sum(p['baseline_metrics']['mrr'] == 0 for p in per_query)},
            'latency_ms': {**{key: summarize_latency([p['latency_ms'][key] for p in per_query]) for key in ('baseline', 'reranker_incremental', 'reranked_total')},
                           'reranker_incremental_when_applied': summarize_latency([p['latency_ms']['reranker_incremental'] for p in applied])}, 'per_query': per_query}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    from core.rag_service import medical_rag_service as rag
    from core.reranker_service import RerankerService, DEFAULT_MODEL
    if not rag.is_available():
        raise SystemExit('Medical corpus unavailable')
    corpus = rag.collection.get(include=['documents', 'metadatas'])
    rows = list(zip(corpus['documents'], corpus['metadatas']))
    if not rows or any(not isinstance(m, dict) or not m.get('source_url') for _, m in rows):
        raise SystemExit('Missing source metadata in active corpus')
    known = {m['source_url'] for _, m in rows}
    raw = args.dataset.read_bytes()
    cases = json.loads(raw.decode('utf-8-sig'))
    validate_dataset(cases, known)
    if rag.vector_search_enabled:
        # Fail clearly rather than silently measuring lexical fallback as hybrid.
        try:
            rag.collection.query(query_texts=['offline vector preflight'], n_results=1)
        except Exception as exc:
            raise SystemExit(f'Configured vector retrieval unavailable offline: {type(exc).__name__}') from exc
    class RetrievalFailureGuard(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if 'lookup unavailable' in msg:
                raise RuntimeError('Retrieval branch failed; benchmark aborted: ' + msg)
    guard = RetrievalFailureGuard()
    log = logging.getLogger('MedicalRAGService')
    log.addHandler(guard)
    try:
        runner = RerankerService(timeout_seconds=120)
        start = time.perf_counter()
        runner._load_model()
        cold_ms = (time.perf_counter() - start) * 1000
        warm = runner.rerank('general health information', [{'content': rows[0][0], 'rerank_score': None}], 1)
        if not warm or warm[0].get('rerank_score') is None:
            raise RuntimeError('Reranker warmup failed')
        per_query = compare(cases, rag, runner)
    finally:
        log.removeHandler(guard)
    fingerprint = hashlib.sha256()
    for doc, meta in sorted(rows, key=lambda x: (x[1]['file_name'], x[0])):
        fingerprint.update((meta['file_name'] + '\0' + doc + '\0').encode('utf-8'))
    metadata = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'query_count': len(cases), 'dataset_sha256': hashlib.sha256(raw).hexdigest(),
                'corpus_sha256': fingerprint.hexdigest(), 'corpus_chunks': len(rows), 'corpus_documents': len(known), 'model': DEFAULT_MODEL,
                'vector_enabled': rag.vector_search_enabled, 'candidate_chunks': 20, 'identity': 'metadata.source_url',
                'reranker_timeout_seconds': 120, 'model_load_ms': cold_ms,
                'notes': ['Synthetic corpus-grounded silver labels, not expert reviewed; judgments are incomplete.',
                          'Document-level metrics deduplicate chunks after retrieving 20 candidates; MRR is bounded by that candidate pool.',
                          'Configured retriever with existing query expansion; no Gemini. Warm inference timing excludes model loading.',
                          'Benchmark timeout differs from default online service timeout; this benchmark does not measure clinical safety or answer quality.']}
    report = build_report(cases, per_query, metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print('\nRAG RETRIEVAL EVALUATION\n========================')
    print(f'Queries: {len(cases)}; vector: {rag.vector_search_enabled}')
    print(f"{'Metric':<12}{'Baseline':>12}{'Reranker':>12}{'Delta':>12}")
    for key, value in report['baseline'].items():
        print(f"{key:<12}{value:>12.3f}{report['reranker'][key]:>12.3f}{report['delta'][key]:>+12.3f}")
    for field, groups in report['breakdown'].items():
        for name, group in groups.items():
            print(f"{field}={name} n={group['count']} recall@5: {group['baseline']['recall@5']:.3f} -> {group['reranker']['recall@5']:.3f}")
    print('Outcomes @5:', {k: len(v) for k, v in report['failure_analysis']['top_5'].items()})
    print('Latency ms:', report['latency_ms'])
    print('Report:', args.output)


if __name__ == '__main__':
    main()
