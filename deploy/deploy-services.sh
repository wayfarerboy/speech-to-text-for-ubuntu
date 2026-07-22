#!/usr/bin/env bash
# deploy-services.sh — install and enable systemd services for speech-to-text.
#
# Safe to re-run (idempotent).  Run as your normal user — no root needed
# (key_listener uses evdev via 'input' group membership).
#
# Usage:
#   chmod +x deploy/deploy-services.sh
#   ./deploy/deploy-services.sh
#
# Prerequisites:
#   - Project cloned to a permanent location
#   - Python venv created at ~/.venv with requirements installed
#   - User must be in the 'input' group for evdev access (run: sudo usermod -a -G input $USER)

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
systemctl --user restart stt-server.service
echo "==> stt-server.service enabled and started"

# ── user service: key listener ────────────────────────────────────────

cat > "$SYSTEMD_USER_DIR/stt-keylistener.service" <<EOF
[Unit]
Description=Speech-to-text key listener
After=graphical-session.target

[Service]
ExecStart=$VENV_PYTHON $PROJECT_DIR/servers/key_listener.py
Restart=always
RestartSec=5
SupplementaryGroups=input

[Install]
WantedBy=default.target
EOF

echo "==> Wrote $SYSTEMD_USER_DIR/stt-keylistener.service"

systemctl --user daemon-reload
systemctl --user restart stt-keylistener.service
echo "==> stt-keylistener.service deployed and restarted"

echo ""
echo "Done. Both services are running."
echo "Check status:"
echo "  systemctl --user status stt-server"
echo "  systemctl --user status stt-keylistener"
echo "Logs:"
echo "  journalctl --user -u stt-server -f"
echo "  journalctl --user -u stt-keylistener -f"
