"""Translate ONLY the separately prepared query-only file; labels are inaccessible here."""
import argparse
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.query_expansion_experiment import ExperimentalQueryExpander, google_translate_unofficial


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timings',type=Path,required=True)
    args=p.parse_args()
    data=json.loads(args.input.read_text(encoding='utf8'))
    if any(set(item)!={'query'} for item in data):
        raise ValueError('Query-only input must not contain IDs, labels, titles or URLs')
    existing=json.loads(args.output.read_text(encoding='utf8')) if args.output.exists() else []
    saved={item['query']:item for item in existing}
    expander=ExperimentalQueryExpander(google_translate_unofficial,'google_translate_unofficial_gtx_vi_en_keywords_v1')
    timings=[]
    for i,item in enumerate(data,1):
        q=item['query']
        if q in saved:
            continue
        result=expander.expand_query(q)
        timings.append({'query':q,'status':result.status,'latency_ms':result.latency_ms})
        if result.status=='ok':
            saved[q]={'query':q,'expanded_query':result.expanded_query,'method':result.method}
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(list(saved.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(f'{i}/{len(data)} {result.status}',flush=True)
    args.timings.parent.mkdir(parents=True,exist_ok=True)
    args.timings.write_text(json.dumps(timings,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

if __name__=='__main__': main()
