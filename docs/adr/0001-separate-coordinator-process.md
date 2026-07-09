# ADR 0001: Separate Coordinator Process

**Date**: 2026-07-09
**Status**: Accepted

## Context

The key_listener was a monolith: reading `/dev/input` events, spawning `arecord`, calling the STT server, running `xdotool`, and managing the indicator — all in one process, one event loop. Multiple failure modes emerged:

- `xdotool` had no timeout — a hung subprocess froze the entire event loop, dropping all subsequent key presses
- Socket operations to the STT server had no timeout — same freeze risk
- Any crash killed the process; no systemd/cron auto-restart existed
- Transient environment failures (missing XAUTHORITY at boot, input-remapper device not ready) prevented startup entirely

## Decision

Separate the key_listener into two concerns:

1. **Key Listener** (root, long-lived) — only reads `/dev/input` events, manages `arecord` recording, signals the indicator, and spawns coordinators. Never blocks.
2. **Coordinator** (user, short-lived, per key press) — transcribes audio via the STT server and types the result. Spawned on key-up, killed after timeout if it hangs. Returns to clipboard fallback if typing fails.

Systemd units for both `key_listener` and `stt_server` with `Restart=always`.

## Alternatives considered

### Long-lived worker process
Avoids Python startup per key press. Rejected because: if xdotool corrupts the process state (stuck modifiers), detection and recovery is complex. A per-press short-lived process is clean — kill it, spawn fresh next time.

### Coordinator runs as root
Simpler to implement (inherits environment). Rejected because: security boundary is clearer when root only touches `/dev/input` and spawning. All other work runs as the desktop user with natural display access.

### Separate transcription and input workers
Protects transcription from input failures. Rejected because: the coordinator's typing timeout + clipboard fallback achieves the same goal without extra process overhead. Transcription is never re-paid on input failure.

### xdotool replaced by wtype (Wayland-native)
Would solve Wayland typing but the user prefers to keep xdotool and make it resilient rather than switching tools. The timeout + clipboard fallback handles xdotool's failure modes.

## Consequences

- **Positive**: Key listener never blocks — a hung coordinator doesn't drop key presses. Systemd auto-restarts dead processes. Timeouts bound all blocking operations.
- **Negative**: ~100ms Python startup per key press for the coordinator. Absorbed into the 3-30s transcription window.
- **Risk**: xdotool on pure Wayland sessions types into the void (exit 0, no text). Mitigated by clipboard fallback — user can paste manually.
