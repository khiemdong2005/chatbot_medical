"""Offline evaluation of cached independent VI->EN query expansions."""
import argparse, hashlib, json, logging, math, os, sys, time
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', ANONYMIZED_TELEMETRY='False')
from scripts.evaluate_retrieval import metrics, ranking, average, summarize_latency, validate_dataset
from scripts.experimental_cross_language import retrieve_with_translation
from scripts.query_expansion_experiment import keywords
from core.rag_service import medical_rag_service as rag
from core.reranker_service import RerankerService


def rank_with_branches(hits):
    rows = ranking(hits)
    branch_map = {}
    for hit in hits:
        identity = (hit.get('metadata') or {}).get('source_url')
        branches = hit.get('branches') or ([name for name, field in (('original','lexical_score'),('vector','vector_score'))
                                              if hit.get(field) is not None] or ['unknown'])
        branch_map.setdefault(identity, set()).update(branches)
    for row in rows:
        row['branches'] = sorted(branch_map.get(row['id'], ()))
    return rows


def summary(rows):
    def group(r):
        return {'count':len(r),'metrics':average([x['metrics'] for x in r]),
                'candidate_recall_at_20':sum(x['candidate_recall_at_20'] for x in r)/len(r),
                'retrieval_latency_ms':summarize_latency([x['retrieval_latency_ms'] for x in r]),
                'estimated_uncached_total_ms':summarize_latency([x['retrieval_latency_ms']+x['expansion_latency_ms'] for x in r])}
    return {'overall':group(rows),'language':{lang:group([x for x in rows if x['language']==lang]) for lang in ('vi','en')}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--rerank',action='store_true');p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    dataset=ROOT/'evaluation/rag_eval_dataset.json'; prior=ROOT/'evaluation/results/rag_eval_latest.json'
    cachefile=ROOT/'evaluation/cache/cross_language_queries.json'; timingfile=ROOT/'evaluation/results/phase15_expansion_timings.json'
    cases=json.loads(dataset.read_text(encoding='utf8')); old=json.loads(prior.read_text(encoding='utf8'))
    digest=hashlib.sha256(dataset.read_bytes()).hexdigest()
    if digest!=old['metadata']['dataset_sha256']: raise RuntimeError('Dataset changed')
    corpus=rag.collection.get(include=['documents','metadatas']); docs=list(zip(corpus['documents'],corpus['metadatas']))
    validate_dataset(cases,{m['source_url'] for d,m in docs})
    h=hashlib.sha256()
    for doc,meta in sorted(docs,key=lambda x:(x[1]['file_name'],x[0])):
        h.update((meta['file_name']+'\0'+doc+'\0').encode('utf8'))
    if h.hexdigest()!=old['metadata']['corpus_sha256']: raise RuntimeError('Corpus changed')
    cache={x['query']:x for x in json.loads(cachefile.read_text(encoding='utf8'))}
    timings={x['query']:x for x in json.loads(timingfile.read_text(encoding='utf8'))}
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
    path=Path(ONNXMiniLM_L6_V2.DOWNLOAD_PATH)/'onnx'
    if not (path/'model.onnx').is_file() or not (path/'tokenizer.json').is_file(): raise RuntimeError('Vector model unavailable offline')
    rag.collection.query(query_texts=['offline embedding preflight'],n_results=1)
    class Guard(logging.Handler):
        def emit(self,record):
            if 'lookup unavailable' in record.getMessage(): raise RuntimeError('Retriever failed: '+record.getMessage())
    guard=Guard();logger=logging.getLogger('MedicalRAGService');logger.addHandler(guard)
    runs={name:[] for name in ('baseline','expansion','vector','expansion_vector')}
    try:
        for mode in runs:
            rag.vector_search_enabled=mode in ('vector','expansion_vector')
            for case in cases:
                query=case['query']; v=cache.get(query) if case['language']=='vi' else None
                expansion=''
                if v and mode in ('expansion','expansion_vector'):
                    try:
                        expansion=keywords(v.get('expanded_query',''))
                    except ValueError:
                        expansion=''
                start=time.perf_counter()
                hits=retrieve_with_translation(rag,query,expansion,20) if expansion else rag.retrieve_candidates(query,20)
                elapsed=(time.perf_counter()-start)*1000
                # Ground-truth labels are only read here, after retrieval.
                relevant=case['relevant_documents']; ordered=rank_with_branches(hits)
                ranks=[x['id'] for x in ordered]
                t=timings.get(query,{}) if expansion else {}
                runs[mode].append({'id':case['id'],'query':query,'language':case['language'],'category':case['category'],
                                   'expanded_query':expansion,'expansion_status':'cached' if expansion else ('not_applicable' if case['language']=='en' else 'fallback'),
                                   'relevant_documents':relevant,'ranking':ordered,
                                   'candidates':[{'content':x['content'],'metadata':x['metadata'],'fusion_score':x.get('fusion_score'),
                                                  'rerank_score':x.get('rerank_score'),
                                                  'branches':x.get('branches') or ([name for name, field in (('original','lexical_score'),('vector','vector_score')) if x.get(field) is not None] or ['unknown'])} for x in hits],
                                   'metrics':metrics(ranks,relevant),'candidate_recall_at_20':len(set(ranks)&set(relevant))/len(relevant),
                                   'retrieval_latency_ms':elapsed,'expansion_latency_ms':t.get('latency_ms',0)})
            print('completed',mode,flush=True)
        # Preserve completed retrieval results if the optional reranker fails.
        checkpoint = {'metadata': {'dataset_sha256':digest, 'corpus_sha256':h.hexdigest(),
                                    'status':'retrieval_complete_reranker_pending'},
                      'configurations':{name:summary(rows) for name,rows in runs.items()},
                      'per_query':{name:[{k:v for k,v in row.items() if k!='candidates'} for row in rows]
                                   for name,rows in runs.items()}}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.with_name(args.output.stem+'_partial.json').write_text(
            json.dumps(checkpoint,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
        load_ms=None
        if args.rerank:
            runner=RerankerService(timeout_seconds=120); start=time.perf_counter();runner._load_model();load_ms=(time.perf_counter()-start)*1000
            first=next(x['candidates'] for x in runs['expansion_vector'] if x['candidates'])
            if runner.rerank('medical information',first[:1],1)[0].get('rerank_score') is None: raise RuntimeError('Reranker warmup failed')
            runs['expansion_vector_reranker']=[]
            for idx,row in enumerate(runs['expansion_vector'],1):
                start=time.perf_counter()
                ranked=runner.rerank(row['query'],row['candidates'],len(row['candidates'])) if row['candidates'] else []
                elapsed=(time.perf_counter()-start)*1000
                if len(ranked)!=len(row['candidates']) or any(not isinstance(x.get('rerank_score'),(int,float)) or not math.isfinite(x['rerank_score']) for x in ranked):
                    raise RuntimeError('Reranker fallback: '+row['id'])
                order=rank_with_branches(ranked); ids=[x['id'] for x in order]
                runs['expansion_vector_reranker'].append({**row,'ranking':order,'candidates':ranked,
                    'metrics':metrics(ids,row['relevant_documents']), 'retrieval_latency_ms':row['retrieval_latency_ms']+elapsed,
                    'rerank_latency_ms':elapsed})
                print(f'rerank {idx}/{len(cases)}',flush=True)
        def trim(row):
            return {k:v for k,v in row.items() if k!='candidates'}
        baseline={x['id']:x for x in runs['baseline']}; vector={x['id']:x for x in runs['vector']}; expanded={x['id']:x for x in runs['expansion']}
        comparisons={}
        for metric in ('hit@5','candidate_recall_at_20'):
            groups={'expansion_only':[],'vector_only':[],'both':[],'neither':[], 'baseline_already_complete':[]}
            for case in cases:
                if case['language']!='vi': continue
                i=case['id']; metric_value=lambda x: x['metrics'][metric] if metric=='hit@5' else x[metric]
                base=metric_value(baseline[i])
                if base >= 1:
                    groups['baseline_already_complete'].append(i)
                    continue
                ex=metric_value(expanded[i])>base; ve=metric_value(vector[i])>base
                key='both' if ex and ve else 'expansion_only' if ex else 'vector_only' if ve else 'neither'
                groups[key].append(i)
            comparisons[metric]=groups
        changes={}
        for mode,rows in runs.items():
            changes[mode]={}
            for k in (1,3,5):
                changes[mode][f'top{k}']={'improved':[x['id'] for x in rows if x['metrics'][f'hit@{k}']>baseline[x['id']]['metrics'][f'hit@{k}']],
                                           'regressed':[x['id'] for x in rows if x['metrics'][f'hit@{k}']<baseline[x['id']]['metrics'][f'hit@{k}']]}
        report={'metadata':{'timestamp_utc':datetime.now(timezone.utc).isoformat(),'dataset_sha256':digest,'corpus_sha256':h.hexdigest(),
                  'cache_sha256':hashlib.sha256(cachefile.read_bytes()).hexdigest(),'method':'google_translate_unofficial_gtx_vi_en_keywords_v1',
                  'model':'Google Translate unofficial endpoint, unspecified model/version', 'dataset_role':'development diagnostic, not held-out test',
                  'candidate_budget':'top 20 chunks then collapse duplicate source URLs',
                  'rerank_scope':'expansion candidates are deduplicated by source before reranking; Phase 1.4 reranked chunks first',
                  'reranker_timeout_seconds':120,'model_load_ms':load_ms,
                  'latency_note':'Retrieval uses cached expansion; estimated uncached adds measured network time. Rerank latency sums separate retrieval and rerank timings.',
                  'cost':'unknown; unofficial endpoint does not provide token or pricing information'},
                'configurations':{k:summary(v) for k,v in runs.items()},'comparison_expansion_vs_vector':comparisons,
                'changes_vs_baseline':changes,
                'improvement_categories_top5':{name:dict(Counter(baseline[id]['category'] for id in change['top5']['improved']))
                                               for name,change in changes.items()},
                'per_query':{k:[trim(x) for x in v] for k,v in runs.items()},
                'expansion_latency_ms':summarize_latency([x['latency_ms'] for x in timings.values()]),
                'expansion_status_counts':dict(Counter(x['status'] for x in timings.values()))}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
        for k,v in report['configurations'].items(): print(k,json.dumps(v,ensure_ascii=False),flush=True)
        print('saved',args.output)
    finally:
        logger.removeHandler(guard);rag.vector_search_enabled=False

if __name__=='__main__':main()
