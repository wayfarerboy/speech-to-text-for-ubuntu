#!/usr/bin/env bash
# deploy-services.sh — install and enable systemd services for speech-to-text.
#
# Safe to re-run (idempotent).  Run as your normal user — sudo is prompted
# for the system-level key-listener unit.
#
# Usage:
#   chmod +x deploy/deploy-services.sh
#   ./deploy/deploy-services.sh
#
# Prerequisites:
#   - Project cloned to a permanent location
#   - Python venv created at ~/.venv with requirements installed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
USER_HOME="$HOME"
VENV_PYTHON="${USER_HOME}/.venv/bin/python3"

echo "==> Project : $PROJECT_DIR"
echo "==> User    : $USER"
echo "==> Venv    : $VENV_PYTHON"

# ── user service: speech-to-text server ────────────────────────────────

SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

cat > "$SYSTEMD_USER_DIR/stt-server.service" <<EOF
[Unit]
Description=Speech-to-text server
After=network.target

[Service]
ExecStart=$VENV_PYTHON $PROJECT_DIR/servers/speech_to_text_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

echo "==> Wrote $SYSTEMD_USER_DIR/stt-server.service"

systemctl --user daemon-reload
systemctl --user enable --now stt-server.service
echo "==> stt-server.service enabled and started"

# ── system service: key listener ──────────────────────────────────────

SYSTEMD_SYSTEM_DIR="/etc/systemd/system"
SYSTEM_PYTHON="/usr/bin/python3"

sudo tee "$SYSTEMD_SYSTEM_DIR/stt-keylistener.service" > /dev/null <<EOF
[Unit]
Description=Speech-to-text key listener
After=multi-user.target

[Service]
ExecStart=$SYSTEM_PYTHON $PROJECT_DIR/servers/key_listener.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "==> Wrote $SYSTEMD_SYSTEM_DIR/stt-keylistener.service"

sudo systemctl daemon-reload
sudo systemctl enable --now stt-keylistener.service
echo "==> stt-keylistener.service enabled and started"

echo ""
echo "Done. Both services are running."
echo "Check status:"
echo "  systemctl --user status stt-server"
echo "  systemctl status stt-keylistener"
echo "Logs:"
echo "  journalctl --user -u stt-server -f"
echo "  sudo journalctl -u stt-keylistener -f"
