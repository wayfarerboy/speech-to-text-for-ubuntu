"""Single configuration for all speech-to-text processes.

Import this module and reference ``config.NAME``.  Tests that need to
override a value can monkeypatch the attribute on this module directly.
"""

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
