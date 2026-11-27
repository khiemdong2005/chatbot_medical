"""Regression tests for scripts/docker_entrypoint.py (fresh Docker RAG auto-bootstrap)."""

from pathlib import Path

from scripts import docker_entrypoint


def test_should_bootstrap_only_for_web_server_commands():
    assert docker_entrypoint.should_bootstrap(["uvicorn", "core.main_fastapi:app"]) is True
    assert docker_entrypoint.should_bootstrap(["gunicorn", "app:app"]) is True
    assert docker_entrypoint.should_bootstrap(["python", "-m", "uvicorn", "core.main_fastapi:app"]) is True
    assert docker_entrypoint.should_bootstrap(["python", "ingest.py"]) is False
    assert docker_entrypoint.should_bootstrap(["pytest", "-q"]) is False
    assert docker_entrypoint.should_bootstrap([]) is False


def test_ensure_vector_db_ready_triggers_ingest_when_empty(tmp_path: Path):
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "doc1.json").write_text('{"title": "test"}', encoding="utf-8")
    db_dir = tmp_path / "vectordb"

    called = {"count": 0}

    def fake_ingest():
        called["count"] += 1
        return True

    ok = docker_entrypoint.ensure_vector_db_ready(
        db_dir=db_dir,
        curated_dir=curated,
        ingest_runner=fake_ingest,
    )
    assert ok is True
    assert called["count"] == 1


def test_ensure_vector_db_ready_skips_when_populated(monkeypatch, tmp_path: Path):
    called = {"count": 0}
    monkeypatch.setattr(docker_entrypoint, "_has_populated_vectordb", lambda _dir: True)

    ok = docker_entrypoint.ensure_vector_db_ready(
        db_dir=tmp_path / "vectordb",
        curated_dir=tmp_path / "curated",
        ingest_runner=lambda: called.__setitem__("count", called["count"] + 1) or True,
    )
    assert ok is True
    assert called["count"] == 0


def test_critical_docker_assets_all_exist():
    for label, path in docker_entrypoint.CRITICAL_ASSETS:
        assert path.exists(), f"Missing critical Docker asset ({label}): {path}"


def test_dockerignore_excludes_local_runtime_state():
    content = (docker_entrypoint.ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".env", "instance/", "medical_vectordb/", "uploads/", "logs/"):
        assert pattern in content, f".dockerignore missing required exclusion: {pattern}"
