# 01 — Systemd auto-restart units

**Type:** task
**Status:** done
**Blocked by:** None

## What was built

Two systemd user units (`stt-keylistener.service` and `stt-server.service`) with `Restart=always`. Both survive process crashes and system reboots. The key_listener runs as a user service with `SupplementaryGroups=input` for evdev access (no root needed).

## Acceptance criteria

- [x] `stt-server.service` starts the STT server, restarts it if it crashes
- [x] `stt-keylistener.service` starts the key_listener (user service, `input` group), restarts it if it crashes
- [x] `systemctl --user enable stt-server.service` survives reboot
- [x] Existing cron-based startup instructions in README/docs updated or replaced with systemd instructions
- [x] Push-to-talk works end-to-end after a `systemctl restart` of both units
