"""Experimental search-keyword expansion; never connected to production."""
import re
import time
from dataclasses import dataclass

# Generic English function words only; not medical concepts or benchmark labels.
STOP = {'a','an','the','i','me','my','we','our','you','your','is','are','was','were',
        'do','does','did','to','of','in','on','at','for','with','by','from','and','or',
        'what','which','who','when','where','how','can','could','should','would','be',
        'as','it','this','that','there','about','some','have','has','had'}


@dataclass(frozen=True)
class ExpandedQuery:
    original_query: str
    expanded_query: str
    source_language: str
    target_language: str
    method: str
    status: str
    latency_ms: float


def keywords(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('empty expansion')
    # Restrict output to English search keywords, not an answer or a paragraph.
    if len(value) > 500 or '\n' in value or any(ord(c) > 127 for c in value):
        raise ValueError('invalid expansion')
    tokens = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", value.lower())
    output = ' '.join(t for t in tokens if t not in STOP)
    if not output or len(output) > 220 or len(output.split()) > 30:
        raise ValueError('invalid keyword count')
    return output


class ExperimentalQueryExpander:
    def __init__(self, translator, method):
        self.translator = translator
        self.method = method

    def expand_query(self, query, source_language='vi', target_language='en'):
        start = time.perf_counter()
        status = 'ok'
        try:
            if not isinstance(query, str) or not query.strip():
                raise ValueError('empty query')
            if source_language != 'vi' or target_language != 'en':
                raise ValueError('unsupported languages')
            expanded = keywords(self.translator(query))
        except Exception:
            # No exception text or patient query is logged. Retrieval will use original.
            expanded, status = '', 'fallback'
        return ExpandedQuery(query, expanded, source_language, target_language, self.method,
                             status, (time.perf_counter() - start) * 1000)


def google_translate_unofficial(query):
    """Unofficial, unsupported endpoint; only for controlled diagnostic inputs."""
    import requests
    response = requests.get('https://translate.googleapis.com/translate_a/single',
                            params={'client':'gtx','sl':'vi','tl':'en','dt':'t','q':query}, timeout=15)
    response.raise_for_status()
    parts = response.json()[0]
    return ' '.join(part[0] for part in parts if part and part[0])
