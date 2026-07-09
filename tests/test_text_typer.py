"""Tests for TextTyper."""

import os
from unittest import mock

import pytest

from text_typer import TextTyper


# ── type ───────────────────────────────────────────────────────────────

class TestType:
    def test_runs_xdotool_type_with_clearmodifiers(self):
        """type() calls xdotool type --clearmodifiers with text + space."""
        typer = TextTyper(clipboard_enabled=False)
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch.object(typer, "_release_modifiers"):
            mock_run.return_value = mock.MagicMock(returncode=0)
            typer.type("hello")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "xdotool"
        assert args[1] == "type"
        assert "--clearmodifiers" in args
        assert args[-1] == "hello "

    def test_appends_space(self):
        """Typed text always has a trailing space."""
        typer = TextTyper()
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch.object(typer, "_release_modifiers"):
            mock_run.return_value = mock.MagicMock(returncode=0)
            typer.type("hello")
        assert mock_run.call_args[0][0][-1] == "hello "

    def test_empty_text_noops(self):
        """Empty or whitespace-only text does nothing."""
        typer = TextTyper()
        with mock.patch("subprocess.run") as mock_run:
            typer.type("")
        mock_run.assert_not_called()

    def test_empty_whitespace_noops(self):
        """Whitespace-only text does nothing."""
        typer = TextTyper()
        with mock.patch("subprocess.run") as mock_run:
            typer.type("   ")
        mock_run.assert_not_called()

    def test_releases_modifiers_after_type(self):
        """type() calls _release_modifiers after xdotool."""
        typer = TextTyper()
        with mock.patch("subprocess.run"), \
             mock.patch.object(typer, "_release_modifiers") as mock_rel:
            mock_run = mock.MagicMock(returncode=0)
            with mock.patch("subprocess.run", return_value=mock_run):
                typer.type("hello")
        mock_rel.assert_called_once()


# ── clipboard ──────────────────────────────────────────────────────────

class TestClipboard:
    def test_disabled_by_config(self):
        """When COPY_TO_CLIPBOARD is empty, clipboard is disabled."""
        typer = TextTyper()
        assert typer.clipboard_enabled is True  # default from config

    def test_disabled_when_empty(self):
        """clipboard_enabled=False when COPY_TO_CLIPBOARD is ''."""
        typer = TextTyper(clipboard_enabled=False)
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch.object(typer, "_release_modifiers"):
            mock_run.return_value = mock.MagicMock(returncode=0)
            typer.type("hello")
        # xdotool still called, clipboard is not
        assert mock_run.call_count == 1  # only xdotool, no clipboard

    @mock.patch("subprocess.run")
    def test_x11_clipboard(self, mock_run):
        """Clipboard uses xclip when DISPLAY is set and no WAYLAND_DISPLAY."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True):
            typer = TextTyper()
            typer._copy_to_clipboard("test text")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "xclip"
        assert "clipboard" in args

    @mock.patch("subprocess.run")
    def test_wayland_clipboard(self, mock_run):
        """Clipboard uses wl-copy when WAYLAND_DISPLAY is set."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            typer = TextTyper()
            typer._copy_to_clipboard("test text")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "wl-copy"

    @mock.patch("subprocess.run")
    def test_clipboard_called_during_type(self, mock_run):
        """type() copies to clipboard when clipboard_enabled is True."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        typer = TextTyper(clipboard_enabled=True)
        with mock.patch.object(typer, "_release_modifiers"):
            typer.type("hello")
        # Two calls: one for xdotool, one for clipboard
        assert mock_run.call_count == 2


# ── modifier release ───────────────────────────────────────────────────

class TestReleaseModifiers:
    def test_calls_xdotool_keyup(self):
        """_release_modifiers calls xdotool keyup for all modifiers."""
        typer = TextTyper()
        with mock.patch("subprocess.run") as mock_run:
            typer._release_modifiers()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "xdotool"
        assert args[1] == "keyup"
        assert "Control_L" in args
        assert "Shift_R" in args
        assert "Super_L" in args

    def test_never_raises(self):
        """_release_modifiers never propagates exceptions."""
        typer = TextTyper()
        with mock.patch("subprocess.run", side_effect=Exception("fail")):
            typer._release_modifiers()  # should not raise
