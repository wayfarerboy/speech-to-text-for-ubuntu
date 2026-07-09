"""PushToTalkSession — recording lifecycle state machine.

Interface: ``start(language)`` / ``stop() -> str``.
"""

import os
import pwd
import subprocess


def _popen_user_kwargs(run_as_user):
    """Return ``dict(user=uid, group=gid)`` if running as root and
    *run_as_user* is set; otherwise an empty dict.
    """
    if run_as_user and os.geteuid() == 0:
        pw = pwd.getpwnam(run_as_user)
        return {"user": pw.pw_uid, "group": pw.pw_gid}
    return {}


class PushToTalkSession:
    """Manages the push-to-talk recording lifecycle.

    Injected dependencies (transcriber, typer, indicator) are called
    at the right moments; tests inject fakes to verify the state machine.

    If *run_as_user* is provided and the current process is root,
    arecord is spawned as that user (avoids polkit dialogs for audio).
    """

    def __init__(self, transcriber, typer, indicator, audio_file, env,
                 run_as_user=None):
        self._transcriber = transcriber
        self._typer = typer
        self._indicator = indicator
        self._audio_file = audio_file
        self._env = env
        self._run_as_user = run_as_user

        self._state = "idle"
        self._recording_process = None
        self._current_language = None

    @property
    def state(self):
        return self._state

    def start(self, language):
        """Begin recording audio for *language*.

        Returns ``True`` if recording started, ``False`` if already busy.
        """
        if self._state != "idle":
            return False

        self._current_language = language
        self._state = "recording"
        self._indicator.show("recording")
        # Remove stale audio file — arecord runs as a different user
        # and can't overwrite a root-owned file.
        try:
            os.remove(self._audio_file)
        except FileNotFoundError:
            pass
        self._recording_process = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                self._audio_file,
            ],
            env=self._env,
            **_popen_user_kwargs(self._run_as_user),
        )
        return True

    def stop(self):
        """Stop recording, transcribe, type, and clean up.

        Returns the transcribed text, or ``None`` if not recording.
        Raises if transcription fails (state is reset to idle regardless).
        """
        if self._state != "recording":
            return None

        self._recording_process.terminate()
        self._recording_process.wait()
        self._recording_process = None
        self._state = "transcribing"
        self._indicator.show("processing")

        try:
            text = self._transcriber.transcribe(
                self._audio_file, self._current_language
            )
        except Exception:
            self._indicator.hide()
            self._state = "idle"
            self._current_language = None
            raise

        self._indicator.hide()
        self._typer.type(text)
        self._state = "idle"
        self._current_language = None
        return text
