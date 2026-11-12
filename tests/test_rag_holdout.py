import json
from pathlib import Path
from scripts.evaluate_rag_holdout import summary
from scripts.evaluate_retrieval import metrics


def test_holdout_summary_uses_query_level_recall_and_subgroups():
    rows=[{'id':'a','metrics':metrics(['x'],['x']),'candidate_recall_at_20':1,
           'retrieval_latency_ms':1,'language':'vi','cross_language':True,'category':'symptom','difficulty':'easy'},
          {'id':'b','metrics':metrics(['z'],['y']),'candidate_recall_at_20':0,
           'retrieval_latency_ms':3,'language':'en','cross_language':False,'category':'disease','difficulty':'hard'}]
    result=summary(rows)
    assert result['overall']['metrics']['recall@5']==.5
    assert result['language']['vi']['metrics']['recall@5']==1
    assert result['language']['en']['candidate_recall_at_20']==0
    assert result['difficulty']['hard']['count']==1


def test_metric_reproducibility():
    # Deterministic metric calculation
    ranking = ['doc_a', 'doc_b', 'doc_c', 'doc_d', 'doc_e']
    relevant = ['doc_b', 'doc_d']
    m = metrics(ranking, relevant)
    assert m['hit@1'] == 0.0
    assert m['hit@3'] == 1.0
    assert m['hit@5'] == 1.0
    assert m['recall@1'] == 0.0
    assert m['recall@3'] == 0.5
    assert m['recall@5'] == 1.0
    assert m['mrr'] == 0.5  # 1/2 for first hit at rank 2
    assert 0.0 < m['ndcg@5'] <= 1.0


def test_config_snapshot_structure():
    cfg_path = Path(__file__).resolve().parents[1] / 'evaluation' / 'rag_phase16_frozen_config.json'
    assert cfg_path.exists(), "Frozen config snapshot must exist"
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    required_keys = ['bm25', 'candidate_chunk_budget', 'vector_enabled', 'reranker_enabled', 'query_expansion_method', 'files_sha256']
    for k in required_keys:
        assert k in cfg, f"Missing required configuration snapshot key: {k}"
    assert cfg['candidate_chunk_budget'] == 20
    assert cfg['vector_enabled'] is False
    assert cfg['reranker_enabled'] is False

