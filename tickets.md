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

- [ ] `PushToTalkSession` class with `start(lang)` / `stop() → path`
- [ ] `EvdevAdapter` interface for key events (real implementation reads /dev/input/event*)
- [ ] `IndicatorAdapter` interface with `show(mode)` / `hide()` (real implementation spawns tkinter)
- [ ] `key_listener.py` main() wires real adapters and runs the session
- [ ] Session state tests: start→recording→stop→idle transitions, double-start blocked, key-up before key-down safe
- [ ] Session integration test with fake adapters: start, simulate key-up, verify stop returns audio path
- [ ] All existing tests pass
- [ ] End-to-end push-to-talk still works
