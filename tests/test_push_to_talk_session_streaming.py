"""Tests for PushToTalkSessionStreaming."""

import os
import subprocess
import threading
from unittest import mock

import pytest

from push_to_talk_session_streaming import PushToTalkSessionStreaming
from tests.fake_adapters import FakeIndicator, FakeTranscriber, FakeTyper


# ── helpers ────────────────────────────────────────────────────────────

class FakeDeepgramClient:
    """Fake Deepgram client for testing streaming session.

    *connect_raises* / *feed_raises* simulate failures.
    *stop_text* is returned from ``stop_and_get_text()``.
    """

    def __init__(self, connect_raises=None, feed_raises=None,
                 stop_text="hello from deepgram"):
        self.connect_raises = connect_raises
        self.feed_raises = feed_raises
        self.stop_text = stop_text

        # call tracking
        self.connected = False
        self.stopped = False
        self.fed_chunks = []

    async def connect(self):
        if self.connect_raises:
            raise self.connect_raises
        self.connected = True

    async def feed_audio_async(self, chunk):
        if self.feed_raises:
            raise self.feed_raises
        self.fed_chunks.append(chunk)

    async def stop_and_get_text(self):
        self.stopped = True
        return self.stop_text


def _fake_popen():
    proc = mock.MagicMock(spec=subprocess.Popen)
    proc.pid = 12345
    return proc


def _streaming_session(**overrides):
    """Build a PushToTalkSessionStreaming with fake adapters."""
    kwargs = dict(
        transcriber=FakeTranscriber("local transcript"),
        typer=FakeTyper(),
        indicator=FakeIndicator(),
        audio_file="/tmp/stt_test.wav",
        env={"HOME": "/tmp"},
        deepgram_factory=lambda: FakeDeepgramClient(),
    )
    kwargs.update(overrides)
    return PushToTalkSessionStreaming(**kwargs)


# ── state machine ──────────────────────────────────────────────────────

class TestStreamingSessionLifecycle:
    def test_start_transitions_to_recording(self, monkeypatch):
        """start() moves from idle to recording, creates FIFO, spawns arecord."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        assert session.state == "idle"

        result = session.start("en")
        assert result is True
        assert session.state == "recording"

    def test_start_creates_fifo(self, monkeypatch):
        """start() calls os.mkfifo with the correct path."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        mkfifo = mock.MagicMock()
        monkeypatch.setattr(os, "mkfifo", mkfifo)
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        session.start("en")

        mkfifo.assert_called_once()
        fifo_path = mkfifo.call_args[0][0]
        assert fifo_path.endswith(".fifo")
        assert "stt_stream_" in fifo_path

    def test_double_start_blocked(self, monkeypatch):
        """Calling start() while already recording is a no-op."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        session.start("en")
        assert session.state == "recording"

        result = session.start("cs")
        assert result is False
        assert session.state == "recording"

    def test_stop_before_start_safe(self):
        """Calling stop() from idle returns None."""
        session = _streaming_session()
        result = session.stop()
        assert result is None
        assert session.state == "idle"

    def test_stop_from_transcribing_blocked(self, monkeypatch):
        """Calling stop() while already transcribing is a no-op."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        session.start("en")
        session._state = "transcribing"
        result = session.stop()
        assert result is None

    def test_stop_terminates_arecord(self, monkeypatch):
        """stop() calls terminate+wait on the arecord process."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        session.start("en")
        session.stop()

        fake_proc.terminate.assert_called_once()
        fake_proc.wait.assert_called_once()


# ── buffer accumulation ────────────────────────────────────────────────

class TestBufferAccumulation:
    def test_no_typing_during_recording(self, monkeypatch):
        """TextTyper.type() is never called before stop()."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        # Don't actually start the worker thread
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        typer = FakeTyper()
        session = _streaming_session(typer=typer)
        session.start("en")

        # During recording, typer should not have been called
        assert typer.texts == []

        # After stop, worker thread join returns immediately (mock)
        session.stop()
        # No Deepgram transcript -> typer not called (empty text)
        assert typer.texts == []

    def test_transcript_typed_on_stop(self, monkeypatch):
        """Transcript from Deepgram is typed only during stop()."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        # Mock the thread so the worker never actually runs
        thread_mock = mock.MagicMock()
        thread_mock.is_alive.return_value = False
        monkeypatch.setattr(threading, "Thread",
                            mock.MagicMock(return_value=thread_mock))

        typer = FakeTyper()
        session = _streaming_session(typer=typer)

        session.start("en")
        # Simulate worker having completed with transcript
        session._transcript = "hello deepgram"
        session.stop()

        assert typer.texts == ["hello deepgram"]

    def test_empty_transcript_not_typed(self, monkeypatch):
        """Empty Deepgram transcript is not sent to typer."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        # Mock the thread so the worker never actually runs
        thread_mock = mock.MagicMock()
        thread_mock.is_alive.return_value = False
        monkeypatch.setattr(threading, "Thread",
                            mock.MagicMock(return_value=thread_mock))

        typer = FakeTyper()
        session = _streaming_session(typer=typer)

        session.start("en")
        session._transcript = ""
        session.stop()

        assert typer.texts == []


