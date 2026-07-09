# 03 — Coordinator script

**Type:** task
**Status:** needs-triage
**Blocked by:** 02 (timeouts and fallback must exist before coordinator uses them)

## What to build

A new `scripts/stt_coordinator.py` that accepts audio file path, language, and indicator PID as CLI arguments. It transcribes via `TranscriptionClient`, signals the indicator to hide (SIGTERM), then types via `TextTyper`. Run as the desktop user, not root. Demoable from the command line against any WAV file the STT server can read.

## Acceptance criteria

- [ ] `scripts/stt_coordinator.py <audio_file> --language <lang> --indicator-pid <pid>` runs end-to-end
- [ ] Transcribes via STT server socket (existing TranscriptionClient)
- [ ] After transcription, sends SIGTERM to indicator PID (hide)
- [ ] Types result via TextTyper (with timeout + clipboard fallback from ticket 02)
- [ ] Exits cleanly on success, non-zero on failure
- [ ] Runs correctly when invoked as the desktop user (subprocess user= switch from key_listener)
