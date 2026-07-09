# Map: Separate Coordinator

## Decisions so far

- Per-press coordinator (short-lived), not long-lived worker — 100ms startup absorbed into transcription time
- Coordinator runs as user, not root
- Coordinator owns transcription + typing in one process (timeout + clipboard handles input failure)
- xdotool with 5s timeout, clipboard fallback on failure, no retry
- Systemd: two independent Restart=always units

## Fog

- None yet
