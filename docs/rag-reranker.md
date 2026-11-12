# Optional local RAG reranker

The reranker is disabled by default. With `RAG_RERANK_ENABLED=true`,
`retrieve_context()` obtains up to 20 RRF candidates, scores them with a local
cross-encoder, and returns the caller's existing `top_k` context format. The
vector-search switch remains independent.

The selected model is `BAAI/bge-reranker-v2-m3`, a multilingual cross-encoder
published under Apache 2.0. Its weights occupy about 2.27 GB. Model scores are
relative relevance scores, not medical probabilities or clinical validation.

## Provisioning

Install the optional dependencies in your environment, then explicitly download
the model before serving requests. Example from the project root in PowerShell:

```powershell
python -m pip install -r requirements-reranker.txt
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='BAAI/bge-reranker-v2-m3', revision='953dc6f', local_dir='models/bge-reranker-v2-m3', allow_patterns=['config.json','model.safetensors','sentencepiece.bpe.model','special_tokens_map.json','tokenizer.json','tokenizer_config.json'])"
$env:RAG_RERANK_ENABLED='true'
python app.py
```

The provisioned model directory is ignored by Git. Alternatively set
`RAG_RERANK_MODEL_PATH` to a previously provisioned local model directory.
Without either directory the service checks the existing Hugging Face cache.
Loading uses `local_files_only=True` and `trust_remote_code=False`; a patient
request does not download model files or send its query to a model provider.

## Operation and fallback

Each application process loads the model lazily at most once and reuses it.
`RAG_RERANK_TIMEOUT_SECONDS` sets a positive finite timeout up to 120 seconds;
the default is 10 seconds. First load may exceed this timeout: that request
returns the original candidate order while loading continues in the background.
Only one load/inference per process can be in flight; busy requests fall back.
Python cannot forcibly terminate a stuck inference thread. If it never returns,
the process must be restarted to release the reranker. A load failure is also
cached until restart; provision/fix the model before restarting.

Missing packages/weights, exceptions, invalid or non-finite scores, and
timeouts retain the original RRF ordering of the **20-candidate pool**. When
disabled, the old `top_k`-sized retrieval path is retained exactly. Thus enabling
the reranker can change candidate retrieval even on fallback, because the larger
pool can affect RRF ranks. Error logs contain exception types, never the raw
query or exception text.

Model inference is CPU/memory intensive. Every server worker holds its own copy;
choose worker counts and timeout based on measurements on the deployment host.
Run `python -m pytest tests/test_reranker_service.py tests/test_rag_and_ingestion.py -v`
for deterministic tests. These use mocks and do not require model weights.
