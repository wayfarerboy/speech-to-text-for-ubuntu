"""Tests for speech_to_text_server.py"""

import json
import os
import socket
import tempfile
from unittest import mock

import numpy as np
import pytest

# Import the module under test after setting up mocks.
# We patch faster_whisper at import time since it's a heavy dependency.
with mock.patch.dict("sys.modules", {"faster_whisper": mock.MagicMock()}):
    import servers.speech_to_text_server as server_mod


# ── helpers ────────────────────────────────────────────────────────────

def _temp_wav(samplerate=16000, duration_sec=1.0, stereo=False):
    """Create a temporary WAV file with synthetic audio."""
    samples = int(samplerate * duration_sec)
    if stereo:
        audio = np.random.randn(samples, 2).astype(np.float32)
    else:
        audio = np.random.randn(samples).astype(np.float32)
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    import soundfile as sf
    sf.write(f.name, audio, samplerate)
    return f.name


# ── load_audio ─────────────────────────────────────────────────────────

class TestLoadAudio:
    def test_loads_mono_wav(self):
        path = _temp_wav(stereo=False)
        try:
            audio = server_mod.load_audio(path)
            assert audio.dtype == np.float32
            assert audio.ndim == 1
        finally:
            os.unlink(path)

    def test_converts_stereo_to_mono(self):
        path = _temp_wav(stereo=True)
        try:
            audio = server_mod.load_audio(path)
            assert audio.ndim == 1
        finally:
            os.unlink(path)

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            server_mod.load_audio("/nonexistent/path.wav")


# ── choose_model ───────────────────────────────────────────────────────

class TestChooseModel:
    def test_primary_only_returns_primary(self):
        models = {"primary": "small-model"}
        model, name = server_mod.choose_model(models, "en")
        assert model == "small-model"
        assert name == server_mod.PRIMARY_LANGUAGE_MODEL

    def test_secondary_language_returns_secondary(self):
        models = {"primary": "small-model", "secondary": "medium-model"}
        model, name = server_mod.choose_model(models, "cs")
        assert model == "medium-model"
        assert name == server_mod.SECONDARY_LANGUAGE_MODEL

    def test_non_secondary_language_returns_primary(self):
        models = {"primary": "small-model", "secondary": "medium-model"}
        model, name = server_mod.choose_model(models, "de")
        assert model == "small-model"

    def test_empty_language_defaults_to_en(self):
        models = {"primary": "small-model"}
        model, name = server_mod.choose_model(models, "")
        assert model == "small-model"
        assert name == server_mod.PRIMARY_LANGUAGE_MODEL


# ── handle_request ─────────────────────────────────────────────────────

class TestHandleRequest:
    def setup_method(self):
        self.models = {"primary": mock.MagicMock()}
        self.models["primary"].transcribe.return_value = (
            [mock.MagicMock(text=" hello "), mock.MagicMock(text=" world ")],
            mock.MagicMock(),
        )

    @mock.patch.object(server_mod, "load_audio")
    def test_returns_ok_with_text(self, mock_load):
        mock_load.return_value = np.zeros(16000, dtype=np.float32)
        resp = server_mod.handle_request(
            self.models,
            {"audio_file": "/fake/path.wav", "language": "en"},
        )
        assert resp["ok"] is True
        assert resp["text"] == "hello world"
        assert len(resp["segments"]) == 2

    def test_missing_audio_file_returns_error(self):
        resp = server_mod.handle_request(self.models, {})
        assert resp["ok"] is False
        assert "Missing audio_file" in resp["error"]

    def test_defaults_language_to_en(self):
        with mock.patch.object(server_mod, "load_audio") as mock_load:
            mock_load.return_value = np.zeros(16000, dtype=np.float32)
            resp = server_mod.handle_request(
                self.models,
                {"audio_file": "/fake/path.wav"},
            )
            assert resp["ok"] is True


# ── recv_json / send_json ──────────────────────────────────────────────

class TestSocketIO:
    def test_recv_json_roundtrip(self):
        parent, child = socket.socketpair()
        try:
            payload = {"ok": True, "text": "hello"}
            # send on parent, receive on child
            server_mod.send_json(parent, payload)
            # shutdown write so recv_json sees EOF after the message
            parent.shutdown(socket.SHUT_WR)
            result = server_mod.recv_json(child)
            assert result == payload
        finally:
            parent.close()
            child.close()

    def test_recv_json_empty_returns_none(self):
        parent, child = socket.socketpair()
        try:
            parent.shutdown(socket.SHUT_WR)
            result = server_mod.recv_json(child)
            assert result is None
        finally:
            parent.close()
            child.close()