# ── indicator ─────────────────────────────────────────────────────────

class TestIndicatorSignalling:
    def test_indicator_shows_recording_on_start(self, monkeypatch):
        """Indicator shows 'recording' on start()."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        indicator = FakeIndicator()
        session = _streaming_session(indicator=indicator)
        session.start("en")

        assert ("show", "recording") in indicator.calls

    def test_indicator_shows_processing_on_stop(self, monkeypatch):
        """Indicator shows 'processing' on stop()."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())

        indicator = FakeIndicator()
        session = _streaming_session(indicator=indicator)
        session.start("en")
        session.stop()

        assert ("show", "processing") in indicator.calls

    def test_indicator_hides_after_stop(self, monkeypatch):
        """Indicator is hidden after stop() completes."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())

        indicator = FakeIndicator()
        session = _streaming_session(indicator=indicator)
        session.start("en")
        session.stop()

        assert ("hide",) in indicator.calls

    def test_indicator_sequence(self, monkeypatch):
        """Indicator sequence: show(recording) → show(processing) → hide."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())

        indicator = FakeIndicator()
        session = _streaming_session(indicator=indicator)
        session.start("en")
        session.stop()

        # Ensure rec → proc → hide order
        assert indicator.calls.index(("show", "recording")) \
            < indicator.calls.index(("show", "processing")) \
            < indicator.calls.index(("hide",))


# ── fallback path ──────────────────────────────────────────────────────

class TestFallbackPath:
    def test_connect_failure_falls_back_to_local(self, monkeypatch):
        """Deepgram connect failure → local transcription is used."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())

        # Patch _pcm_to_wav to succeed (it exists)
        monkeypatch.setattr(
            "push_to_talk_session_streaming.PushToTalkSessionStreaming._pcm_to_wav",
            mock.MagicMock(),
        )
        # Patch exists so fallback finds the backup
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        transcriber = FakeTranscriber("local fallback text")
        typer = FakeTyper()

        session = _streaming_session(
            transcriber=transcriber,
            typer=typer,
            deepgram_factory=lambda: FakeDeepgramClient(
                connect_raises=ConnectionError("no network"),
            ),
        )

        session.start("en")
        # Worker would set _fallback_needed; simulate it
        session._fallback_needed = True
        session.stop()

        assert typer.texts == ["local fallback text"]
        assert transcriber.calls[0][1] == "en"

    def test_midstream_failure_falls_back_to_local(self, monkeypatch):
        """Mid-stream Deepgram failure → local transcription is used."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        monkeypatch.setattr(
            "push_to_talk_session_streaming.PushToTalkSessionStreaming._pcm_to_wav",
            mock.MagicMock(),
        )
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        transcriber = FakeTranscriber("local fallback text")
        typer = FakeTyper()

        session = _streaming_session(
            transcriber=transcriber,
            typer=typer,
            deepgram_factory=lambda: FakeDeepgramClient(
                feed_raises=RuntimeError("stream broken"),
            ),
        )

        session.start("en")
        session._fallback_needed = True
        session.stop()

        assert typer.texts == ["local fallback text"]

    def test_fallback_handles_missing_backup(self, monkeypatch):
        """Fallback returns empty string when PCM backup is missing."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        monkeypatch.setattr(os.path, "exists", lambda p: False)

        typer = FakeTyper()
        session = _streaming_session(typer=typer)
        session.start("en")
        session._fallback_needed = True
        text = session.stop()

        assert text == ""
        assert typer.texts == []

    def test_fallback_transcriber_exception_returns_empty(self, monkeypatch):
        """If local transcriber also fails, returns empty string."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        monkeypatch.setattr(
            "push_to_talk_session_streaming.PushToTalkSessionStreaming._pcm_to_wav",
            mock.MagicMock(),
        )
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        failing = FakeTranscriber()
        failing.transcribe = mock.MagicMock(side_effect=RuntimeError("fail"))
        typer = FakeTyper()

        session = _streaming_session(
            transcriber=failing,
            typer=typer,
        )
        session.start("en")
        session._fallback_needed = True
        text = session.stop()

        assert text == ""
        assert typer.texts == []


# ── FIFO cleanup ───────────────────────────────────────────────────────

