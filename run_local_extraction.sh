#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
PYTHON="${HOME}/.venvs/capfind-local-worker/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "CAPFind Python environment not found: $PYTHON"
  echo "Create it using cet/requirements-dev.txt first. See local_extraction/README.md."
  exit 2
fi
exec "$PYTHON" scripts/local_folder_extract.py "$@"
