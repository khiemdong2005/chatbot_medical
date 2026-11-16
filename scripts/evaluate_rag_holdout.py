"""One-shot frozen evaluation of BM25 versus cached cross-language expansion."""
import hashlib,json,logging,os,sys,time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',ANONYMIZED_TELEMETRY='False')
from scripts.evaluate_retrieval import metrics,ranking,average,summarize_latency
from scripts.experimental_cross_language import retrieve_with_translation
from scripts.query_expansion_experiment import keywords
from scripts.validate_rag_test_set import validate


def file_hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(rows):
    def group(items):
        return {'count':len(items),'metrics':average([x['metrics'] for x in items]),
                'candidate_recall_at_20':sum(x['candidate_recall_at_20'] for x in items)/len(items),
                'cached_retrieval_latency_ms':summarize_latency([x['retrieval_latency_ms'] for x in items])}
    result={'overall':group(rows)}
    for key in ('language','cross_language','category','difficulty'):
        result[key]={str(value):group([x for x in rows if x[key]==value]) for value in sorted(set(x[key] for x in rows))}
    return result


def main():
    from core.rag_service import medical_rag_service as rag
    cfg_path=ROOT/'evaluation/rag_phase16_frozen_config.json'
    result_path=ROOT/'evaluation/results/rag_phase16_holdout.json'
    marker=ROOT/'evaluation/results/rag_phase16_attempt.json'
    if result_path.exists() or marker.exists():raise SystemExit('One-shot guard: a Phase 1.6 attempt already exists; refusing to rerun')
    config=json.loads(cfg_path.read_text(encoding='utf8'))
    for name,digest in config['files_sha256'].items():
        if file_hash(ROOT/name)!=digest:raise SystemExit('Frozen file changed: '+name)
    corpus=rag.collection.get(include=['documents','metadatas']);rows=list(zip(corpus['documents'],corpus['metadatas']))
    h=hashlib.sha256()
    for doc,meta in sorted(rows,key=lambda x:(x[1]['file_name'],x[0])):h.update((meta['file_name']+'\0'+doc+'\0').encode('utf8'))
    if h.hexdigest()!=config['corpus_sha256']:raise SystemExit('Corpus does not match frozen version')
    dev=json.loads((ROOT/'evaluation/rag_dev_dataset.json').read_text(encoding='utf8'))
    cases=json.loads((ROOT/'evaluation/rag_test_dataset.json').read_text(encoding='utf8'))
    validation=validate(dev,cases,{m['source_url'] for _,m in rows})
    if validation['errors']:raise SystemExit('Dataset validation failed')
    cache_path=ROOT/'evaluation/cache/cross_language_test_queries.json'
    timings_path=ROOT/'evaluation/results/phase16_expansion_timings.json'
    cache={x['query']:x for x in json.loads(cache_path.read_text(encoding='utf8'))}
    times=json.loads(timings_path.read_text(encoding='utf8'))
    if any(set(x)!={'query','expanded_query','method'} for x in cache.values()):raise SystemExit('Invalid query-only cache')
    if any(x['method']!=config['query_expansion_method'] for x in cache.values()):raise SystemExit('Unexpected expansion provider')
    marker.parent.mkdir(parents=True,exist_ok=True)
    with marker.open('x',encoding='utf8') as f:
        json.dump({'started_utc':datetime.now(timezone.utc).isoformat(),'frozen_config_sha256':file_hash(cfg_path),
                   'translation_cache_sha256':file_hash(cache_path),'status':'started'},f,indent=2)
    class Guard(logging.Handler):
        def emit(self,record):
            if 'lookup unavailable' in record.getMessage():raise RuntimeError('Retrieval failed; refusing to report fallback as measured retrieval')
    logger=logging.getLogger('MedicalRAGService');guard=Guard();logger.addHandler(guard)
    rag.vector_search_enabled=False
    results={'baseline':[],'expansion':[]}
    try:
        for case in cases:
            q=case['query'];cached=cache.get(q) if case['language']=='vi' else None
            try: expanded=keywords(cached['expanded_query']) if cached else ''
            except (ValueError,KeyError,TypeError):expanded=''
            for mode in ('baseline','expansion'):
                t=time.perf_counter()
                # No relevance labels are passed to either retrieval branch.
                hits=retrieve_with_translation(rag,q,expanded,20) if mode=='expansion' and expanded else rag.retrieve_candidates(q,20)
                latency=(time.perf_counter()-t)*1000
                order=ranking(hits)
                for item in order:
                    branch=set()
                    for hit in hits:
                        if (hit.get('metadata') or {}).get('source_url')==item['id']:
                            branch.update(hit.get('branches') or (['original'] if hit.get('lexical_score') is not None else []))
                    item['branches']=sorted(branch)
                labels=case['relevant_documents'];ids=[x['id'] for x in order]
                results[mode].append({'id':case['id'],'query':q,'language':case['language'],'cross_language':case['cross_language'],
                                      'category':case['category'],'difficulty':case['difficulty'],'relevant_documents':labels,
                                      'expanded_query':expanded if mode=='expansion' else '',
                                      'expansion_status':('cached' if expanded else 'fallback') if case['language']=='vi' and mode=='expansion' else 'not_applicable',
                                      'ranking':order,'metrics':metrics(ids,labels),
                                      'candidate_recall_at_20':len(set(ids)&set(labels))/len(labels),'retrieval_latency_ms':latency})
    finally:logger.removeHandler(guard)
    old={x['id']:x for x in results['baseline']};new={x['id']:x for x in results['expansion']}
    changes={}
    for k in (1,3,5):
        changes[f'top{k}']={'improved':[i for i in old if new[i]['metrics'][f'hit@{k}']>old[i]['metrics'][f'hit@{k}']],
                            'regressed':[i for i in old if new[i]['metrics'][f'hit@{k}']<old[i]['metrics'][f'hit@{k}']]}
    failures=[]
    for case in cases:
        x=new[case['id']]
        if x['metrics']['recall@5']<1:
            failures.append({'id':x['id'],'query':x['query'],'expanded_query':x['expanded_query'],'expected_sources':x['relevant_documents'],
                             'retrieved_top5':x['ranking'][:5],
                             'reason_codes':['EXPANSION_UNAVAILABLE' if x['language']=='vi' and not x['expanded_query'] else 'UNKNOWN_REQUIRES_REVIEW']})
    report={'metadata':{'status':'one_shot_completed','timestamp_utc':datetime.now(timezone.utc).isoformat(),
             'frozen_config_sha256':file_hash(cfg_path),'cache_sha256':file_hash(cache_path),'corpus_sha256':h.hexdigest(),
             'notes':['Draft labels and queries were authored by the same assistant familiar with dev results; not independently expert reviewed.',
                      'Separate questions do not guarantee author or semantic independence, or complete relevance labels.',
                      'Unofficial provider version may change; cached translations are frozen for this run.',
                      'No clinical validation; result is provisional and not unbiased final performance.']},
            'validation':validation,'configurations':{name:summary(r) for name,r in results.items()},
            'changes_vs_baseline':changes,'failure_analysis':failures,
            'expansion_generation':{'attempts':len(times),'status_counts':dict(Counter(x['status'] for x in times)),
                                    'latency_ms':summarize_latency([x['latency_ms'] for x in times])},
            'per_query':results}
    with result_path.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print('One-shot result written:',result_path)
    for name,s in report['configurations'].items():
        print(name,'VI R@5',s['language']['vi']['metrics']['recall@5'],'EN R@5',s['language']['en']['metrics']['recall@5'],
              'VI Candidate@20',s['language']['vi']['candidate_recall_at_20'])
    print('regressions @5:',len(changes['top5']['regressed']),'failures:',len(failures))
if __name__=='__main__':main()
