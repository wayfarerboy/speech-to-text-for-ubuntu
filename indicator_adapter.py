"""Indicator adapters for PushToTalkSession.

Interface: ``show(mode)`` / ``hide()`` / ``close()``.
"""

import abc
import os
import pwd
import signal
import subprocess


class IndicatorAdapter(abc.ABC):
    """Abstract interface for a recording/processing indicator."""

    @abc.abstractmethod
    def show(self, mode):
        """Display the indicator.

        Args:
            mode: ``"recording"`` or ``"processing"``.
        """

    @abc.abstractmethod
    def hide(self):
        """Hide the indicator."""

    @abc.abstractmethod
    def close(self):
        """Permanently shut down the indicator.  No further calls allowed."""


class ProcessIndicator(IndicatorAdapter):
    """Real indicator: manages a persistent tkinter spectrogram process.

    The indicator process is spawned once at construction (hidden).
    Subsequent ``show`` / ``hide`` calls send signals to control it:

    * SIGUSR1 — show recording spectrogram (deiconify + start audio)
    * SIGUSR2 — switch to processing animation (stop audio)
    * SIGTERM — hide window (withdraw, stop audio, reset)
    * SIGINT  — exit completely (used by ``close()``)

    If *run_as_user* is provided and the current process is root, the
    indicator is spawned as that user (avoids polkit dialogs for audio).
    """

    def __init__(self, indicator_script, venv_python, env, run_as_user=None):
        self._indicator_script = indicator_script
        self._venv_python = venv_python
        self._env = env
        self._closed = False

        popen_kwargs = dict(
            env=self._env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if run_as_user and os.geteuid() == 0:
            pw = pwd.getpwnam(run_as_user)
            popen_kwargs["user"] = pw.pw_uid
            popen_kwargs["group"] = pw.pw_gid

        self._process = subprocess.Popen(
            [self._venv_python, self._indicator_script],
            **popen_kwargs,
        )

    def show(self, mode):
        if self._closed:
            return
        if self._process is None or self._process.poll() is not None:
            return
        if mode == "recording":
            self._process.send_signal(signal.SIGUSR1)
        elif mode == "processing":
            self._process.send_signal(signal.SIGUSR2)

    def hide(self):
        if self._closed:
            return
        if self._process and self._process.poll() is None:
            self._process.send_signal(signal.SIGTERM)

    def close(self):
        """Kill the indicator process permanently."""
        if self._closed:
            return
        self._closed = True
        if self._process and self._process.poll() is None:
            self._process.send_signal(signal.SIGINT)
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._process = None
