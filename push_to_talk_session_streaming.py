"""PushToTalkSessionStreaming — streaming recording via FIFO + Deepgram.

Falls back to local transcription on Deepgram failure.
"""

import asyncio
import logging
import os
import subprocess
import threading

logger = logging.getLogger(__name__)


class PushToTalkSessionStreaming:
    """Streaming push-to-talk session using Deepgram over WebSocket.

    On *start* a FIFO is created and ``arecord`` writes raw PCM to it.
    A background thread reads the FIFO, tees the PCM to a backup file,
    and feeds chunks to the Deepgram streaming client.  Transcripts
    accumulate in a buffer; nothing is typed until *stop*.

    If the Deepgram connection or stream fails, the session falls back
    to local transcription using the captured PCM backup.
    """

    def __init__(self, transcriber, typer, indicator, audio_file, env,
                 deepgram_factory=None):
        self._transcriber = transcriber
        self._typer = typer
        self._indicator = indicator
        self._audio_file = audio_file       # WAV for fallback
        self._env = env
        self._dg_factory = deepgram_factory or _build_default_dg_client

        self._state = "idle"
        self._recording_process = None
        self._current_language = None

        # Streaming internals
        self._fifo_path = None
        self._pcm_backup_path = None
        self._worker_thread = None
        self._stop_event = None
        self._transcript = None
        self._fallback_needed = False

    # ── public API ─────────────────────────────────────────────────

    @property
    def state(self):
        return self._state

    def start(self, language):
        """Begin streaming recording for *language*.

        Returns ``True`` if recording started, ``False`` if already busy.
        """
        if self._state != "idle":
            return False

        self._current_language = language
        self._state = "recording"
        self._indicator.show("recording")

        pid = os.getpid()
        self._fifo_path = f"/tmp/stt_stream_{pid}.fifo"
        self._pcm_backup_path = f"/tmp/stt_stream_{pid}.pcm"

        # Create FIFO
        try:
            os.mkfifo(self._fifo_path)
        except FileExistsError:
            os.unlink(self._fifo_path)
            os.mkfifo(self._fifo_path)

        # Worker that reads the FIFO and feeds Deepgram
        self._stop_event = threading.Event()
        self._transcript = None
        self._fallback_needed = False

        self._worker_thread = threading.Thread(
            target=self._stream_worker,
            daemon=True,
        )
        self._worker_thread.start()

        # Start arecord writing raw PCM to the FIFO
        self._recording_process = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                "--file-type", "raw",
                self._fifo_path,
            ],
            env=self._env,
        )
        return True

    def stop(self):
        """Stop recording, drain Deepgram, type result, clean up.

        Returns the transcribed text, or ``None`` if not recording.
        On Deepgram failure falls back to local transcription.
        """
        if self._state != "recording":
            return None

        # Stop arecord
        self._recording_process.terminate()
        self._recording_process.wait()
        self._recording_process = None

        self._state = "transcribing"
        self._indicator.show("processing")

        # Signal the worker to drain / stop
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=15)

        self._indicator.hide()

        text = ""
        try:
            if self._fallback_needed:
                logger.info("Deepgram stream failed — falling back to local")
                text = self._transcribe_fallback()
            else:
                text = self._transcript or ""

            if text.strip():
                self._typer.type(text)
        finally:
            self._cleanup()

        self._state = "idle"
        self._current_language = None
        return text

    # ── worker (runs in background thread) ────────────────────────

    def _stream_worker(self):
        """Connect Deepgram, read FIFO → feed audio, drain on stop."""
        dg = self._dg_factory()

        # 1. Connect
        try:
            _run_async(dg.connect())
        except Exception:
            logger.warning("Deepgram connect failed — will fall back")
            self._fallback_needed = True
            self._capture_pcm_only()
            return

        # 2. Stream audio
        try:
            self._feed_fifo_to_deepgram(dg)
        except Exception as exc:
            logger.warning("Deepgram stream error: %s", exc)
            self._fallback_needed = True

        # 3. Drain final transcripts (only if stream didn't fail)
        if not self._fallback_needed:
            try:
                self._transcript = _run_async(dg.stop_and_get_text())
            except Exception:
                logger.warning("Deepgram drain failed — falling back")
                self._fallback_needed = True

    def _feed_fifo_to_deepgram(self, dg):
        """Read FIFO chunks, tee to backup, feed to Deepgram."""
        with open(self._pcm_backup_path, "wb") as backup:
            with open(self._fifo_path, "rb") as fifo:
                while not self._stop_event.is_set():
                    chunk = fifo.read(8192)
                    if not chunk:
                        break
                    backup.write(chunk)
                    try:
                        _run_async(dg.feed_audio_async(chunk))
                    except Exception:
                        self._fallback_needed = True
                        self._drain_fifo_to_backup(fifo, backup)
                        return

    def _capture_pcm_only(self):
        """Read FIFO into backup file (no Deepgram — already failed)."""
        try:
            with open(self._pcm_backup_path, "wb") as backup:
                with open(self._fifo_path, "rb") as fifo:
                    self._drain_fifo_to_backup(fifo, backup)
        except Exception:
            pass

    @staticmethod
    def _drain_fifo_to_backup(fifo, backup):
        """Read remaining data from *fifo* into *backup* until stopped."""
        while True:
            chunk = fifo.read(8192)
            if not chunk:
                break
            backup.write(chunk)

    # ── fallback transcription ────────────────────────────────────

    def _transcribe_fallback(self):
        """Convert captured PCM to WAV and transcribe locally."""
        if not os.path.exists(self._pcm_backup_path):
            return ""

        self._pcm_to_wav(self._pcm_backup_path, self._audio_file)

        try:
            return self._transcriber.transcribe(
                self._audio_file, self._current_language
            )
        except Exception as exc:
            logger.warning("Fallback transcription failed: %s", exc)
            return ""

    @staticmethod
    def _pcm_to_wav(pcm_path, wav_path):
        """Convert raw 16-bit 16kHz mono PCM to WAV."""
        import wave

        with open(pcm_path, "rb") as pcm:
            pcm_data = pcm.read()

        with wave.open(wav_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(16000)
            wav.writeframes(pcm_data)

    # ── cleanup ───────────────────────────────────────────────────

    def _cleanup(self):
        """Remove FIFO and PCM backup files."""
        for path in (self._fifo_path, self._pcm_backup_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ── helpers ──────────────────────────────────────────────────────────

def _run_async(coro):
    """Run async coroutine synchronously in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_default_dg_client():
    from deepgram_streaming_client import DeepgramStreamingClient
    return DeepgramStreamingClient()
