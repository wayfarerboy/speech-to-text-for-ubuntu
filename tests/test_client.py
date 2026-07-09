"""Tests for speech_to_text_client.py (CLI wrapper)."""

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
        args = parser.parse_args(["/tmp/test.wav"])
        assert args.language == "en"


# ── main flow ──────────────────────────────────────────────────────────

class TestMainFlow:
    def test_main_transcribes_and_types(self):
        """main() calls transcribe then type."""
        with mock.patch.object(client_mod, "TranscriptionClient") as mock_tc, \
             mock.patch.object(client_mod, "TextTyper") as mock_tt, \
             mock.patch("sys.argv", [
                 "speech_to_text_client.py",
                 "/tmp/test.wav",
                 "--language", "en",
             ]):
            mock_client = mock_tc.return_value
            mock_client.transcribe.return_value = "hello world"
            mock_typer = mock_tt.return_value
            mock_typer.clipboard_enabled = False

            client_mod.main()

            mock_client.transcribe.assert_called_once_with("/tmp/test.wav", language="en")
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
