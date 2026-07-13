"""Tests for stt_coordinator."""

import os
import signal
import sys
from unittest import mock

import pytest

# The coordinator is a script, not a module. We test by importing its
# pieces and mocking external dependencies.
from scripts import stt_coordinator


# ── CLI argument parsing ──────────────────────────────────────────────

class TestParseArgs:
    def test_minimal_args(self):
        """Minimal invocation: audio file only, defaults language and indicator."""
        argv = ["stt_coordinator.py", "/tmp/audio.wav"]
        args = stt_coordinator.parse_args(argv)
        assert args.audio_file == "/tmp/audio.wav"
        assert args.language == "en"
        assert args.indicator_pid is None

    def test_all_args(self):
        """All arguments specified."""
        argv = [
            "stt_coordinator.py",
            "/tmp/audio.wav",
            "--language", "cs",
            "--indicator-pid", "12345",
        ]
        args = stt_coordinator.parse_args(argv)
        assert args.audio_file == "/tmp/audio.wav"
        assert args.language == "cs"
        assert args.indicator_pid == 12345


class TestMain:
    def test_transcribes_then_types_then_hides_indicator(self):
        """Happy path: transcribe -> type -> hide indicator -> exit 0."""
        with mock.patch.object(
            stt_coordinator.TranscriptionClient, "transcribe",
            return_value="hello world",
        ) as mock_transcribe, \
             mock.patch.object(
            stt_coordinator.TextTyper, "type",
        ) as mock_type, \
             mock.patch("os.kill") as mock_kill:

            exit_code = stt_coordinator.main(
                audio_file="/tmp/test.wav",
                language="en",
                indicator_pid=42,
            )

            assert exit_code == 0
            mock_transcribe.assert_called_once_with("/tmp/test.wav", "en")
            mock_type.assert_called_once_with("hello world")
            mock_kill.assert_called_once_with(42, signal.SIGTERM)

    def test_exits_nonzero_on_transcription_failure(self):
        """When transcription fails, exit non-zero. Still hides indicator."""
        with mock.patch.object(
            stt_coordinator.TranscriptionClient, "transcribe",
            side_effect=RuntimeError("server down"),
        ), mock.patch.object(
            stt_coordinator.TextTyper, "type",
        ) as mock_type, \
           mock.patch("os.kill") as mock_kill:

            exit_code = stt_coordinator.main(
                audio_file="/tmp/test.wav",
                language="en",
                indicator_pid=42,
            )

            assert exit_code != 0
            mock_type.assert_not_called()
            mock_kill.assert_called_once_with(42, signal.SIGTERM)

    def test_exits_nonzero_when_audio_file_missing(self):
        """FileNotFoundError from transcription -> non-zero exit."""
        with mock.patch.object(
            stt_coordinator.TranscriptionClient, "transcribe",
            side_effect=FileNotFoundError("no file"),
        ), mock.patch.object(
            stt_coordinator.TextTyper, "type",
        ) as mock_type, \
           mock.patch("os.kill") as mock_kill:

            exit_code = stt_coordinator.main(
                audio_file="/tmp/missing.wav",
                language="en",
                indicator_pid=42,
            )

            assert exit_code != 0
            mock_type.assert_not_called()
            mock_kill.assert_called_once_with(42, signal.SIGTERM)

    def test_skips_indicator_when_pid_is_none(self):
        """When no indicator PID given, skip kill."""
        with mock.patch.object(
            stt_coordinator.TranscriptionClient, "transcribe",
            return_value="hello",
        ), mock.patch.object(
            stt_coordinator.TextTyper, "type",
        ), mock.patch("os.kill") as mock_kill:

            exit_code = stt_coordinator.main(
                audio_file="/tmp/test.wav",
                language="en",
                indicator_pid=None,
            )

            assert exit_code == 0
            mock_kill.assert_not_called()

    def test_handles_indicator_kill_failure(self):
        """If killing indicator fails (e.g., PID not found), still exit cleanly."""
        with mock.patch.object(
            stt_coordinator.TranscriptionClient, "transcribe",
            return_value="hello",
        ), mock.patch.object(
            stt_coordinator.TextTyper, "type",
        ), mock.patch("os.kill", side_effect=ProcessLookupError("no such process")):

            exit_code = stt_coordinator.main(
                audio_file="/tmp/test.wav",
                language="en",
                indicator_pid=99999,
            )

            assert exit_code == 0

    def test_default_language_is_en(self):
        """When language is empty string, default to en."""
        with mock.patch.object(
            stt_coordinator.TranscriptionClient, "transcribe",
            return_value="hello",
        ) as mock_transcribe, \
             mock.patch.object(stt_coordinator.TextTyper, "type"), \
             mock.patch("os.kill"):

            exit_code = stt_coordinator.main(
                audio_file="/tmp/test.wav",
                language="",
                indicator_pid=None,
            )

            assert exit_code == 0
            mock_transcribe.assert_called_once_with("/tmp/test.wav", "en")


# ── Run entry-point ───────────────────────────────────────────────────

class TestRun:
    def test_run_calls_main_with_parsed_args(self):
        """run() parses argv, calls main, calls sys.exit."""
        with mock.patch.object(sys, "argv", [
            "stt_coordinator.py",
            "/tmp/audio.wav",
            "--language", "cs",
            "--indicator-pid", "42",
        ]), mock.patch.object(stt_coordinator, "main", return_value=0) as mock_main:
            with pytest.raises(SystemExit) as exc:
                stt_coordinator.run()
            mock_main.assert_called_once_with(
                audio_file="/tmp/audio.wav",
                language="cs",
                indicator_pid=42,
            )
            assert exc.value.code == 0

    def test_run_exits_with_main_return_code(self):
        """run() uses main()'s return value as exit code."""
        with mock.patch.object(sys, "argv", [
            "stt_coordinator.py", "/tmp/audio.wav",
        ]), mock.patch.object(stt_coordinator, "main", return_value=3) as mock_main:
            with pytest.raises(SystemExit) as exc:
                stt_coordinator.run()
            assert exc.value.code == 3
