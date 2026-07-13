"""DeepgramStreamingClient — async streaming STT via Deepgram WebSocket.

Connects to the Deepgram API, streams raw PCM audio, and accumulates
final transcript segments.  Returns concatenated text when stopped.
"""

import asyncio
import json
import logging

import websockets
import websockets.exceptions

import config

logger = logging.getLogger(__name__)


class DeepgramStreamingClient:
    """Stream audio to Deepgram and collect final transcripts.

    Usage::

        client = DeepgramStreamingClient()
        await client.connect()
        await client.feed_audio_async(pcm_chunk)
        text = await client.stop_and_get_text()
    """

    def __init__(self, api_key=None, model=None, endpoint=None):
        self.api_key = api_key or config.DEEPGRAM_API_KEY
        self.model = model or config.DEEPGRAM_MODEL
        self.endpoint = endpoint or config.DEEPGRAM_ENDPOINT
        self._buffer = []
        self._ws = None
        self._receiver_task = None

    # ── public API ─────────────────────────────────────────────────

    async def connect(self):
        """Open the Deepgram WebSocket and start listening for results."""
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY is not set")

        params = (
            f"encoding=linear16&sample_rate=16000&channels=1"
            f"&model={self.model}"
        )
        url = f"{self.endpoint}?{params}"

        try:
            self._ws = await websockets.connect(
                url,
                additional_headers={
                    "Authorization": f"Token {self.api_key}",
                },
            )
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to Deepgram: {exc}"
            ) from exc

        self._receiver_task = asyncio.create_task(self._receive_loop())

    async def feed_audio_async(self, audio_chunk: bytes):
        """Send a chunk of raw PCM audio over the WebSocket."""
        if not self._ws:
            raise RuntimeError("Not connected.  Call connect() first.")
        await self._ws.send(audio_chunk)

    async def stop_and_get_text(self) -> str:
        """Close the stream, drain remaining results, return final text."""
        if not self._ws:
            raise RuntimeError("Not connected.  Call connect() first.")

        await self._ws.send(json.dumps({"type": "CloseStream"}))

        if self._receiver_task:
            try:
                await self._receiver_task
            except Exception:
                pass

        await self._ws.close()
        self._ws = None

        return " ".join(self._buffer)

    # ── internal ──────────────────────────────────────────────────

    async def _receive_loop(self):
        """Continuously read WebSocket messages; buffer final transcripts."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                if data.get("type") != "Results":
                    continue
                if not data.get("is_final"):
                    continue

                channel = data.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if not alternatives:
                    continue

                transcript = alternatives[0].get("transcript", "").strip()
                if transcript:
                    self._buffer.append(transcript)

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as exc:
            logger.warning("Deepgram receive loop error: %s", exc)
