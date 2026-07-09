"""Tests for TranscriptionClient."""

import json
import os
import socket
from unittest import mock

import pytest

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
