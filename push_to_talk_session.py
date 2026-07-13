"""PushToTalkSession — recording lifecycle state machine.

Interface: ``start(language)`` / ``stop() -> str | None``.

This slimmed variant handles only recording (arecord lifecycle).
Transcription and typing are offloaded to the coordinator script.
"""

import subprocess


class PushToTalkSession:
    """Manages the push-to-talk recording lifecycle.

    Slimmed to recording-only — the coordinator handles transcription
    and typing.  The indicator is shown on start/stop; the coordinator
    is responsible for hiding it after typing.
    """

    def __init__(self, indicator, audio_file, env):
        self._indicator = indicator
        self._audio_file = audio_file
        self._env = env

        self._state = "idle"
        self._recording_process = None
        self._current_language = None

    @property
    def state(self):
        return self._state

    @property
    def current_language(self):
        return self._current_language

    def start(self, language):
        """Begin recording audio for *language*.

        Returns ``True`` if recording started, ``False`` if already busy.
        """
        if self._state != "idle":
            return False

        self._current_language = language
        self._state = "recording"
        self._indicator.show("recording")
        self._recording_process = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                self._audio_file,
            ],
            env=self._env,
        )
        return True

    def stop(self):
        """Stop recording and show the processing indicator.

        Returns the recorded language string, or ``None`` if not recording.
        Transcription and typing are handled by the coordinator — this
        method only terminates arecord and signals the indicator.
        """
        if self._state != "recording":
            return None

        if self._recording_process is not None:
            self._recording_process.terminate()
            self._recording_process.wait()
            self._recording_process = None
        self._indicator.show("processing")
        self._state = "idle"
        language = self._current_language
        self._current_language = None
        return language
