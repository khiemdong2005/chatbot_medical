"""Docker startup entrypoint with automatic RAG vector DB bootstrap & dataset readiness audit.

Guarantees that a fresh container built from Git (where medical_vectordb/chroma.sqlite3
is intentionally gitignored) automatically ingests the 364 curated bilingual documents
into /app/medical_vectordb on first boot, then execs Uvicorn as PID 1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VECTOR_DB_DIR = ROOT / "medical_vectordb"
CHROMA_SQLITE = VECTOR_DB_DIR / "chroma.sqlite3"
MANIFEST_FILE = VECTOR_DB_DIR / "active_collection.json"
CURATED_DIR = ROOT / "data" / "curated" / "ready_documents"

CRITICAL_ASSETS = (
    ("Nutrition Recipes (Mon Ngon Moi Ngay)", ROOT / "data" / "recipes" / "monngonmoingay_recipes_with_kcal.json"),
    ("Facilities HCM", ROOT / "data" / "CSKCB_Data" / "danh_sach_co_so_kcb_normalized.json"),
    ("Facilities Hanoi", ROOT / "data" / "CSKCB_Data" / "danh_sach_co_so_kcb_hanoi_normalized.json"),
    ("Curated RAG Corpus", CURATED_DIR),
    ("Frontend Shell HTML", ROOT / "frontend" / "templates" / "index.html"),
    ("Frontend App JS", ROOT / "frontend" / "static" / "js" / "app.js"),
)


def should_bootstrap(argv: list[str]) -> bool:
    """Run startup bootstrap only when launching the web server (uvicorn/gunicorn)."""
    if not argv:
        return False
    exe = Path(argv[0]).name.lower()
    if exe in ("uvicorn", "gunicorn"):
        return True
    if exe.startswith("python") and len(argv) >= 3 and argv[1] == "-m" and argv[2] in ("uvicorn", "gunicorn"):
        return True
    return False


def _has_populated_vectordb(db_dir: Path = VECTOR_DB_DIR) -> bool:
    """Return True if ChromaDB SQLite exists and active collection has >0 chunks."""
    sqlite_path = db_dir / "chroma.sqlite3"
    manifest_path = db_dir / "active_collection.json"
    if not sqlite_path.is_file() or sqlite_path.stat().st_size == 0:
        return False
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        col_name = manifest.get("active_collection")
        if not col_name:
            return False
        import chromadb

        client = chromadb.PersistentClient(path=str(db_dir))
        col = client.get_collection(name=col_name)
        return col.count() > 0
    except Exception as exc:
        print(f"[DockerEntrypoint] ChromaDB readiness check needs rebuild: {exc}", flush=True)
        return False


def ensure_vector_db_ready(
    db_dir: Path = VECTOR_DB_DIR,
    curated_dir: Path = CURATED_DIR,
    ingest_runner=None,
) -> bool:
    """Auto-build ChromaDB from curated corpus if missing/empty on fresh container start."""
    db_dir.mkdir(parents=True, exist_ok=True)
    if _has_populated_vectordb(db_dir):
        print("[DockerEntrypoint] ChromaDB vector store ready — skipping auto-ingest.", flush=True)
        return True

    if os.getenv("SKIP_AUTO_RAG_INGEST", "").strip().lower() in ("1", "true", "yes"):
        print("[DockerEntrypoint] SKIP_AUTO_RAG_INGEST=true — skipping auto-ingest.", flush=True)
        return False

    if not curated_dir.exists() or not any(curated_dir.glob("*.json")):
        print(f"[DockerEntrypoint] WARNING: Curated RAG corpus missing at {curated_dir}", flush=True)
        return False

    print(
        "[DockerEntrypoint] Fresh deploy detected (medical_vectordb empty). "
        "Auto-building ChromaDB RAG index from curated documents...",
        flush=True,
    )
    if ingest_runner is not None:
        return bool(ingest_runner())

    proc = subprocess.run(
        [sys.executable, str(ROOT / "ingest.py")],
        cwd=str(ROOT),
        check=False,
    )
    if proc.returncode == 0:
        print("[DockerEntrypoint] Auto-ingest completed successfully.", flush=True)
        return True
    print(
        f"[DockerEntrypoint] WARNING: Auto-ingest exited with code {proc.returncode}; "
        "continuing startup in degraded RAG mode.",
        flush=True,
    )
    return False


def log_asset_readiness() -> None:
    """Verify and print status of all critical static datasets & frontend assets."""
    missing = []
    for label, path in CRITICAL_ASSETS:
        if path.exists():
            print(f"[DockerEntrypoint] OK  | {label}: {path.relative_to(ROOT)}", flush=True)
        else:
            print(f"[DockerEntrypoint] ERR | MISSING {label}: {path.relative_to(ROOT)}", flush=True)
            missing.append(label)
    if missing:
        print(f"[DockerEntrypoint] WARNING: Missing critical assets: {', '.join(missing)}", flush=True)


def main() -> int:
    cmd = sys.argv[1:]
    if not cmd:
        cmd = [
            "uvicorn",
            "core.main_fastapi:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("PORT", "8000"),
            "--proxy-headers",
            "--forwarded-allow-ips=*",
        ]

    if should_bootstrap(cmd):
        (ROOT / "instance").mkdir(parents=True, exist_ok=True)
        (ROOT / "uploads").mkdir(parents=True, exist_ok=True)
        log_asset_readiness()
        ensure_vector_db_ready()

    os.execvp(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