class TestCleanup:
    def test_fifo_cleaned_up_after_session(self, monkeypatch):
        """FIFO and PCM backup are removed after stop()."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        unlink = mock.MagicMock()
        monkeypatch.setattr(os, "unlink", unlink)
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        session = _streaming_session()
        session.start("en")
        session.stop()

        unlink_calls = [c[0][0] for c in unlink.call_args_list]
        assert any("stt_stream_" in p and ".fifo" in p for p in unlink_calls)
        assert any("stt_stream_" in p and ".pcm" in p for p in unlink_calls)

    def test_cleanup_handles_oserror(self, monkeypatch):
        """Cleanup does not crash if unlink raises OSError."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink",
                            mock.MagicMock(side_effect=OSError))
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        session = _streaming_session()
        session.start("en")
        # Should not raise
        session.stop()

    def test_fifo_unlinks_after_existing(self, monkeypatch):
        """If FIFO already exists, unlink then mkfifo."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        mkfifo = mock.MagicMock()
        unlink = mock.MagicMock()
        monkeypatch.setattr(os, "mkfifo", mkfifo)
        monkeypatch.setattr(os, "unlink", unlink)
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        # mkfifo raises FileExistsError first time
        mkfifo.side_effect = [FileExistsError, None]

        session = _streaming_session()
        session.start("en")

        assert unlink.called
        assert mkfifo.call_count == 2


# ── arecord args ──────────────────────────────────────────────────────

class TestArecordArgs:
    def test_arecord_writes_raw_pcm_to_fifo(self, monkeypatch):
        """arecord is called with --file-type raw and the FIFO path."""
        popen = mock.MagicMock(return_value=_fake_popen())
        monkeypatch.setattr(subprocess, "Popen", popen)
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        session.start("en")

        args = popen.call_args[0][0]
        assert args[0] == "arecord"
        assert "--file-type" in args
        assert "raw" in args
        assert any("stt_stream_" in a and ".fifo" in a for a in args)


# ── language routing ──────────────────────────────────────────────────

class TestLanguageRouting:
    def test_current_language_set_on_start(self, monkeypatch):
        """start() stores the language for use in fallback."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(threading, "Thread", mock.MagicMock())

        session = _streaming_session()
        session.start("cs")
        assert session._current_language == "cs"

    def test_fallback_uses_correct_language(self, monkeypatch):
        """Fallback transcription uses the language from start()."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())
        monkeypatch.setattr(
            "push_to_talk_session_streaming.PushToTalkSessionStreaming._pcm_to_wav",
            mock.MagicMock(),
        )
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        transcriber = FakeTranscriber("přepis")
        session = _streaming_session(transcriber=transcriber)
        session.start("cs")
        session._fallback_needed = True
        session.stop()

        assert transcriber.calls[0] == ("/tmp/stt_test.wav", "cs")


# ── worker thread ─────────────────────────────────────────────────────

class TestWorkerThread:
    def test_worker_thread_started_on_start(self, monkeypatch):
        """A daemon Thread is started in _stream_worker."""
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=_fake_popen()))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())

        thread_mock = mock.MagicMock()
        monkeypatch.setattr(threading, "Thread",
                            mock.MagicMock(return_value=thread_mock))

        session = _streaming_session()
        session.start("en")

        threading.Thread.assert_called_once()
        _, kwargs = threading.Thread.call_args
        assert kwargs.get("target") is not None
        assert kwargs.get("daemon") is True
        thread_mock.start.assert_called_once()

    def test_worker_thread_joined_on_stop(self, monkeypatch):
        """stop() waits for the worker thread."""
        fake_proc = _fake_popen()
        monkeypatch.setattr(subprocess, "Popen",
                            mock.MagicMock(return_value=fake_proc))
        monkeypatch.setattr(os, "mkfifo", mock.MagicMock())
        monkeypatch.setattr(os, "unlink", mock.MagicMock())

        thread_mock = mock.MagicMock()
        thread_mock.is_alive.return_value = True
        monkeypatch.setattr(threading, "Thread",
                            mock.MagicMock(return_value=thread_mock))

        session = _streaming_session()
        session.start("en")
        session.stop()

        thread_mock.join.assert_called_once()


# ── PCM-to-WAV conversion ─────────────────────────────────────────────

class TestPcmToWav:
    def test_conversion_creates_valid_wav(self, tmp_path, monkeypatch):
        """_pcm_to_wav generates a WAV file from raw PCM."""
        import wave

        pcm_path = tmp_path / "test.pcm"
        wav_path = tmp_path / "test.wav"

        # 160 samples of silence (16-bit, 16000 Hz = 10ms of audio)
        pcm_data = b"\x00\x00" * 160
        pcm_path.write_bytes(pcm_data)

        session = _streaming_session()
        session._pcm_to_wav(str(pcm_path), str(wav_path))

        assert wav_path.exists()
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.readframes(160) == pcm_data
