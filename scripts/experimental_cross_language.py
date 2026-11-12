"""Isolated RRF experiment. The caller supplies an independently translated query.

No translator, model, network call, or production integration is included.
Do not generate translations from evaluation labels: that would leak ground truth.
"""
import math


def retrieve_with_translation(rag, query, english_query, top_k=20):
    """Fuse existing lexical + independently translated lexical + optional vector.

    If a translation is absent, use the exact configured production retriever.
    Scores are RRF over separate branches; one chunk can receive multiple votes.
    """
    if not isinstance(english_query, str) or not english_query.strip():
        return rag.retrieve_candidates(query, top_k)
    if not isinstance(query, str) or not query.strip() or not rag.is_available():
        return []
    if type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError('top_k must be an integer between 1 and 20')
    pool = min(rag.collection.count(), top_k * 3)
    expanded = rag.expand_query(query[:2000])
    branches = [('original', rag.lexical_search(expanded, pool)),
                ('translated', rag.lexical_search(english_query.strip()[:2000], pool))]
    if rag.vector_search_enabled:
        branches.append(('vector', rag.vector_search(expanded, pool)))
    fused = {}
    for branch, hits in branches:
        seen = set()
        for hit in hits:
            content, rank = hit.get('content'), hit.get('rank')
            if not isinstance(content, str) or not content or type(rank) is not int or rank < 1:
                raise ValueError('Invalid branch result')
            if content in seen:
                continue
            seen.add(content)
            item = fused.setdefault(content, {'content': content, 'metadata': hit.get('metadata') or {},
                                               'fusion_score': 0.0, 'branches': [], 'rerank_score': None})
            item['metadata'] = {**(hit.get('metadata') or {}), **item['metadata']}
            item['fusion_score'] += 1 / (60 + rank)
            item['branches'].append(branch)
            if branch == 'vector':
                item['metadata'] = {**item['metadata'], **(hit.get('metadata') or {})}
                item['distance'] = hit.get('distance')
    if not all(math.isfinite(x['fusion_score']) for x in fused.values()):
        raise ValueError('Invalid RRF score')
    # Keep the same top-K chunk budget as the baseline, then collapse source
    # URLs for document-level evaluation. Do not refill after deduplication.
    chunks = sorted(fused.values(), key=lambda x: x['fusion_score'], reverse=True)[:top_k]
    documents = {}
    for hit in chunks:
        identity = hit['metadata'].get('source_url') or ('content:' + hit['content'])
        if identity not in documents:
            documents[identity] = hit
        else:
            existing = documents[identity]
            existing['branches'] = list(dict.fromkeys(existing['branches'] + hit['branches']))
            existing['metadata'] = {**hit['metadata'], **existing['metadata']}
    return list(documents.values())
