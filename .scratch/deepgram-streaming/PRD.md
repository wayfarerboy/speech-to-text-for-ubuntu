# Deepgram Streaming Integration — PRD

**Status:** `ready-for-agent`

## Problem

Local faster-whisper transcription is too slow on CPU-only hardware (3–10 seconds per utterance). The user has $200 in Deepgram credit and wants to stream live audio to Deepgram for near-instant transcription while keeping the same push-to-talk workflow.

## Solution

Add Deepgram streaming as an alternative transcription backend. While the key is held, raw PCM audio streams to Deepgram over WebSocket. Transcripts accumulate in a buffer — nothing is typed until key release. On release, the buffer flushes and TextTyper types the result. The existing local TranscriptionClient remains as fallback.

## Architecture

- **DeepgramStreamingClient** — WebSocket client to Deepgram. `start_streaming(language)` / `feed_audio_async(chunk)` / `stop_and_get_text() -> str`. Accumulates only `is_final=true` segments.
- **PushToTalkSessionStreaming** — variant of PushToTalkSession. Uses FIFO instead of WAV: `arecord` writes raw PCM to `/tmp/stt_audio_fifo`, which is read and forwarded to the Deepgram WebSocket.
- **Key listener** — selects backend based on `DEEPGRAM_API_KEY` presence. Falls back to local TranscriptionClient if streaming fails.

## Out of scope

- Incremental typing during recording — buffer only, type on release
- Deepgram interim results display
- Model selection beyond single configured model
