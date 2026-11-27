from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".pytest_cache", "data", "scripts"}
EXTS = {".py", ".js", ".html", ".css", ".vue"}


def main() -> None:
    total = 0
    files = 0
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name == "vue.global.prod.js":
            continue
        if p.suffix.lower() not in EXTS:
            continue
        n = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        total += n
        files += 1
        print(f"{n:5d}  {p.relative_to(ROOT)}")
    print(f"TOTAL {total} lines in {files} files (excl. scripts/vendor)")


if __name__ == "__main__":
    main()
