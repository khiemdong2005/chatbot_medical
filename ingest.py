"""
MediMind RAG Ingestion Pipeline Root Forwarder
Cho phép chạy:
  python ingest.py --dry-run
hoặc:
  python ingest.py
hoặc:
  docker compose run --rm medical-api python ingest.py --dry-run
"""
import sys
from pathlib import Path

# Đảm bảo import được module
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.ingest import main

if __name__ == "__main__":
    main()
