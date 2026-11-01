#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CET_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$HOME/.venvs/capfind-local-worker"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/capfind-local-worker.service"
ENV_DIR="$HOME/.config/capfind"
ENV_FILE="$ENV_DIR/local-worker.env"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Local worker environment is missing: $VENV/bin/python" >&2
  exit 1
fi

mkdir -p "$UNIT_DIR" "$ENV_DIR"
chmod 700 "$ENV_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<'EOF'
# Set this to the exact same random value as Render's CAPFIND_REMOTE_WORKER_TOKEN.
CAPFIND_REMOTE_WORKER_TOKEN=
CAPFIND_BACKEND_URL=https://cetfind.onrender.com
EOF
  chmod 600 "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

cat >"$UNIT_FILE" <<EOF
[Unit]
Description=CAPFind PDF extraction worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$CET_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$VENV/bin/python -m backend.local_worker
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user stop capfind-local-worker.service 2>/dev/null || true
systemctl --user enable --now capfind-local-worker.service
echo "Installed and enabled the CAPFind worker user service."
echo "Worker environment: $ENV_FILE (permissions set to owner-only when first created)."
echo "Set the shared token there and in Render, then restart with: systemctl --user restart capfind-local-worker.service"
