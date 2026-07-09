"""Tests for PushToTalkSession."""

import subprocess
from unittest import mock

import pytest

from push_to_talk_session import PushToTalkSession
from tests.fake_adapters import FakeIndicator, FakeTranscriber, FakeTyper


# ── helpers ────────────────────────────────────────────────────────────

def _fake_popen():
    """Return a mock Popen that looks like a running process."""
    proc = mock.MagicMock(spec=subprocess.Popen)
    proc.pid = 12345
    return proc


# ── session state machine ──────────────────────────────────────────────

class TestSessionLifecycle:
    def test_start_transitions_to_recording(self, monkeypatch):
        """start() moves from idle to recording, spawns arecord and shows indicator."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        indicator = FakeIndicator()
        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=indicator,
            audio_file="/tmp/test.wav",
            env={"HOME": "/tmp"},
        )

        assert session.state == "idle"
        result = session.start("en")
        assert result is True
        assert session.state == "recording"
        assert session._current_language == "en"

        # arecord spawned with correct args
        mock_popen.assert_called_once()
        arecord_args = mock_popen.call_args[0][0]
        assert arecord_args[0] == "arecord"
        assert arecord_args[-1] == "/tmp/test.wav"

        # indicator shown in recording mode
        assert indicator.calls == [("show", "recording")]

    def test_double_start_blocked(self, monkeypatch):
        """Calling start() while recording is a no-op."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        indicator = FakeIndicator()
        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=indicator,
            audio_file="/tmp/test.wav",
            env={},
        )

        session.start("en")
        assert session.state == "recording"

        result = session.start("cs")
        assert result is False
        assert session.state == "recording"
        assert session._current_language == "en"  # unchanged
        assert mock_popen.call_count == 1  # only one arecord spawned

    def test_start_from_transcribing_blocked(self, monkeypatch):
        """Calling start() while transcribing is a no-op."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=FakeIndicator(),
            audio_file="/tmp/test.wav",
            env={},
        )
        # Force into transcribing state
        session._state = "transcribing"
        result = session.start("en")
        assert result is False

    def test_stop_transcribes_and_types(self, monkeypatch):
        """stop() terminates recording, transcribes, types, hides indicator."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        transcriber = FakeTranscriber("hello world")
        typer = FakeTyper()
        indicator = FakeIndicator()
        session = PushToTalkSession(
            transcriber=transcriber,
            typer=typer,
            indicator=indicator,
            audio_file="/tmp/test.wav",
            env={},
        )

        session.start("en")
        text = session.stop()

        assert text == "hello world"
        assert session.state == "idle"
        assert transcriber.calls == [("/tmp/test.wav", "en")]
        assert typer.texts == ["hello world"]
        assert indicator.calls == [
            ("show", "recording"),
            ("show", "processing"),
            ("hide",),
        ]

    def test_stop_before_start_safe(self):
        """Calling stop() from idle is a no-op."""
        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=FakeIndicator(),
            audio_file="/tmp/test.wav",
            env={},
        )
        result = session.stop()
        assert result is None
        assert session.state == "idle"

    def test_stop_terminates_arecord(self, monkeypatch):
        """stop() calls terminate() and wait() on the arecord process."""
        fake_proc = _fake_popen()
        mock_popen = mock.MagicMock(return_value=fake_proc)
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=FakeIndicator(),
            audio_file="/tmp/test.wav",
            env={},
        )

        session.start("en")
        session.stop()

        fake_proc.terminate.assert_called_once()
        fake_proc.wait.assert_called_once()

    def test_transcribe_error_cleans_up(self, monkeypatch):
        """If transcribe raises, indicator is hidden and state resets to idle."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        failing = FakeTranscriber()
        failing.transcribe = mock.MagicMock(side_effect=RuntimeError("fail"))
        indicator = FakeIndicator()

        session = PushToTalkSession(
            transcriber=failing,
            typer=FakeTyper(),
            indicator=indicator,
            audio_file="/tmp/test.wav",
            env={},
        )

        session.start("en")
        with pytest.raises(RuntimeError, match="fail"):
            session.stop()

        assert session.state == "idle"
        # indicator was shown (processing) then hidden
        assert ("show", "processing") in indicator.calls
        assert ("hide",) in indicator.calls

    def test_stop_from_transcribing_blocked(self):
        """Calling stop() while already transcribing is a no-op."""
        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=FakeIndicator(),
            audio_file="/tmp/test.wav",
            env={},
        )
        session._state = "transcribing"
        result = session.stop()
        assert result is None


# ── language routing ───────────────────────────────────────────────────

class TestLanguageRouting:
    def test_start_records_correct_language(self, monkeypatch):
        """start("cs") sets current_language to 'cs'."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        session = PushToTalkSession(
            transcriber=FakeTranscriber(),
            typer=FakeTyper(),
            indicator=FakeIndicator(),
            audio_file="/tmp/test.wav",
            env={},
        )

        session.start("cs")
        assert session._current_language == "cs"


# ── integration ────────────────────────────────────────────────────────

class TestIntegration:
    def test_full_lifecycle(self, monkeypatch):
        """start → stop → idle: full happy path."""
        mock_popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        transcriber = FakeTranscriber("hello world")
        typer = FakeTyper()
        indicator = FakeIndicator()

        session = PushToTalkSession(
            transcriber=transcriber,
            typer=typer,
            indicator=indicator,
            audio_file="/tmp/test.wav",
            env={},
        )

        assert session.state == "idle"

        started = session.start("en")
        assert started is True
        assert session.state == "recording"

        text = session.stop()
        assert text == "hello world"
        assert session.state == "idle"
        assert typer.texts == ["hello world"]
