"""Tests for speech_to_text_client.py (CLI wrapper)."""

import os
import signal
from unittest import mock

import pytest

import scripts.speech_to_text_client as client_mod


# ── argument parsing ───────────────────────────────────────────────────

class TestArgParsing:
    def test_default_language(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("audio_file")
        parser.add_argument("--language", default="en")
        parser.add_argument("--indicator-pid", type=int, default=None)
        args = parser.parse_args(["/tmp/test.wav"])
        assert args.language == "en"
        assert args.indicator_pid is None

    def test_indicator_pid_flag(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("audio_file")
        parser.add_argument("--language", default="en")
        parser.add_argument("--indicator-pid", type=int, default=None)
        args = parser.parse_args(["/tmp/test.wav", "--indicator-pid", "42"])
        assert args.indicator_pid == 42


# ── indicator PID handling ─────────────────────────────────────────────

class TestIndicatorPid:
    def test_kills_indicator_before_typing(self):
        with mock.patch.object(os, "kill") as mock_kill:
            os.kill(12345, signal.SIGTERM)
            mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_ignores_missing_pid(self):
        with mock.patch.object(os, "kill", side_effect=OSError):
            try:
                os.kill(99999, signal.SIGTERM)
            except OSError:
                pass  # the actual code catches this


# ── main flow ──────────────────────────────────────────────────────────

class TestMainFlow:
    def test_main_transcribes_and_types(self):
        """main() calls transcribe then type, handles indicator PID."""
        with mock.patch.object(client_mod, "TranscriptionClient") as mock_tc, \
             mock.patch.object(client_mod, "TextTyper") as mock_tt, \
             mock.patch.object(os, "kill") as mock_kill, \
             mock.patch("sys.argv", [
                 "speech_to_text_client.py",
                 "/tmp/test.wav",
                 "--language", "en",
                 "--indicator-pid", "42",
             ]):
            mock_client = mock_tc.return_value
            mock_client.transcribe.return_value = "hello world"
            mock_typer = mock_tt.return_value
            mock_typer.clipboard_enabled = False

            client_mod.main()

            mock_client.transcribe.assert_called_once_with("/tmp/test.wav", language="en")
            mock_kill.assert_called_once_with(42, signal.SIGTERM)
            mock_typer.type.assert_called_once_with("hello world")

    def test_main_handles_transcribe_error(self):
        """main() releases modifiers and exits 1 on transcription error."""
        with mock.patch.object(client_mod, "TranscriptionClient") as mock_tc, \
             mock.patch.object(client_mod, "TextTyper") as mock_tt, \
             mock.patch("sys.argv", [
                 "speech_to_text_client.py",
                 "/tmp/test.wav",
             ]):
            mock_client = mock_tc.return_value
            mock_client.transcribe.side_effect = RuntimeError("fail")
            mock_typer = mock_tt.return_value

            with pytest.raises(SystemExit) as exc:
                client_mod.main()
            assert exc.value.code == 1
            mock_typer._release_modifiers.assert_called_once()
