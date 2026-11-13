"""Check tracked repository paths and Python syntax without app dependencies."""

import ast
from pathlib import Path, PurePosixPath
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIRECTORIES = {
    ".agents", ".claude", ".gemini", ".venv", "venv", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "scratch", "_quarantine_trash", "antigravity-setup", "instance",
    "medical_vectordb", "models",
}
LOCAL_FILES = {"skills-lock.json", ".artifact-server.json", ".sharing.json"}
DESIGN_HISTORY = (
    "designs/medimind-redesign/history/",
    "docs/design/medimind-redesign/history/",
)


def path_problem(name: str) -> str | None:
    path = PurePosixPath(name)
    if set(path.parts).intersection(LOCAL_DIRECTORIES):
        return "local configuration, cache or generated database"
    if path.name in LOCAL_FILES or name.startswith(DESIGN_HISTORY):
        return "personal tooling or generated editor state"
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return "private environment configuration"
    if path.suffix.lower() in {".pyc", ".pyo", ".log", ".db", ".sqlite", ".sqlite3"}:
        return "runtime output"
    if any(marker in path.name.lower() for marker in (".db-", ".sqlite-", ".sqlite3-")):
        return "database journal"
    if path.parts[0] == "uploads" and name != "uploads/.gitkeep":
        return "user upload"
    return None


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    )
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    problems = []
    python_files = 0
    for name in names:
        reason = path_problem(name)
        if reason:
            problems.append(f"{name}: {reason}")
        if name.endswith(".py"):
            python_files += 1
            try:
                ast.parse((ROOT / name).read_text(encoding="utf-8-sig"), filename=name)
            except (SyntaxError, UnicodeError, OSError) as error:
                problems.append(f"{name}: {type(error).__name__}")
    if problems:
        print("Repository checks failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"Repository checks passed: {len(names)} tracked paths; {python_files} Python files parsed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
