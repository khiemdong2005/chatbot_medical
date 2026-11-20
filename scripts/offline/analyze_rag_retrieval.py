"""Phase 1.4: offline, paired lexical/hybrid retrieval and missed-query diagnostics."""
import argparse
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', ANONYMIZED_TELEMETRY='False')
from scripts.evaluate_retrieval import metrics, ranking, average, summarize_latency, validate_dataset
from core.rag_service import medical_rag_service as rag, search_tokens, VIETNAMESE_TO_ENGLISH_KEYWORDS

DATASET = ROOT / 'evaluation/rag_eval_dataset.json'
PRIOR = ROOT / 'evaluation/results/rag_eval_latest.json'


def doc_rank(hits, relevant):
    return next((i for i, hit in enumerate(hits, 1) if (hit.get('metadata') or {}).get('source_url') in relevant), None)


def description(hits, limit=50):
    return [{'rank_chunk': i, 'title': (h.get('metadata') or {}).get('title'),
             'source_url': (h.get('metadata') or {}).get('source_url'),
             'distance': h.get('distance'), 'retrieval': h.get('retrieval')} for i, h in enumerate(hits[:limit], 1)]


def evaluate(cases, enable_vector):
    rag.vector_search_enabled = enable_vector
    result = []
    for case in cases:
        start = time.perf_counter()
        hits = rag.retrieve_candidates(case['query'], 20)
        elapsed = (time.perf_counter() - start) * 1000
        order = [x['id'] for x in ranking(hits)]
        rel = case['relevant_documents']
        result.append({'id': case['id'], 'query': case['query'], 'language': case['language'],
                       'category': case['category'], 'metrics': metrics(order, rel),
                       'candidate_recall_at_20': len(set(order) & set(rel)) / len(rel),
                       'candidate_count_chunks': len(hits), 'latency_ms': elapsed,
                       'candidates': hits})
    return result


def aggregate(rows):
    out = {'count': len(rows), 'metrics': average([x['metrics'] for x in rows]),
           'candidate_recall_at_20': sum(x['candidate_recall_at_20'] for x in rows) / len(rows),
           'latency_ms': summarize_latency([x['latency_ms'] for x in rows])}
    out['language'] = {lang: {'count': len(sub), 'metrics': average([x['metrics'] for x in sub]),
                               'candidate_recall_at_20': sum(x['candidate_recall_at_20'] for x in sub) / len(sub)}
                       for lang in ('vi','en') if (sub := [x for x in rows if x['language']==lang])}
    return out


def rerank(rows, cases):
    from core.reranker_service import RerankerService
    service = RerankerService(timeout_seconds=120)
    started = time.perf_counter()
    service._load_model()
    cold_ms = (time.perf_counter()-started)*1000
    first = next((x['candidates'] for x in rows if x['candidates']), [])
    warm = service.rerank('medical information', first[:1], 1)
    if not warm or warm[0].get('rerank_score') is None:
        raise RuntimeError('Reranker unavailable')
    labels = {c['id']: c['relevant_documents'] for c in cases}
    result = []
    for index, row in enumerate(rows, 1):
        start = time.perf_counter()
        hits = service.rerank(row['query'], row['candidates'], len(row['candidates'])) if row['candidates'] else []
        duration = (time.perf_counter() - start)*1000
        if len(hits) != len(row['candidates']) or any(not isinstance(x.get('rerank_score'),(int,float)) or not math.isfinite(x['rerank_score']) for x in hits):
            raise RuntimeError(f"Reranker fallback for {row['id']}")
        order = [x['id'] for x in ranking(hits)]
        result.append({**{k:v for k,v in row.items() if k!='candidates'},
                       'metrics':metrics(order, labels[row['id']]),
                       'latency_ms':row['latency_ms']+duration,
                       'rerank_incremental_ms': duration, 'rerank_applied': bool(hits),
                       'ranking':ranking(hits)})
        print(f'Rerank {index}/{len(rows)} {row["id"]}', flush=True)
    return result, cold_ms


