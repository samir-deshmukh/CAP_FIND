#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CET_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$HOME/.venvs/capfind-local-worker"
STATE_DIR="$HOME/.local/state/capfind-local-worker"
LOG_FILE="$STATE_DIR/worker.log"
PID_FILE="$STATE_DIR/worker.pid"
mkdir -p "$STATE_DIR"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Local worker environment is missing. Create it with:"
  echo "  python3 -m venv \"$VENV\""
  echo "  \"$VENV/bin/python\" -m pip install -r \"$CET_DIR/requirements-dev.txt\""
  exit 1
fi
if systemctl --user is-enabled capfind-local-worker.service >/dev/null 2>&1; then
  systemctl --user start capfind-local-worker.service
  for _ in $(seq 1 30); do
    if curl --silent --fail http://127.0.0.1:8765/health >/dev/null 2>&1; then
      echo "CAPFind local worker is running as a managed user service."
      exit 0
    fi
    sleep 0.25
  done
  systemctl --user status capfind-local-worker.service --no-pager || true
  exit 1
fi
if curl --silent --fail http://127.0.0.1:8765/health >/dev/null 2>&1; then
  echo "CAPFind local worker is already running at 127.0.0.1:8765."
  exit 0
fi
cd "$CET_DIR"
nohup "$VENV/bin/python" -m backend.local_worker >>"$LOG_FILE" 2>&1 </dev/null &
echo $! > "$PID_FILE"
for _ in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:8765/health >/dev/null 2>&1; then
    echo "CAPFind local worker started in the background."
    echo "Log: $LOG_FILE"
    exit 0
  fi
  sleep 0.25
done
echo "Worker did not start. Recent log:"
tail -60 "$LOG_FILE" || true
exit 1
