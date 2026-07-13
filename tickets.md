# Tickets: Deepen architecture

Consolidate scattered config, extract deep modules from shallow scripts, and make the codebase testable at module interfaces. See `.scratch/speech-to-text-system/PRD.md` for the full system spec.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

## 1. Single configuration module

**What to build:** A `config.py` module that all three scripts import instead of ~25 module-level globals. The push-to-talk workflow continues to work end-to-end. Tests can swap config in one place instead of monkeypatching per-file globals.

**Blocked by:** None — can start immediately.

- [x] `config.py` exists with sections for key_listener, server, and client
- [x] `key_listener.py` imports config instead of its own globals
- [x] `speech_to_text_server.py` imports config instead of its own globals
- [x] `speech_to_text_client.py` imports config instead of its own globals
- [x] All existing tests pass
- [x] End-to-end push-to-talk still works

## 2. Extract TranscriptionClient + TextTyper

**What to build:** `TranscriptionClient` module with a single-method interface `transcribe(audio_path, language) → str` that encapsulates socket communication and JSON protocol. `TextTyper` module with `type(text)` that handles xdotool typing, clipboard copy, and modifier cleanup. `key_listener.py` imports and calls both. Each has isolated tests — socket tests use a socketpair fake, typing tests mock subprocess.

**Blocked by:** 1. Single configuration module

- [x] `TranscriptionClient` class with `transcribe(path, lang) → str`
- [x] `TextTyper` class with `type(text)`
- [x] `key_listener.py` uses both instead of subprocess.run to the client script
- [x] `scripts/speech_to_text_client.py` becomes a thin CLI wrapper around both modules
- [x] TranscriptionClient tests: socket round-trip, missing file raises, error response propagates
- [x] TextTyper tests: xdotool args correct, space appended, clipboard selected by env, empty text no-ops
- [x] All existing tests pass
- [x] End-to-end push-to-talk still works

## 3. Collapse key listener into PushToTalkSession

**What to build:** `PushToTalkSession` module with `start(language)` / `stop() → audio_path` interface. Recording state machine, arecord lifecycle, and busy flag live inside. Device reading (evdev) and indicator display become swappable adapters injected at construction. Session state is tested with fake adapters — no real /dev/input hardware needed. The main() in key_listener becomes thin glue: wire real adapters, run the session.

**Blocked by:** 1. Single configuration module, 2. Extract TranscriptionClient + TextTyper

- [x] `PushToTalkSession` class with `start(lang)` / `stop() → path`
- [x] `EvdevAdapter` interface for key events (real implementation reads /dev/input/event*) — evdev stays inline in main(); session tested with fake adapters injected
- [x] `IndicatorAdapter` interface with `show(mode)` / `hide()` (real implementation spawns tkinter)
- [x] `key_listener.py` main() wires real adapters and runs the session
- [x] Session state tests: start→recording→stop→idle transitions, double-start blocked, key-up before key-down safe
- [x] Session integration test with fake adapters: start, simulate key-up, verify stop returns audio path
- [x] All existing tests pass
- [x] End-to-end push-to-talk still works

---

## Separate coordinator

These tickets split the key listener into a non-blocking recording loop that spawns a separate coordinator process for transcription and typing. The coordinator runs as the desktop user (not root). All were completed via GitHub Issues #1–#7.

### Hardened modules: timeouts + clipboard fallback (GH #1)

**What:** `TextTyper.type()` and `TranscriptionClient.transcribe()` get configurable timeouts. xdotool hangs → kill + clipboard fallback. Socket connect times out.

- [x] TextTyper timeout + clipboard fallback (5s default)
- [x] TranscriptionClient socket timeout (10s default)
- [x] Both log warnings, never crash the caller

### Refactor key_listener to spawn coordinator (GH #2)

**What:** Key-up spawns `stt_coordinator.py` as desktop user, key_listener returns to listening immediately. PushToTalkSession slimmed to recording-only.

- [x] Non-blocking coordinator spawn with privilege dropping
- [x] PushToTalkSession recording-only — no TranscriptionClient/TextTyper references
- [x] Rapid successive key presses handled
- [x] Coordinator failures don't affect key_listener

### Cleanup: remove dead code (GH #3)

**What:** Remove `speech_to_text_client.py` (superseded by coordinator), update docs, verify no dead imports.

- [x] `speech_to_text_client.py` removed
- [x] `tests/test_client.py` removed
- [x] README and docstrings updated
- [x] All existing tests pass

### Coordinator script (GH #4)

**What:** `scripts/stt_coordinator.py` — CLI that transcribes via socket, types via TextTyper, hides indicator.

- [x] `stt_coordinator.py <audio> --language <lang> --indicator-pid <pid>` works
- [x] Transcribes via TranscriptionClient, types via TextTyper
- [x] Sends SIGTERM to indicator PID
- [x] Exits 0 on success, non-zero on failure

### Systemd auto-restart units (GH #5)

**What:** systemd user unit for STT server, system unit for key listener, both with `Restart=always`.

- [x] `stt-server.service` (user) with auto-restart
- [x] `stt-keylistener.service` (system) with graphical session dependency
- [x] Deploy script idempotent

### Deepgram streaming client & config (GH #6)

**What:** `DeepgramStreamingClient` connects to Deepgram WebSocket, streams raw PCM, returns concatenated final transcript.

- [x] `DeepgramStreamingClient` with `feed_audio_async()` and `stop_and_get_text()`
- [x] Config entries for API key, model, endpoint
- [x] `websockets` added to requirements.txt
- [x] Mocked WebSocket unit tests verify buffer accumulation and stop behaviour

### Streaming session + key listener wiring + fallback (GH #7)

**What:** `PushToTalkSessionStreaming` uses FIFO + arecord → Deepgram WebSocket. Falls back to local transcription on failure.

- [x] `PushToTalkSessionStreaming` manages FIFO, arecord, Deepgram lifecycle
- [x] Transcript buffer accumulates during recording, flushes on stop
- [x] Key listener auto-selects Deepgram when `DEEPGRAM_API_KEY` is set
- [x] Deepgram connection failure → local transcription fallback
- [x] FIFO cleaned up after each session
