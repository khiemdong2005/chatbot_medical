# RAG retrieval evaluation

Run from the repository root:

```powershell
python scripts/evaluate_retrieval.py
```

The command runs offline and needs the existing Chroma collection and local `models/bge-reranker-v2-m3` weights (or the local path in `RAG_RERANK_MODEL_PATH`). It uses the configured vector flag; if vector retrieval is configured, its embedding model must also be available offline. No Gemini or answer generation is involved. Model load and warmup are excluded from per-query latency, and model load time is recorded separately. The evaluation timeout is 120 seconds, not necessarily the online service timeout.

For every query, the configured retriever runs once and returns up to 20 chunks. The same chunks are fed to the reranker. Both rankings are deduplicated by `metadata.source_url` before computing document-level metrics. This groups files that cite the same article, including differently named aliases. It can also merge distinct sections on the same URL. MRR is bounded by the top-20 chunk pool. Hit@1/3/5 and Recall@1/3/5 and binary NDCG@5 operate on unique source URLs. One relevant URL makes hit and recall identical for that query. A failed branch or a reranker fallback aborts the run instead of being reported as a successful measurement.

Queries with no candidates skip model inference; the report counts them and provides reranker latency both across all queries and for the subset where inference actually ran. The first baseline lookup may include initial index setup. Candidate coverage counts queries for which no labeled source was in the entire top-20 chunk pool; reranking cannot recover those sources.

`rag_eval_dataset.json` contains synthetic test questions and provisional, corpus-grounded relevance labels: the labeled URLs were assigned from existing curated source topics, not retrieval results. These are not expert-reviewed judgments, do not exhaust every relevant article, and can have topic-word overlap with the indexed content. The two multi-source questions demonstrate partial recall. `cross_language=true` denotes Vietnamese query against predominantly English source content, whose indexed wrapper may include Vietnamese labels. This set is a development benchmark, not evidence of clinical accuracy or safety. A clinician should review labels and later add independently sourced, representative queries and complete relevance judgments.

The ingestion script loads only `data/curated/ready_documents/*.json`; evaluation files are outside that directory and are not ingested. The report records dataset and corpus hashes, configuration, per-query rankings, metrics, breakdowns, and failures. The JSON output is written to `evaluation/results/rag_eval_latest.json`; do not compare runs with mismatched corpus or dataset hashes as if only the model had changed.

```powershell
python -m pytest tests/test_rag_evaluation.py tests/test_rag_and_ingestion.py tests/test_reranker_service.py -q
```

## Phase 1.4 diagnostics

```powershell
# Reproduce the previous accent-folded expansion, in the benchmark process only
python scripts/analyze_rag_retrieval.py --legacy-expansion --output evaluation/results/rag_phase14_before.json
# Compare the current expansion and run the existing local reranker on hybrid candidates
python scripts/analyze_rag_retrieval.py --rerank --output evaluation/results/rag_phase14_after.json
```

Both commands verify the Phase 1.3 dataset and corpus hashes and use the existing local Chroma default embedding. They do not change the production vector flag, model, threshold or corpus. A missing embedding or a retrieval/reranking fallback aborts the experiment. The reranker run can take minutes on CPU.

For each Phase 1.3 miss, the diagnostic report includes the baseline source ranking, up to 50 lexical and vector chunks, a separate top-50 fusion experiment (with up to 150 chunks per branch), ranks and overlapping reason codes. Top-50 diagnostics are not the production top-20 candidate pool; filtered and unfiltered vector ranks are reported separately. Reason codes describe observable retrieval conditions, not clinically established diagnoses. The existing search index still folds accents for lexical matching. Phrase expansion now respects explicitly typed accents and retains a fallback for unaccented input.

The isolated `scripts/experimental_cross_language.py` exposes `retrieve_with_translation(rag, query, english_query)`: lexical results from the existing expanded query and an independently translated English query are combined using RRF, with the configured vector branch if enabled. Empty translations fall back to the existing retrieval method. This is not connected to production and does not include or call a translator. No D/E/F scores or translation costs were measured: translations produced from the evaluation labels would leak the answers. A separately sourced translator and held-out evaluation set are required to evaluate the experiment. Hybrid + reranker latency in the report is the sum of separately measured retrieval and reranking times, excluding model loading; the benchmark uses a 120-second timeout rather than necessarily matching the online timeout.

## Phase 1.5 cross-language expansion

`scripts/query_expansion_experiment.py` isolates query expansion from retrieval. The diagnostic provider uses an unofficial Google Translate endpoint and generic English function-word filtering; there is no supported API contract, fixed model version or reliable price/token data. It is not integrated into production. Do not send actual patient text through this experiment without a separate privacy and provider review. Validation and exceptions return an empty expansion, which falls back to the original retriever.

The translation input `evaluation/cache/phase15_vi_input.json` has only synthetic question text; it contains no labels or titles. `scripts/cache_cross_language_queries.py` reads that file alone and stores successful outputs in `evaluation/cache/cross_language_queries.json`. After the cache exists, the benchmark runs offline:

```powershell
python scripts/evaluate_cross_language.py --rerank --output evaluation/results/rag_phase15.json
python -m pytest tests/test_query_expansion_experiment.py tests/test_rag_expansion_experiment.py -q
```

Remove `--rerank` for a quicker A/B/vector run. The script writes a partial report after retrieval before beginning optional reranking. Missing or invalid expansions fall back to the original retrieval. English queries do not invoke translation. All scores use the existing development set; the experiment is not a held-out estimate. Since expanded results are deduplicated by source before reranking, that reranking stage is not directly comparable to Phase 1.4, which reranked chunks before source deduplication. Translation latency is measured separately; cached retrieval and estimated uncached retrieval are reported separately. Token counts and cost are unknown.

RRF scores are assigned to chunks first using branch ranks. After limiting to the first 20 chunks, chunks sharing `source_url` are collapsed: the highest-ranked chunk supplies the displayed score and content, while `branches` records the union of branches among the collapsed chunks. Branch membership therefore does not imply that all branch votes were added to that one displayed chunk score. This preserves the baseline's 20-chunk budget; it is not document-level RRF scoring.
