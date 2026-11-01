#!/usr/bin/env bash
set -euo pipefail
PID_FILE="$HOME/.local/state/capfind-local-worker/worker.pid"
if systemctl --user is-active --quiet capfind-local-worker.service 2>/dev/null; then
  systemctl --user stop capfind-local-worker.service
  if systemctl --user is-enabled capfind-local-worker.service >/dev/null 2>&1; then
    echo "CAPFind worker stopped. It will start again at the next login."
  else
    echo "CAPFind worker stopped."
  fi
  exit 0
fi
if [[ ! -f "$PID_FILE" ]]; then
  echo "No CAPFind local worker PID file found."
  exit 0
fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in $(seq 1 20); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.25
  done
fi
rm -f "$PID_FILE"
echo "CAPFind local worker stop requested."
