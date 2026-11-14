import os
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pattern = re.compile(r'os\.(?:getenv|environ\.get|environ\[)[\(\[\'\"]+([A-Za-z0-9_]+)')
results = {}

for p in root.rglob('*.py'):
    rel = p.relative_to(root).as_posix()
    if any(part in p.parts for part in ['.git', '.venv', '__pycache__', 'node_modules', '.pytest_cache']):
        continue
    try:
        content = p.read_text(encoding='utf-8', errors='ignore')
        matches = pattern.findall(content)
        for m in matches:
            results.setdefault(m, set()).add(rel)
    except Exception:
        pass

for k in sorted(results.keys()):
    files = ', '.join(sorted(results[k]))
    print(f'{k} -> {files}')
