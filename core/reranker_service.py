"""Optional local cross-encoder reranking with bounded, fail-open execution."""
import logging
import math
import os
import threading
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"
LOCAL_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "bge-reranker-v2-m3"


def _configured_timeout() -> float:
    try:
        value = float(os.getenv("RAG_RERANK_TIMEOUT_SECONDS", "10"))
        return value if math.isfinite(value) and 0 < value <= 120 else 10.0
    except ValueError:
        return 10.0


class RerankerService:
    """Reuse one local model per process; failures leave the incoming order intact.

    A timed-out inference cannot be forcibly stopped safely in a Python thread.
    The single-flight lock prevents additional workers from accumulating until
    that inference finishes. A process restart recovers a permanently stuck call.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, timeout_seconds: Optional[float] = None):
        self.model_name = model_name
        self.timeout_seconds = _configured_timeout() if timeout_seconds is None else timeout_seconds
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        self._model = None
        self._load_failed = False
        self._busy = threading.Lock()

    def _load_model(self):
        if self._load_failed:
            raise RuntimeError("Local reranker is unavailable until restart")
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                # Provision model files before enabling. Never fetch weights or
                # executable remote code as a side effect of a patient request.
                model_path = os.getenv("RAG_RERANK_MODEL_PATH")
                if not model_path:
                    model_path = str(LOCAL_MODEL_DIR) if self.model_name == DEFAULT_MODEL and LOCAL_MODEL_DIR.is_dir() else self.model_name
                self._model = CrossEncoder(model_path, local_files_only=True,
                                           trust_remote_code=False, max_length=512)
            except Exception:
                self._load_failed = True
                raise
        return self._model

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        """Return scored copies, or the original RRF ordering if inference fails."""
        fallback = candidates[:top_k]
        if not candidates:
            return fallback
        if not self._busy.acquire(blocking=False):
            logger.warning("Local reranker busy; retaining retrieval order.")
            return fallback
        done = threading.Event()
        result: Dict[str, Any] = {}

        def run() -> None:
            try:
                model = self._load_model()
                pairs = [(query[:2000], candidate["content"]) for candidate in candidates]
                scores = model.predict(pairs, show_progress_bar=False)
                values = [float(score) for score in scores]
                if len(values) != len(candidates) or not all(math.isfinite(v) for v in values):
                    raise ValueError("Invalid reranker scores")
                scored = [dict(candidate, rerank_score=score) for candidate, score in zip(candidates, values)]
                result["ranked"] = sorted(scored, key=lambda candidate: candidate["rerank_score"], reverse=True)[:top_k]
            except Exception as error:
                # Exception messages may contain the private query or document text.
                logger.warning("Local reranker unavailable (%s); retaining retrieval order.", type(error).__name__)
            finally:
                self._busy.release()
                done.set()

        try:
            threading.Thread(target=run, name="rag-reranker", daemon=True).start()
        except Exception as error:
            self._busy.release()
            logger.warning("Local reranker worker unavailable (%s); retaining retrieval order.", type(error).__name__)
            return fallback
        if not done.wait(self.timeout_seconds):
            logger.warning("Local reranker timed out; retaining retrieval order.")
            return fallback
        return result.get("ranked", fallback)


reranker_service = RerankerService()
