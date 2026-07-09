# 04 — Refactor key_listener to spawn coordinator

**Type:** task
**Status:** needs-triage
**Blocked by:** 03 (coordinator script must exist)

## What to build

The key_listener event loop is simplified: on key-up it spawns the coordinator subprocess (as the desktop user) and returns to listening immediately — no blocking on transcription or typing. The key_listener no longer imports `TranscriptionClient` or `TextTyper` directly. `PushToTalkSession` is slimmed to recording-only (or replaced inline). Indicator signalling stays in the key_listener (SIGUSR1 on key-down, SIGUSR2 on key-up); the coordinator handles SIGTERM (hide).

## Acceptance criteria

- [ ] Key-down: arecord starts, indicator shows "recording" — same as today
- [ ] Key-up: arecord terminated, indicator shows "processing", coordinator spawned as user
- [ ] Key_listener returns to listening immediately after spawning coordinator (no blocking)
- [ ] Push-to-talk works end-to-end: press F16, speak, release → text appears (or clipboard fallback)
- [ ] Rapid successive key presses work (coordinator from press N runs concurrently with press N+1 recording)
- [ ] Coordinator failures (timeout, crash) do not affect key_listener — next key press spawns fresh coordinator
- [ ] `TranscriptionClient` and `TextTyper` no longer imported in key_listener
