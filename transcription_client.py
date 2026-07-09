"""TranscriptionClient — send audio to the speech-to-text server over a Unix socket."""

import json
import os
import socket

import config


class TranscriptionClient:
    """Client for the speech-to-text Unix socket server.

    Interface: ``transcribe(audio_path, language) -> str``.
    """

    def __init__(self, socket_path=None):
        self.socket_path = socket_path or config.SOCKET_PATH

    def transcribe(self, audio_path, language="en"):
        """Send an audio file to the server and return the transcript text.

        Args:
            audio_path: Absolute path to a WAV file the server can read.
            language: ISO 639-1 language code (default ``"en"``).

        Returns:
            The transcribed text, whitespace-stripped.

        Raises:
            FileNotFoundError: If *audio_path* does not exist.
            RuntimeError: If the server returns an error or the connection fails.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        language = (language or "en").strip().lower()
        req = {"audio_file": audio_path, "language": language}

        sock = None
        try:
            sock = self._connect()
            sock.sendall(json.dumps(req).encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            resp = self._recv_json(sock)
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Connection failed: {e}") from e
        finally:
            if sock:
                sock.close()

        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "Unknown server error"))

        return resp.get("text", "").strip()

    # ── internal ──────────────────────────────────────────────────

    def _connect(self):
        """Open a new Unix socket connection.  Overridable for tests."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.socket_path)
        return sock

    @staticmethod
    def _recv_json(sock):
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))
