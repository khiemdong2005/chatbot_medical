"""Validate a draft test set against its development set and indexed source URLs."""
import argparse, json, re, sys, unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
CATEGORIES={'symptom','emergency','disease','medication','prevention','diagnosis','treatment'}
DIFFICULTIES={'easy','medium','hard'}


def normalize(query):
    text=unicodedata.normalize('NFC',query).casefold()
    return ' '.join(re.findall(r'[^\W_]+',text,flags=re.UNICODE))


def validate(dev,test,known):
    errors=[]; seen_ids=set(); seen_queries={}; dev_normal={normalize(x['query']) for x in dev}
    for row in test:
        ident=row.get('id');q=row.get('query')
        if not isinstance(ident,str) or not ident or ident in seen_ids: errors.append({'id':ident,'error':'missing_or_duplicate_id'})
        seen_ids.add(ident)
        if not isinstance(q,str) or not q.strip(): errors.append({'id':ident,'error':'invalid_query'});continue
        n=normalize(q)
        if n in seen_queries: errors.append({'id':ident,'error':'duplicate_normalized_query','other':seen_queries[n]})
        seen_queries[n]=ident
        if n in dev_normal: errors.append({'id':ident,'error':'exact_dev_overlap'})
        lang=row.get('language')
        if lang not in ('vi','en') or row.get('cross_language') != (lang=='vi'): errors.append({'id':ident,'error':'invalid_language_or_cross_language'})
        if row.get('category') not in CATEGORIES: errors.append({'id':ident,'error':'invalid_category'})
        if row.get('difficulty') not in DIFFICULTIES: errors.append({'id':ident,'error':'invalid_difficulty'})
        labels=row.get('relevant_documents')
        if not isinstance(labels,list) or not labels or len(set(labels))!=len(labels):
            errors.append({'id':ident,'error':'invalid_labels'});continue
        for url in labels:
            if not isinstance(url,str) or urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc or url not in known:
                errors.append({'id':ident,'error':'invalid_or_unindexed_source','source':url})
    similar=[]
    for row in test:
        q=normalize(row['query']);qt=set(q.split())
        for d in dev:
            if row['language']!=d['language']:continue
            other=normalize(d['query']);ot=set(other.split())
            ratio=SequenceMatcher(None,q,other).ratio();jaccard=len(qt&ot)/len(qt|ot) if qt|ot else 0
            if ratio>=.82 or (len(qt)>=5 and len(ot)>=5 and jaccard>=.75):
                similar.append({'test_id':row['id'],'dev_id':d['id'],'test_query':row['query'],'dev_query':d['query'],
                                'character_similarity':round(ratio,3),'token_jaccard':round(jaccard,3),'status':'needs_human_review'})
    return {'errors':errors,'near_dev_flags':similar,
            'distribution':{'count':len(test),'languages':dict(Counter(x['language'] for x in test)),
                            'categories':dict(Counter(x['category'] for x in test)),
                            'difficulty':dict(Counter(x['difficulty'] for x in test)),
                            'multi_source_queries':sum(len(x['relevant_documents'])>1 for x in test)},
            'notes':['Similarity flags are heuristic and do not establish semantic independence.',
                     'Source existence is not a clinical relevance review; all labels require independent human review.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    from core.rag_service import medical_rag_service as rag
    raw=rag.collection.get(include=['metadatas'])
    known={x['source_url'] for x in raw['metadatas'] if x.get('source_url')}
    dev=json.loads((ROOT/'evaluation/rag_dev_dataset.json').read_text(encoding='utf8'))
    test=json.loads((ROOT/'evaluation/rag_test_dataset.json').read_text(encoding='utf8'))
    report=validate(dev,test,known)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('distribution:',report['distribution'])
    print('errors:',len(report['errors']),'near-dev flags:',len(report['near_dev_flags']))
    if report['errors']:raise SystemExit(1)
if __name__=='__main__':main()
