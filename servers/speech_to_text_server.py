#!/usr/bin/env python3
"""
Speech-to-text server

Listens on a Unix domain socket (SOCKET_PATH) and accepts one JSON request per
connection: an absolute or server-readable path to an audio file and an ISO 639-1
language code (default: en). It loads the file with soundfile, runs faster-whisper,
and returns JSON with segment strings and joined text.

You may configure a primary model for most languages and an optional secondary model
for specific language codes (see SECONDARY_LANGUAGE_MODEL and SECONDARY_MODEL_LANGUAGES).
Clients such as speech_to_text_client.py connect to this socket; the server must be
able to read any audio path the client sends.

Requirements: 
1) sudo apt install libsndfile1

2) Create a Python virtual environment and install packages. The examples use 
/home/amara/venv; substitute your venv path.

  python3 -m venv /home/amara/venv
  /home/amara/venv/bin/pip install -r /home/amara/speech-to-text-for-ubuntu/requirements.txt

Automatic startup on boot:
To automatically start this server on boot, you can use the following crontab entry
for the user running the display (e.g. amara):

* * * * * ps -ef | grep "speech-to-text-for-ubuntu/servers/speech_to_text_server.py" | grep -v grep > /dev/null || /home/amara/venv/bin/python3 /home/amara/speech-to-text-for-ubuntu/servers/speech_to_text_server.py > /dev/null 2>&1 &

This cron job checks every minute if the script is running and if it is not, it starts the script.
"""

import json
import logging
import os
import socket
import sys
import time
import traceback

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

# Ensure repo root is on sys.path so import config works regardless of
# how this script is launched (systemd, full path, relative path, etc.).
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config

# Re-exported for test visibility.
SOCKET_PATH = config.SOCKET_PATH
PRIMARY_LANGUAGE_MODEL = config.PRIMARY_LANGUAGE_MODEL
SECONDARY_LANGUAGE_MODEL = config.SECONDARY_LANGUAGE_MODEL
SECONDARY_MODEL_LANGUAGES = config.SECONDARY_MODEL_LANGUAGES
COMPUTE_TYPE = config.COMPUTE_TYPE
WHISPER_CPU_THREADS = config.WHISPER_CPU_THREADS
INITIAL_PROMPT_EN = config.INITIAL_PROMPT_EN
INITIAL_PROMPT_CS = config.INITIAL_PROMPT_CS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/stt_server.log")
    ]
)

def load_audio(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    audio, samplerate = sf.read(file_path)
    audio = audio.astype("float32")

    if len(audio.shape) > 1 and audio.shape[1] > 1:
        audio = np.mean(audio, axis=1)
        logging.info("Converted stereo audio to mono")

    logging.info(f"Audio loaded: {file_path}, sample rate: {samplerate}")
    return audio

def choose_model(models, language):
    primary = models["primary"]
    if "secondary" not in models:
        return primary, PRIMARY_LANGUAGE_MODEL
    if language in SECONDARY_MODEL_LANGUAGES:
        return models["secondary"], SECONDARY_LANGUAGE_MODEL
    return primary, PRIMARY_LANGUAGE_MODEL

def transcribe_audio(models, audio, language="en"):
    start_time = time.perf_counter()
    language = (language or "en").strip().lower()
    model, selected_model_name = choose_model(models, language)
    logging.info(
        "Transcribe request language: %s, model: %s",
        language,
        selected_model_name,
    )

    initial_prompt = None
    if language == "en":
        initial_prompt = INITIAL_PROMPT_EN
    elif language == "cs":
        initial_prompt = INITIAL_PROMPT_CS

    logging.info(
        "Initial prompt mode: %s",
        "enabled" if initial_prompt else "disabled",
    )

    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=1,
        vad_filter=True,
        task="transcribe",
        initial_prompt=initial_prompt,
    )

    results = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            results.append(text)

    full_text = " ".join(results).strip()
    preview = full_text[:60] + ("..." if len(full_text) > 60 else "")
    logging.info(
        "Transcribe result: segments=%d, text_length=%d, preview='%s'",
        len(results),
        len(full_text),
        preview,
    )
    elapsed_s = time.perf_counter() - start_time
    logging.info(
        "Transcribe timing: elapsed_ms=%.1f, elapsed_s=%.3f",
        elapsed_s * 1000,
        elapsed_s,
    )

    return results

def handle_request(models, req):
    audio_file = req.get("audio_file")
    if not audio_file:
        return {"ok": False, "error": "Missing audio_file"}
    language = req.get("language", "en")

    logging.info("Request for audio file: %s, language: %s", audio_file, language)
    audio = load_audio(audio_file)
    results = transcribe_audio(models, audio, language=language)
    text = " ".join(results).strip()

    logging.info(f"Transcription completed, {len(results)} segments")
    return {
        "ok": True,
        "segments": results,
        "text": text
    }

def recv_json(conn):
    data = b""
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
    if not data:
        return None
    return json.loads(data.decode("utf-8"))

def send_json(conn, obj):
    payload = json.dumps(obj).encode("utf-8")
    conn.sendall(payload)

def main():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    logging.info(
        "Loading Whisper model (PRIMARY): %s, cpu_threads=%s",
        PRIMARY_LANGUAGE_MODEL,
        WHISPER_CPU_THREADS,
    )
    models = {
        "primary": WhisperModel(
            PRIMARY_LANGUAGE_MODEL,
            compute_type=COMPUTE_TYPE,
            cpu_threads=WHISPER_CPU_THREADS,
            num_workers=1,
        )
    }
    logging.info("Loaded PRIMARY model")
    if SECONDARY_LANGUAGE_MODEL:
        logging.info(
            "Loading Whisper model (SECONDARY): %s, cpu_threads=%s",
            SECONDARY_LANGUAGE_MODEL,
            WHISPER_CPU_THREADS,
        )
        models["secondary"] = WhisperModel(
            SECONDARY_LANGUAGE_MODEL,
            compute_type=COMPUTE_TYPE,
            cpu_threads=WHISPER_CPU_THREADS,
            num_workers=1,
        )
        logging.info("Loaded SECONDARY model")
    else:
        logging.info("No SECONDARY model; all languages use PRIMARY")

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o600)
    server.listen(5)

    logging.info(f"Listening on {SOCKET_PATH}")

    try:
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    req = recv_json(conn)
                    if req is None:
                        send_json(conn, {"ok": False, "error": "Empty request"})
                        continue

                    resp = handle_request(models, req)
                    send_json(conn, resp)

                except Exception as e:
                    logging.error(f"Request failed: {e}")
                    logging.error(traceback.format_exc())
                    send_json(conn, {"ok": False, "error": str(e)})
    finally:
        server.close()
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

if __name__ == "__main__":
    main()
