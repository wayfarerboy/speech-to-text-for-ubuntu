# 02 — Hardened modules: timeouts + clipboard fallback

**Type:** task
**Status:** needs-triage
**Blocked by:** None — can start immediately

## What to build

`TextTyper.type()` gets a configurable timeout on the xdotool subprocess call. If xdotool hangs or exits non-zero, text is copied to clipboard (wl-copy / xclip) and a warning is logged — no exception propagates. `TranscriptionClient.transcribe()` gets a configurable timeout on socket connect and receive operations. All existing tests pass; new tests cover timeout and fallback paths.

## Acceptance criteria

- [ ] `TextTyper.type()` spawns xdotool with a timeout (default 5s); `TimeoutExpired` → kill xdotool → clipboard fallback
- [ ] `TextTyper.type()` on xdotool exit ≠ 0 → clipboard fallback
- [ ] `TranscriptionClient.transcribe()` socket connect times out after configurable duration
- [ ] Both log warnings on failure, never crash the caller
- [ ] Clipboard fallback uses wl-copy (Wayland) or xclip (X11) matching existing clipboard detection
- [ ] Unit tests for timeout path (mock slow subprocess), fallback path (mock non-zero exit), and socket timeout
