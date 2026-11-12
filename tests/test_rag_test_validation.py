from scripts.validate_rag_test_set import validate,normalize


def item(id, query, lang='vi', url='https://example.org/a'):
    return {'id':id,'query':query,'language':lang,'cross_language':lang=='vi','category':'symptom','difficulty':'medium','relevant_documents':[url]}


def test_valid_schema_and_duplicate_normalization():
    assert normalize('Đau-ĐẦU?')==normalize('đau đầu')
    report=validate([], [item('a','Đau-ĐẦU?'),item('b','đau đầu')], {'https://example.org/a'})
    assert any(x['error']=='duplicate_normalized_query' for x in report['errors'])


def test_validation_rejects_unknown_urls_and_category():
    row=item('a','test');row['category']='unsupported';row['relevant_documents']=['https://not.example/no']
    report=validate([], [row], {'https://example.org/a'})
    assert {'invalid_category','invalid_or_unindexed_source'} <= {x['error'] for x in report['errors']}


def test_exact_dev_duplicates_and_near_matches_are_flagged():
    dev=[item('d','What can cause severe muscle cramps?',lang='en')]
    report=validate(dev,[item('a','What can cause severe muscle cramps?',lang='en')],{'https://example.org/a'})
    assert any(x['error']=='exact_dev_overlap' for x in report['errors'])
    assert report['near_dev_flags'][0]['status']=='needs_human_review'
