"""Tests for indicator_adapter.py — ProcessIndicator persistent lifecycle."""

import os
import signal
import subprocess
from unittest import mock

import pytest

from indicator_adapter import ProcessIndicator


# ── helpers ────────────────────────────────────────────────────────────

def _fake_popen():
    proc = mock.MagicMock()
    proc.pid = 12345
    proc.poll.return_value = None  # still running
    return proc


@pytest.fixture
def mock_popen():
    with mock.patch("subprocess.Popen") as mp:
        mp.return_value = _fake_popen()
        yield mp


@pytest.fixture
def mock_geteuid():
    with mock.patch("indicator_adapter.os.geteuid", return_value=0):
        yield


# ── persistent lifecycle ───────────────────────────────────────────────

class TestPersistentLifecycle:
    def test_spawns_at_construction(self, mock_popen):
        """ProcessIndicator spawns the process on __init__, not on show."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert call_args == ["/usr/bin/python3", "/path/to/script.py"]

    def test_process_starts_hidden(self, mock_popen):
        """The spawned process starts hidden — no signal sent at init."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        proc = mock_popen.return_value
        proc.send_signal.assert_not_called()

    def test_show_recording_sends_sigusr1(self, mock_popen):
        """show('recording') sends SIGUSR1 to the persistent process."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        indicator.show("recording")
        mock_popen.return_value.send_signal.assert_called_once_with(
            signal.SIGUSR1
        )

    def test_show_processing_sends_sigusr2(self, mock_popen):
        """show('processing') sends SIGUSR2 to the persistent process."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        indicator.show("processing")
        mock_popen.return_value.send_signal.assert_called_once_with(
            signal.SIGUSR2
        )

    def test_hide_sends_sigterm(self, mock_popen):
        """hide() sends SIGTERM (hide, not kill) to the persistent process."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        indicator.hide()
        mock_popen.return_value.send_signal.assert_called_once_with(
            signal.SIGTERM
        )

    def test_close_sends_sigint_and_waits(self, mock_popen):
        """close() sends SIGINT (quit), waits, and kills on timeout."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        indicator.close()
        proc = mock_popen.return_value
        proc.send_signal.assert_called_once_with(signal.SIGINT)
        proc.wait.assert_called()

    def test_full_cycle(self, mock_popen):
        """show recording → processing → hide → close: correct signals."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        proc = mock_popen.return_value

        indicator.show("recording")
        assert proc.send_signal.call_args_list[-1] == mock.call(signal.SIGUSR1)

        indicator.show("processing")
        assert proc.send_signal.call_args_list[-1] == mock.call(signal.SIGUSR2)

        indicator.hide()
        assert proc.send_signal.call_args_list[-1] == mock.call(signal.SIGTERM)

        indicator.close()
        assert proc.send_signal.call_args_list[-1] == mock.call(signal.SIGINT)


# ── dead process handling ──────────────────────────────────────────────

class TestDeadProcess:
    def test_show_does_nothing_if_process_dead(self, mock_popen):
        """If the process has exited, show() is a no-op."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        proc = mock_popen.return_value
        proc.poll.return_value = 99  # exited with code 99

        indicator.show("recording")
        # No signal sent — process is dead
        proc.send_signal.assert_not_called()

    def test_hide_does_nothing_if_process_dead(self, mock_popen):
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        proc = mock_popen.return_value
        proc.poll.return_value = 99

        indicator.hide()
        proc.send_signal.assert_not_called()


# ── idempotent close ───────────────────────────────────────────────────

class TestCloseIdempotent:
    def test_double_close_safe(self, mock_popen):
        """Close twice doesn't double-send SIGINT."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        indicator.close()
        indicator.close()
        # Only one SIGINT sent
        assert mock_popen.return_value.send_signal.call_count == 1

    def test_close_then_show_noop(self, mock_popen):
        """After close(), show() is a no-op."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
        )
        indicator.close()
        proc = mock_popen.return_value
        proc.send_signal.reset_mock()

        indicator.show("recording")
        proc.send_signal.assert_not_called()


# ── run_as_user ────────────────────────────────────────────────────────

class TestRunAsUser:
    def test_no_user_when_not_root(self, mock_popen, mock_geteuid):
        """Without run_as_user, no user/group kwargs passed."""
        # override geteuid to return non-root
        with mock.patch("indicator_adapter.os.geteuid", return_value=1000):
            indicator = ProcessIndicator(
                indicator_script="/path/to/script.py",
                venv_python="/usr/bin/python3",
                env={"DISPLAY": ":0"},
                run_as_user="alpagan",
            )
        # Even with run_as_user, not root → no user/group
        _, kwargs = mock_popen.call_args
        assert "user" not in kwargs
        assert "group" not in kwargs

    def test_user_when_root(self, mock_popen, mock_geteuid):
        """As root, run_as_user drops privileges."""
        with mock.patch("pwd.getpwnam") as mock_pwd:
            mock_pwd.return_value = mock.MagicMock(pw_uid=1000, pw_gid=1000)
            indicator = ProcessIndicator(
                indicator_script="/path/to/script.py",
                venv_python="/usr/bin/python3",
                env={"DISPLAY": ":0"},
                run_as_user="alpagan",
            )
        _, kwargs = mock_popen.call_args
        assert kwargs["user"] == 1000
        assert kwargs["group"] == 1000

    def test_none_user_no_drop(self, mock_popen, mock_geteuid):
        """With run_as_user=None, no user/group even as root."""
        indicator = ProcessIndicator(
            indicator_script="/path/to/script.py",
            venv_python="/usr/bin/python3",
            env={"DISPLAY": ":0"},
            run_as_user=None,
        )
        _, kwargs = mock_popen.call_args
        assert "user" not in kwargs
