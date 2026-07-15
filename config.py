"""Single configuration for all speech-to-text processes.

Import this module and reference ``config.NAME``.  Tests that need to
override a value can monkeypatch the attribute on this module directly.

Secrets are loaded from a ``.env`` file (python-dotenv).  Copy
``.env.example`` to ``.env`` and fill in real values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ── Key listener ──────────────────────────────────────────────────────
DEVICE_NAME = "input-remapper keyboard"
AUDIO_FILE = "/tmp/stt_recorded_audio.wav"
USER = "alpagan"  # Set to your desktop username
USER_DISPLAY = ":0"
USER_WAYLAND_DISPLAY = "wayland-0"
STATIC_XAUTHORITY = ""
PROCESS_FOR_XAUTH_COPY = "/usr/bin/ksmserver"
PRIMARY_LANGUAGE = "en"
SECONDARY_LANGUAGE = "cs"

# ── Speech-to-text server ─────────────────────────────────────────────
SOCKET_PATH = "/tmp/stt_server.sock"
PRIMARY_LANGUAGE_MODEL = "small"
SECONDARY_LANGUAGE_MODEL = "medium"
SECONDARY_MODEL_LANGUAGES = ("cs",)
COMPUTE_TYPE = "int8"
WHISPER_CPU_THREADS = 8
INITIAL_PROMPT_EN = (
    "Clean transcription style. Remove filler words such as um, uh, like, "
    "you know, I mean. Remove obvious repeated words and false starts. "
    "Keep the intended sentence natural and concise."
)
INITIAL_PROMPT_CS = (
    "Použij čistý styl přepisu. Odstraň vyplňová slova jako ehm, hmm, "
    "jakože, víš a podobně. Odstraň zjevně opakovaná slova a falešné začátky. "
    "Zachovej zamýšlenou větu přirozenou a stručnou."
)

# ── Client ────────────────────────────────────────────────────────────
COPY_TO_CLIPBOARD = "yes"

# ── Timeouts ───────────────────────────────────────────────────────────
TYPING_TIMEOUT = 5      # seconds before xdotool is killed + clipboard fallback
TRANSCRIPTION_TIMEOUT = 10  # seconds for socket connect/recv

# ── Deepgram streaming ────────────────────────────────────────────────
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = "nova-2"
DEEPGRAM_ENDPOINT = "wss://api.deepgram.com/v1/listen"


def streaming_enabled():
    """Return True when Deepgram streaming is configured."""
    return bool(DEEPGRAM_API_KEY.strip())

# ── Deepgram formatting ───────────────────────────────────────────────
SMART_FORMAT = "true"   # capitals, punctuation, dates, numbers
PUNCTUATE = "true"       # periods, commas, question/exclamation marks
UTTERANCE_END_MS = 0  # ms of silence before finalizing utterance (disabled — 400 with nova-2)
NUMERALS = "false"       # "42" instead of "forty two"
DIARIZE = "false"        # speaker labels


def deepgram_extra_params():
    """Build extra query params for Deepgram streaming."""
    params = []
    if str(SMART_FORMAT).strip() == "true":
        params.append("smart_format=true")
    if str(PUNCTUATE).strip() == "true":
        params.append("punctuate=true")
    if str(NUMERALS).strip() == "true":
        params.append("numerals=true")
    if str(DIARIZE).strip() == "true":
        params.append("diarize=true")
    ms = UTTERANCE_END_MS
    if isinstance(ms, int) and ms > 0:
        params.append(f"utterance_end_ms={ms}")
    if params:
        return "&" + "&".join(params)
    return ""
