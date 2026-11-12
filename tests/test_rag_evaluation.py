import math
import pytest
from scripts.evaluate_retrieval import metrics, ranking, validate_dataset, compare


def test_binary_metrics_expected_by_hand():
    m = metrics(['A', 'B', 'C'], ['B'])
    assert m['hit@1'] == 0 and m['hit@3'] == 1
    assert m['recall@1'] == 0 and m['recall@3'] == 1
    assert m['mrr'] == .5
    assert m['ndcg@5'] == pytest.approx(1 / math.log2(3))


def test_multi_relevance_ndcg_and_recall():
    m = metrics(['A', 'B', 'C', 'D'], ['B', 'D'])
    assert m['recall@3'] == .5 and m['recall@5'] == 1
    assert m['ndcg@5'] == pytest.approx((1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3)))


def test_duplicates_and_misses():
    assert metrics(['A', 'A', 'B'], ['B'])['mrr'] == .5
    assert metrics(['A'], ['B'])['ndcg@5'] == 0
    with pytest.raises(ValueError): metrics(['A'], [])


def test_document_identity_dedup():
    values = [{'metadata': {'source_url': 'a'}}, {'metadata': {'source_url': 'a'}}, {'metadata': {'source_url': 'b'}}]
    assert [x['id'] for x in ranking(values)] == ['a', 'b']
    with pytest.raises(ValueError): ranking([{'metadata': {}}])


def test_dataset_rejects_unknown_and_duplicate_ids():
    x = {'id': 'q', 'query': 'question', 'category': 'symptom', 'language': 'vi', 'cross_language': True, 'relevant_documents': ['a']}
    validate_dataset([x], {'a'})
    with pytest.raises(ValueError): validate_dataset([x], {'b'})
    with pytest.raises(ValueError): validate_dataset([x, x], {'a'})


def test_same_candidates_and_failed_reranker_never_reported():
    c = [{'content': 'a', 'metadata': {'source_url': 'a'}, 'rerank_score': None}, {'content': 'b', 'metadata': {'source_url': 'b'}, 'rerank_score': None}]
    class Retriever:
        def retrieve_candidates(self, q, n):
            assert n == 20
            return c
    class Scorer:
        def rerank(self, q, candidates, n):
            assert candidates is c
            return [dict(candidates[1], rerank_score=2), dict(candidates[0], rerank_score=1)]
    case = {'id': 'q', 'query': 'question', 'relevant_documents': ['b']}
    result = compare([case], Retriever(), Scorer())[0]
    assert result['baseline_metrics']['hit@1'] == 0
    assert result['reranker_metrics']['hit@1'] == 1
    class Fallback:
        def rerank(self, q, candidates, n): return candidates
    with pytest.raises(RuntimeError): compare([case], Retriever(), Fallback())
