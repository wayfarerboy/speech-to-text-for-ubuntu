# 01 — Systemd auto-restart units

**Type:** task
**Status:** needs-triage
**Blocked by:** None — can start immediately

## What to build

Two systemd user units (`stt-key-listener.service` and `stt-server.service`) with `Restart=always`. Both survive process crashes and system reboots. The key_listener unit waits for the graphical session to be ready before starting.

## Acceptance criteria

- [ ] `stt-server.service` starts the STT server, restarts it if it crashes
- [ ] `stt-key-listener.service` starts the key_listener (root, so may need a system unit or pkexec), restarts it if it crashes
- [ ] `systemctl --user enable stt-server.service` survives reboot
- [ ] Existing cron-based startup instructions in README/docs updated or replaced with systemd instructions
- [ ] Push-to-talk works end-to-end after a `systemctl restart` of both units
