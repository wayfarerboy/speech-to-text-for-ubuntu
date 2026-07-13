"""Tests for DeepgramStreamingClient."""

import asyncio
import json
from unittest import mock

import pytest

import config
from deepgram_streaming_client import DeepgramStreamingClient


# ── helpers ────────────────────────────────────────────────────────────

class _MockWebSocket:
    """Simulates a websockets.WebSocketClientProtocol for testing."""

    def __init__(self, messages=None):
        self.sent = []
        self.closed = False
        self._messages = list(messages or [])
        self._index = 0

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg


def _make_results_msg(transcript, is_final=True):
    """Build a Deepgram Results JSON string."""
    return json.dumps({
        "type": "Results",
        "channel_index": [0],
        "duration": 1.0,
        "start": 0.0,
        "is_final": is_final,
        "speech_final": is_final,
        "channel": {
            "alternatives": [
                {
                    "transcript": transcript,
                    "confidence": 0.95,
                    "words": [],
                }
            ]
        },
    })


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ── config ─────────────────────────────────────────────────────────────

class TestConfig:
    def test_config_entries_exist(self):
        """All Deepgram config entries are present."""
        assert hasattr(config, "DEEPGRAM_API_KEY")
        assert hasattr(config, "DEEPGRAM_MODEL")
        assert hasattr(config, "DEEPGRAM_ENDPOINT")

    def test_streaming_enabled_when_api_key_set(self, monkeypatch):
        """STREAMING_ENABLED returns True when API key is non-empty."""
        monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "sk-abc123")
        assert config.streaming_enabled() is True

    def test_streaming_disabled_when_api_key_empty(self, monkeypatch):
        """STREAMING_ENABLED returns False when API key is empty."""
        monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "")
        assert config.streaming_enabled() is False


# ── connect ────────────────────────────────────────────────────────────

class TestConnect:
    def test_connect_uses_correct_encoding_params(self):
        """Connect URL includes linear16, 16kHz, mono, and model."""
        ws = _MockWebSocket()
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect) as m:
            _run(client.connect())

        m.assert_called_once()
        url = m.call_args[0][0]
        assert "encoding=linear16" in url
        assert "sample_rate=16000" in url
        assert "channels=1" in url
        assert "model=nova-2" in url

    def test_connect_sends_auth_header(self):
        """Authorization header contains the API key."""
        ws = _MockWebSocket()
        client = DeepgramStreamingClient(api_key="sk-secret")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect) as m:
            _run(client.connect())

        headers = m.call_args[1].get("additional_headers", {})
        assert headers.get("Authorization") == "Token sk-secret"

    def test_connect_raises_on_no_api_key(self):
        """connect raises ValueError when API key is empty."""
        client = DeepgramStreamingClient(api_key="")
        with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
            _run(client.connect())

    def test_connect_wraps_connection_error(self):
        """Connection failures raise ConnectionError."""
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(*args, **kwargs):
            raise OSError("network down")

        with mock.patch("websockets.connect", side_effect=_connect):
            with pytest.raises(ConnectionError, match="Failed to connect"):
                _run(client.connect())


# ── feed_audio_async ───────────────────────────────────────────────────

class TestFeedAudio:
    def test_feed_audio_sends_binary_data(self):
        """feed_audio_async sends raw PCM bytes over the WebSocket."""
        ws = _MockWebSocket()
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        _run(client.feed_audio_async(b"\x00\x01\x02\x03"))
        assert ws.sent == [b"\x00\x01\x02\x03"]

    def test_feed_audio_raises_when_not_connected(self):
        """feed_audio_async raises RuntimeError before connect."""
        client = DeepgramStreamingClient(api_key="test-key")
        with pytest.raises(RuntimeError, match="Not connected"):
            _run(client.feed_audio_async(b"\x00\x01"))


# ── transcript accumulation ────────────────────────────────────────────

class TestTranscriptAccumulation:
    def test_accumulates_final_transcripts(self):
        """Only is_final=true transcripts are added to the buffer."""
        ws = _MockWebSocket(messages=[
            _make_results_msg("hello", is_final=True),
            _make_results_msg("world", is_final=True),
        ])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        text = _run(client.stop_and_get_text())
        assert text == "hello world"

    def test_ignores_interim_results(self):
        """is_final=false transcripts are NOT added to the buffer."""
        ws = _MockWebSocket(messages=[
            _make_results_msg("hel", is_final=False),
            _make_results_msg("hello", is_final=True),
        ])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        text = _run(client.stop_and_get_text())
        assert text == "hello"

    def test_skips_empty_transcripts(self):
        """Final transcripts that are empty/whitespace are skipped."""
        ws = _MockWebSocket(messages=[
            _make_results_msg("  ", is_final=True),
            _make_results_msg("hello", is_final=True),
        ])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        text = _run(client.stop_and_get_text())
        assert text == "hello"

    def test_ignores_non_results_messages(self):
        """Non-Results type messages are ignored."""
        ws = _MockWebSocket(messages=[
            json.dumps({"type": "UtteranceEnd"}),
            _make_results_msg("hello", is_final=True),
        ])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        text = _run(client.stop_and_get_text())
        assert text == "hello"

    def test_ignores_malformed_json(self):
        """Malformed JSON messages are silently skipped."""
        ws = _MockWebSocket(messages=[
            "not valid json{{{",
            _make_results_msg("hello", is_final=True),
        ])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        text = _run(client.stop_and_get_text())
        assert text == "hello"


# ── stop_and_get_text ──────────────────────────────────────────────────

class TestStopAndGetText:
    def test_stop_sends_close_stream(self):
        """stop_and_get_text sends a CloseStream JSON message."""
        ws = _MockWebSocket(messages=[])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        _run(client.stop_and_get_text())
        close_msg = json.loads(ws.sent[-1])
        assert close_msg == {"type": "CloseStream"}

    def test_stop_closes_websocket(self):
        """stop_and_get_text closes the WebSocket connection."""
        ws = _MockWebSocket(messages=[])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        _run(client.stop_and_get_text())
        assert ws.closed is True

    def test_stop_returns_empty_for_no_transcripts(self):
        """Returns empty string when no transcripts were received."""
        ws = _MockWebSocket(messages=[])
        client = DeepgramStreamingClient(api_key="test-key")

        async def _connect(url, **kwargs):
            return ws

        with mock.patch("websockets.connect", side_effect=_connect):
            _run(client.connect())

        text = _run(client.stop_and_get_text())
        assert text == ""

    def test_stop_raises_when_not_connected(self):
        """stop_and_get_text raises RuntimeError before connect."""
        client = DeepgramStreamingClient(api_key="test-key")
        with pytest.raises(RuntimeError, match="Not connected"):
            _run(client.stop_and_get_text())


# ── constructor ────────────────────────────────────────────────────────

class TestConstructor:
    def test_defaults_from_config(self):
        """Constructor uses config values when not overridden."""
        client = DeepgramStreamingClient()
        assert client.api_key == config.DEEPGRAM_API_KEY
        assert client.model == config.DEEPGRAM_MODEL
        assert client.endpoint == config.DEEPGRAM_ENDPOINT

    def test_accepts_custom_values(self):
        """Constructor accepts custom api_key, model, endpoint."""
        client = DeepgramStreamingClient(
            api_key="custom-key",
            model="custom-model",
            endpoint="wss://custom.endpoint/v1/listen",
        )
        assert client.api_key == "custom-key"
        assert client.model == "custom-model"
        assert client.endpoint == "wss://custom.endpoint/v1/listen"
