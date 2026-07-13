"""Indicator adapters for PushToTalkSession.

Interface: ``show(mode)`` / ``hide()``.
"""

import abc
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


class ProcessIndicator(IndicatorAdapter):
    """Real indicator: spawns a tkinter spectrogram window.

    Uses SIGUSR1 to switch from spectrogram to processing animation,
    SIGTERM to close.
    """

    def __init__(self, indicator_script, venv_python, env):
        self._indicator_script = indicator_script
        self._venv_python = venv_python
        self._env = env
        self._process = None

    @property
    def pid(self):
        """PID of the indicator process, or None if not running."""
        if self._process and self._process.poll() is None:
            return self._process.pid
        return None

    def show(self, mode):
        if mode == "recording":
            if self._process is not None:
                self.hide()
            self._process = subprocess.Popen(
                [self._venv_python, self._indicator_script],
                env=self._env,
            )
        elif mode == "processing":
            if self._process and self._process.poll() is None:
                self._process.send_signal(signal.SIGUSR1)

    def hide(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