class RetrievalFailureGuard(logging.Handler):
    def emit(self, record):
        if 'lookup unavailable' in record.getMessage():
            raise RuntimeError('Retrieval failed: '+record.getMessage())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rerank',action='store_true')
    parser.add_argument('--legacy-expansion',action='store_true', help='Reproduce Phase 1.3 accent-folded phrase matching in this process only')
    args=parser.parse_args()
    if args.legacy_expansion:
        def legacy_expand(query):
            folded = ' ' + ' '.join(search_tokens(query)) + ' '
            terms = []
            for vi, en in VIETNAMESE_TO_ENGLISH_KEYWORDS.items():
                if ' ' + ' '.join(search_tokens(vi)) + ' ' in folded and en not in terms:
                    terms.append(en)
            return query + ' ' + ' '.join(terms) if terms else query
        rag.expand_query = legacy_expand
    cases=json.loads(DATASET.read_text(encoding='utf8'))
    prior=json.loads(PRIOR.read_text(encoding='utf8'))
    raw=rag.collection.get(include=['documents','metadatas'])
    known={m['source_url'] for m in raw['metadatas']}
    validate_dataset(cases,known)
    digest=hashlib.sha256(DATASET.read_bytes()).hexdigest()
    if digest!=prior['metadata']['dataset_sha256']:
        raise RuntimeError('Dataset differs from Phase 1.3 benchmark')
    h=hashlib.sha256()
    for doc,m in sorted(zip(raw['documents'],raw['metadatas']),key=lambda x:(x[1]['file_name'],x[0])):
        h.update((m['file_name']+'\0'+doc+'\0').encode('utf8'))
    if h.hexdigest()!=prior['metadata']['corpus_sha256']:
        raise RuntimeError('Corpus differs from Phase 1.3 benchmark')
    # Chroma's default embedding can download its ONNX files lazily, bypassing
    # HF_HUB_OFFLINE. Require the local files before exercising the vector path.
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
    model_dir = Path(ONNXMiniLM_L6_V2.DOWNLOAD_PATH) / 'onnx'
    for name in ('model.onnx', 'tokenizer.json', 'config.json', 'tokenizer_config.json',
                 'special_tokens_map.json', 'vocab.txt'):
        if not (model_dir / name).is_file():
            raise RuntimeError(f'Offline Chroma embedding cache incomplete: {name}')
    rag.collection.query(query_texts=['offline vector availability'], n_results=1)
    guard=RetrievalFailureGuard(); log=logging.getLogger('MedicalRAGService'); log.addHandler(guard)
    try:
        baseline=evaluate(cases,False)
        hybrid=evaluate(cases,True)
        selected=[]
        old={x['id']:x for x in prior['per_query']}
        baseline_by_id={x['id']:x for x in baseline}
        docs=list(zip(raw['documents'],raw['metadatas']))
        for case in cases:
            previous=old[case['id']]
            if previous['baseline_metrics']['hit@5']:
                continue
            q=case['query']; expanded=rag.expand_query(q); relevant=set(case['relevant_documents'])
            # 150 chunks per branch is the diagnostic equivalent of the production 3x pool at limit 50.
            lex=rag.lexical_search(expanded,150)
            rag.vector_search_enabled=True
            vector=rag.vector_search(expanded,150)
            merged=rag.merge_results(lex,vector,50)
            vraw=rag.collection.query(query_texts=[expanded],n_results=150)
            raw_vec=[{'metadata':m,'distance':d} for m,d in zip(vraw['metadatas'][0],vraw['distances'][0])]
            relevant_docs=[(d,m) for d,m in docs if m.get('source_url') in relevant]
            tokens=search_tokens(expanded)
            expected_overlap=max((len(set(tokens) & set(search_tokens(m.get('title','')+' '+d))) for d,m in relevant_docs), default=0)
            # Mirror the current BM25 term filter to distinguish missing terms
            # from the two-distinct-term requirement, without claiming clinical causality.
            _, _, _, df, _ = rag._lexical_index
            stop = {'va','co','la','cua','toi','bi','nay','thi','cho','xin','hoi','gi',
                    'khong','voi','ve','nhu','nao','the','and','of','in','to','with','is'}
            terms = {t for t in tokens if t not in stop and len(t)>1 and 0<df[t]<=max(1,len(docs)*.4)}
            eligible_overlap=max((len(terms & set(search_tokens(m.get('title','')+' '+d))) for d,m in relevant_docs),default=0)
            required_overlap=min(2,len(terms))
            english_added=expanded != q
            lex_rank=doc_rank(lex,relevant); raw_vec_rank=doc_rank(raw_vec,relevant)
            codes=['VECTOR_DISABLED_IN_BASELINE']
            if relevant_docs and case['language']=='vi' and not english_added:
                codes.append('NO_CROSS_LANGUAGE_EXPANSION')
            if not eligible_overlap:
                codes.append('NO_ELIGIBLE_LEXICAL_OVERLAP')
            elif eligible_overlap < required_overlap:
                codes.append('ELIGIBLE_OVERLAP_BELOW_BM25_MINIMUM')
            if lex_rank is None:
                codes.append('BM25_NO_EXPECTED_IN_TOP_150')
            elif lex_rank>20:
                codes.append('BM25_EXPECTED_BEYOND_TOP_20_CHUNKS')
            if raw_vec_rank is None:
                codes.append('VECTOR_NO_EXPECTED_IN_TOP_150_RAW')
            elif doc_rank(vector,relevant) is None:
                codes.append('VECTOR_THRESHOLD_FILTERED_EXPECTED')
            selected.append({'id':case['id'],'query':q,'language':case['language'],
                             'expected_documents':[{'source_url':u,'titles':sorted({m.get('title','') for d,m in relevant_docs if m.get('source_url')==u})} for u in case['relevant_documents']],
                             'expanded_query':expanded,'english_terms_added':english_added,'query_tokens':tokens,
                             'expected_max_token_overlap_all_tokens':expected_overlap,
                             'bm25_eligible_query_terms':sorted(terms),'expected_max_eligible_term_overlap':eligible_overlap,
                             'bm25_required_term_overlap':required_overlap,
                             'reason_codes':codes,
                             'baseline_vector':'disabled', 'baseline_merged_top20':description([{'metadata':{'title':x['title'],'source_url':x['source_url']},'retrieval':'bm25'} for x in previous['baseline_ranking']],20),
                             'bm25_top50_chunks':description(lex), 'hybrid_vector_top50_accepted_chunks':description(vector),
                             'hybrid_merged_top50_chunks_diagnostic':description(merged),
                             'bm25_count_within_150':len(lex), 'vector_count_accepted_within_150':len(vector),
                             'bm25_expected_rank_within_150_chunks':lex_rank,'vector_expected_rank_within_150_raw_chunks':raw_vec_rank,
                             'vector_expected_rank_accepted_within_150_chunks':doc_rank(vector,relevant),
                             'hybrid_expected_rank_within_top50_chunks_diagnostic':doc_rank(merged,relevant),
                             'baseline_candidate_count_chunks':baseline_by_id[case['id']]['candidate_count_chunks'],
                             'baseline_candidate_count_unique_sources':len(previous['baseline_ranking'])})
        report={'metadata':{'dataset_sha256':digest,'corpus_sha256':h.hexdigest(), 'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                            'vector_model':'Chroma default all-MiniLM-L6-v2 (existing collection configuration)',
                            'phrase_matching':'legacy accent-folded' if args.legacy_expansion else 'accent-aware with accent-free fallback',
                            'vector_distance_threshold':rag.acceptance_threshold,
                            'diagnostic_note':'Top 50 is a separate 150-chunk-per-branch experiment, not production retrieve_candidates (clamped to 20).',
                            'benchmark_note':'Exploratory evaluation on the same development set; not an unbiased test or clinical validation.'},
                'baseline':aggregate(baseline),'hybrid':aggregate(hybrid),
                'per_query':[{'baseline':{k:v for k,v in b.items() if k!='candidates'},'hybrid':{k:v for k,v in a.items() if k!='candidates'}} for b,a in zip(baseline,hybrid)],
                'failures_phase13':selected,
                'reason_counts':dict(Counter(code for row in selected for code in row['reason_codes'])),
                'regressions_hybrid_top5':[b['id'] for b,a in zip(baseline,hybrid) if a['metrics']['hit@5']<b['metrics']['hit@5']],
                'improvements_hybrid_top5':[b['id'] for b,a in zip(baseline,hybrid) if a['metrics']['hit@5']>b['metrics']['hit@5']]}
        if args.rerank:
            ranked,cold=rerank(hybrid,cases)
            report['hybrid_reranker']=aggregate(ranked)
            report['hybrid_reranker_model_load_ms']=cold
            report['hybrid_reranker_per_query']=ranked
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
        print('OUTPUT',args.output)
        for key in ('baseline','hybrid','hybrid_reranker'):
            if key in report: print(key,json.dumps(report[key],ensure_ascii=False))
        print('REASONS',report['reason_counts'])
        print('REGRESSIONS', report['regressions_hybrid_top5'])
        print('IMPROVEMENTS', report['improvements_hybrid_top5'])
    finally:
        rag.vector_search_enabled=False
        log.removeHandler(guard)

if __name__=='__main__': main()
