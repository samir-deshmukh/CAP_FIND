"""Lightweight local guard against accidentally committing obvious secrets.

This is a defense-in-depth check; GitHub secret scanning/push protection remains
important because it can detect provider-specific credentials and scan history.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".md", ".txt", ".toml",
    ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf", ".sql", ".sh"
}
PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-./+=]{16,}['\"]"),
    re.compile(r"(?i)postgres(?:ql)?://[^\s/'\"]+:[^\s/'\"]+@"),
    re.compile(r"(?i)\b(?:password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}['\"]"),
]
findings: list[str] = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):
        continue
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for pattern in PATTERNS:
        if pattern.search(text):
            findings.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")

if findings:
    print("Potential secret(s) detected:")
    print("\n".join(findings))
    raise SystemExit(1)

print("Secret guard: PASS")
