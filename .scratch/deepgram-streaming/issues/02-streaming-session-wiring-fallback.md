# 02 — Streaming session + key listener wiring + fallback

**What to build:** A streaming variant of PushToTalkSession that uses a FIFO instead of a WAV file — `arecord` writes raw PCM to the FIFO, which is bridged into the Deepgram WebSocket live. Transcripts accumulate in the buffer during recording; nothing is typed until key release. On key-up, the stream stops, the buffer flushes, and TextTyper types the result.

The key listener auto-selects Deepgram streaming when `DEEPGRAM_API_KEY` is set. If the key is missing or the Deepgram stream fails, it falls back to the existing local TranscriptionClient (faster-whisper over Unix socket).

End-to-end behaviour: hold F16, speak, release — text appears typed into the focused application, same as today but faster when using Deepgram.

**Blocked by:** #01 — Deepgram streaming client & config

**Status:** ready-for-agent
**GitHub:** [#7](https://github.com/wayfarerboy/speech-to-text-for-ubuntu/issues/7)

- [ ] `PushToTalkSessionStreaming` manages FIFO creation, `arecord` spawning to FIFO, and Deepgram streaming lifecycle
- [ ] Transcript buffer accumulates during recording; no typing or clipboard copy until `stop()` is called
- [ ] On `stop()`: recording terminates, Deepgram stream drains, final text is typed via TextTyper and copied to clipboard
- [ ] Recording indicator shows spectrogram during recording, processing animation during stream drain
- [ ] Key listener selects backend: Deepgram when `DEEPGRAM_API_KEY` is set, local TranscriptionClient otherwise
- [ ] On Deepgram connection failure mid-stream: falls back to local transcription for that utterance
- [ ] FIFO is cleaned up after each session
- [ ] Unit tests: verify state machine (start → recording → stop → typing), buffer accumulation, fallback path
- [ ] `requirements.txt` updated if any new system deps are needed beyond `websockets` (from #01)
