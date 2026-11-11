"""Small reproducible retrieval smoke test against the bundled medical corpus.

Run from the repository root: python -m scripts.evaluate_retrieval
"""
from core.rag_service import medical_rag_service as rag


CASES = [
    ("nhói ở chấn thủy lan ra sau lưng", "Abdominal pain"),
    ("tôi bị sốt", "Fever"),
    ("dau bung", "Abdominal pain"),
    ("ho khan", "Dry cough"),
    ("ibuprofen", "Ibuprofen"),
    ("đau ngực", "Chest pain"),
    ("viết truy vấn SQL join bảng nhân viên", None),
    ("lập trình decorator Python", None),
]


def vector_titles(query):
    result = rag.collection.query(query_texts=[query], n_results=3)
    return [meta["title"] for meta, distance in zip(result["metadatas"][0], result["distances"][0])
            if distance <= rag.acceptance_threshold]


def main():
    if not rag.is_available():
        raise SystemExit("Medical corpus unavailable")
    for label, retrieve in [
        ("Vector", vector_titles),
        ("Expanded vector", lambda q: vector_titles(rag.expand_query(q))),
        ("Hybrid", lambda q: [d["title"] for d in rag.retrieve_context(q, 3)]),
    ]:
        hits = irrelevant = 0
        for question, target in CASES:
            titles = retrieve(question)
            if target is None:
                irrelevant += bool(titles)
            elif target in titles:
                hits += 1
            else:
                print(f"{label} miss: {question} -> {titles}")
        total = sum(target is not None for _, target in CASES)
        print(f"{label}: top-3 hits {hits}/{total}, out-of-scope results {irrelevant}/{len(CASES) - total}")


if __name__ == "__main__":
    main()
