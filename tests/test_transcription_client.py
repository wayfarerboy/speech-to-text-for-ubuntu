"""Tests for TranscriptionClient."""

import json
import logging
import os
import socket
from unittest import mock

import pytest

import config
from transcription_client import TranscriptionClient


# ── transcribe ─────────────────────────────────────────────────────────

class TestTranscribe:
    def test_returns_text_on_ok_response(self):
        """Round-trip: send request, receive ok response, get text."""
        parent, child = socket.socketpair()
        try:
            client = TranscriptionClient(socket_path=None)
            with mock.patch.object(client, "_connect", return_value=child), \
                 mock.patch.object(os.path, "exists", return_value=True):
                response = {
                    "ok": True,
                    "text": "hello world",
                    "segments": ["hello", "world"],
                }

                def _serve():
                    data = b""
                    while True:
                        chunk = parent.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    req = json.loads(data)
                    assert req["audio_file"] == "/tmp/test.wav"
                    assert req["language"] == "en"
                    parent.sendall(json.dumps(response).encode())
                    parent.close()

                import threading
                t = threading.Thread(target=_serve)
                t.start()

                result = client.transcribe("/tmp/test.wav", "en")
                assert result == "hello world"
                t.join()
        finally:
            parent.close()
            child.close()

    def test_raises_on_missing_file(self):
        """transcribe raises FileNotFoundError for nonexistent audio."""
        client = TranscriptionClient()
        with pytest.raises(FileNotFoundError, match="not found"):
            client.transcribe("/nonexistent/path.wav")

    def test_raises_on_error_response(self):
        """transcribe raises RuntimeError when server returns ok=False."""
        parent, child = socket.socketpair()
        try:
            client = TranscriptionClient(socket_path=None)
            with mock.patch.object(client, "_connect", return_value=child), \
                 mock.patch.object(os.path, "exists", return_value=True):
                response = {"ok": False, "error": "Model not loaded"}

                def _serve():
                    data = b""
                    while True:
                        chunk = parent.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    parent.sendall(json.dumps(response).encode())
                    parent.close()

                import threading
                t = threading.Thread(target=_serve)
                t.start()

                with pytest.raises(RuntimeError, match="Model not loaded"):
                    client.transcribe("/tmp/test.wav")
                t.join()
        finally:
            parent.close()
            child.close()

    def test_uses_configured_socket_path(self):
        """TranscriptionClient uses the socket_path from config by default."""
        client = TranscriptionClient()
        assert client.socket_path == "/tmp/stt_server.sock"

    def test_accepts_custom_socket_path(self):
        """TranscriptionClient accepts a custom socket_path."""
        client = TranscriptionClient(socket_path="/custom/path.sock")
        assert client.socket_path == "/custom/path.sock"

    def test_default_language_is_en(self):
        """When language is omitted, default to 'en'."""
        parent, child = socket.socketpair()
        try:
            client = TranscriptionClient(socket_path=None)
            with mock.patch.object(client, "_connect", return_value=child), \
                 mock.patch.object(os.path, "exists", return_value=True):
                response = {"ok": True, "text": "hello", "segments": ["hello"]}

                def _serve():
                    data = b""
                    while True:
                        chunk = parent.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    req = json.loads(data)
                    assert req["language"] == "en"
                    parent.sendall(json.dumps(response).encode())
                    parent.close()

                import threading
                t = threading.Thread(target=_serve)
                t.start()

                result = client.transcribe("/tmp/test.wav")
                assert result == "hello"
                t.join()
        finally:
            parent.close()
            child.close()

    def test_handles_connection_refused(self):
        """transcribe wraps socket errors in RuntimeError."""
        client = TranscriptionClient(socket_path="/nonexistent/socket.sock")
        with mock.patch.object(os.path, "exists", return_value=True), \
             mock.patch.object(client, "_connect",
                               side_effect=ConnectionRefusedError("refused")):
            with pytest.raises(RuntimeError, match="Connection failed"):
                client.transcribe("/tmp/test.wav")

    def test_strips_text(self):
        """Returned text is whitespace-stripped."""
        parent, child = socket.socketpair()
        try:
            client = TranscriptionClient(socket_path=None)
            with mock.patch.object(client, "_connect", return_value=child), \
                 mock.patch.object(os.path, "exists", return_value=True):
                response = {"ok": True, "text": "  hello world  ",
                            "segments": ["hello", "world"]}

                def _serve():
                    data = b""
                    while True:
                        chunk = parent.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    parent.sendall(json.dumps(response).encode())
                    parent.close()

                import threading
                t = threading.Thread(target=_serve)
                t.start()

                result = client.transcribe("/tmp/test.wav", "en")
                assert result == "hello world"
                t.join()
        finally:
            parent.close()
            child.close()


# ── timeout ────────────────────────────────────────────────────────────

class TestTimeout:
    def test_uses_configured_timeout(self):
        """TranscriptionClient uses TRANSCRIPTION_TIMEOUT from config by default."""
        client = TranscriptionClient()
        assert client.timeout == config.TRANSCRIPTION_TIMEOUT

    def test_accepts_custom_timeout(self):
        """TranscriptionClient accepts a custom timeout."""
        client = TranscriptionClient(timeout=5)
        assert client.timeout == 5

    def test_socket_connect_timeout_logs_warning(self, caplog):
        """Socket connect timeout logs a warning and propagates as RuntimeError."""
        client = TranscriptionClient(socket_path="/tmp/stt_server.sock", timeout=1)
        with mock.patch.object(os.path, "exists", return_value=True), \
             mock.patch.object(client, "_connect",
                               side_effect=socket.timeout("timed out")):
            with caplog.at_level(logging.WARNING):
                with pytest.raises(RuntimeError, match="Connection timed out"):
                    client.transcribe("/tmp/test.wav")
        assert any("timeout" in r.message.lower() or "timed out" in r.message.lower()
                   for r in caplog.records)

    def test_socket_sets_timeout_before_connect(self):
        """_connect sets socket timeout before calling connect."""
        client = TranscriptionClient(timeout=3)
        mock_sock = mock.MagicMock()
        mock_sock.connect.side_effect = OSError("no such file")
        with mock.patch("socket.socket", return_value=mock_sock):
            with pytest.raises(OSError):
                client._connect()
        mock_sock.settimeout.assert_called_once_with(3)
