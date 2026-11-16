import pytest
from scripts.query_expansion_experiment import ExperimentalQueryExpander, keywords
from scripts.experimental_cross_language import retrieve_with_translation


def test_expansion_preserves_original_and_generates_keywords():
    exp = ExperimentalQueryExpander(lambda _: 'What are the symptoms of diabetes?', 'mock')
    out = exp.expand_query('Triệu chứng tiểu đường là gì?')
    assert out.original_query == 'Triệu chứng tiểu đường là gì?'
    assert out.expanded_query == 'symptoms diabetes'
    assert out.status == 'ok'


@pytest.mark.parametrize('value', ['', 'nội dung tiếng Việt', 'one\ntwo', 'x' * 501])
def test_invalid_expansion_falls_back(value):
    out = ExperimentalQueryExpander(lambda _: value, 'mock').expand_query('đau đầu')
    assert out.expanded_query == '' and out.status == 'fallback'


def test_exception_falls_back_without_query_in_log(caplog):
    def fail(_): raise RuntimeError('private text')
    out = ExperimentalQueryExpander(fail, 'mock').expand_query('private patient query')
    assert out.original_query == 'private patient query' and out.expanded_query == ''
    assert 'private' not in caplog.text


def test_translation_input_cannot_contain_labels(tmp_path, monkeypatch):
    import json
    import sys
    from scripts.cache_cross_language_queries import main
    data = tmp_path / 'input.json'
    data.write_text(json.dumps([{'query':'test', 'relevant_documents':['secret']}]), encoding='utf8')
    monkeypatch.setattr(sys, 'argv', ['cache', '--input', str(data), '--output', str(tmp_path/'out'),
                                     '--timings', str(tmp_path/'times')])
    with pytest.raises(ValueError, match='Query-only'):
        main()


def test_no_expansion_uses_original_query():
    class Fake:
        def retrieve_candidates(self, q, n):
            assert q == 'đau đầu' and n == 20
            return ['baseline']
    assert retrieve_with_translation(Fake(), 'đau đầu', '') == ['baseline']


def test_rrf_deduplicates_sources_and_preserves_metadata():
    class Fake:
        vector_search_enabled = False
        class C:
            def count(self): return 100
        collection = C()
        def is_available(self): return True
        def expand_query(self,q): return q
        def lexical_search(self,q,n):
            if q == 'en': return [{'content':'chunk two','rank':1,'metadata':{'source_url':'same','source':'NLM'}}]
            return [{'content':'chunk one','rank':1,'metadata':{'source_url':'same','title':'A'}},
                    {'content':'other','rank':2,'metadata':{'source_url':'other'}}]
    hits=retrieve_with_translation(Fake(),'vi','en')
    assert [x['metadata']['source_url'] for x in hits] == ['same','other']
    assert hits[0]['metadata']['title'] == 'A'
    assert hits[0]['metadata']['source'] == 'NLM'
    assert set(hits[0]['branches']) == {'original','translated'}


def test_vector_branch_and_translation_branch_share_source():
    class Fake:
        vector_search_enabled = True
        class C:
            def count(self): return 100
        collection = C()
        def is_available(self): return True
        def expand_query(self,q): return q
        def lexical_search(self,q,n):
            return [{'content':'same chunk','rank':1,'metadata':{'source_url':'same','title':'A'}}] if q == 'en' else []
        def vector_search(self,q,n):
            return [{'content':'same chunk','rank':2,'metadata':{'source_url':'same','source':'NLM'},'distance':.3}]
    hits=retrieve_with_translation(Fake(),'vi','en')
    assert len(hits)==1
    assert hits[0]['fusion_score'] == pytest.approx(1/61+1/62)
    assert set(hits[0]['branches']) == {'translated','vector'}
    assert hits[0]['metadata']['title']=='A' and hits[0]['metadata']['source']=='NLM'
