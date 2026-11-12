from scripts.experimental_cross_language import retrieve_with_translation
import pytest


class Fake:
    vector_search_enabled = False
    class Collection:
        def count(self): return 100
    collection = Collection()
    def is_available(self): return True
    def expand_query(self, q): return q
    def lexical_search(self, q, n):
        if q == 'en':
            return [{'content':'b', 'metadata':{'source_url':'b'}, 'rank':1},
                    {'content':'a', 'metadata':{'source_url':'a'}, 'rank':2}]
        return [{'content':'a', 'metadata':{'source_url':'a'}, 'rank':1}]
    def retrieve_candidates(self, q, top): return [{'content':'baseline'}]


def test_experiment_fuses_independent_lexical_branches():
    hits = retrieve_with_translation(Fake(), 'vi', 'en')
    assert [x['content'] for x in hits] == ['a','b']
    assert hits[0]['fusion_score'] == pytest.approx(1/61+1/62)
    assert hits[0]['branches'] == ['original','translated']


def test_empty_translation_retains_configured_baseline():
    assert retrieve_with_translation(Fake(), 'vi', '') == [{'content':'baseline'}]


def test_bad_top_k_rejected():
    with pytest.raises(ValueError): retrieve_with_translation(Fake(), 'vi', 'en', 21)
