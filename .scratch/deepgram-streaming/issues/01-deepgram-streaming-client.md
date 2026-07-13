# 01 — Deepgram streaming client & config

**What to build:** A standalone Deepgram streaming client that connects to the Deepgram API over WebSocket, streams raw PCM audio chunks, accumulates final transcript segments in a buffer (no incremental typing), and returns the concatenated text when stopped. Config entries for API key, model, and endpoint. The `websockets` dependency added to requirements.

The client is independently testable: a script feeds a pre-recorded `.wav` to Deepgram and prints the transcript — no key listener integration needed.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent
**GitHub:** [#6](https://github.com/wayfarerboy/speech-to-text-for-ubuntu/issues/6)

- [ ] `DEEPGRAM_API_KEY`, `DEEPGRAM_MODEL`, and `DEEPGRAM_ENDPOINT` config entries exist, with `STREAMING_ENABLED` auto-enabled when the API key is set
- [ ] `websockets` added to `requirements.txt`
- [ ] `DeepgramStreamingClient` connects to Deepgram WebSocket with correct encoding params (linear16, 16kHz, mono)
- [ ] Audio chunks fed via `feed_audio_async()` are sent over the WebSocket
- [ ] `is_final=true` transcript segments accumulate in a buffer; interim results are ignored
- [ ] `stop_and_get_text()` sends CloseStream, drains remaining responses, returns concatenated final text
- [ ] Client handles connection errors gracefully (no crash, raises descriptive exception)
- [ ] Unit tests: mock WebSocket, verify buffer accumulation, verify stop behaviour
