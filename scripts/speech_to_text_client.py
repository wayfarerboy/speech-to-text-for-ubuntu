#!/usr/bin/env python3
"""
Speech-to-text client — thin CLI wrapper around TranscriptionClient + TextTyper.

Normally key_listener.py records audio on a hotkey, then runs this script with the
wav file and language; the STT server runs as its own process. You can also run this
client manually against any audio path the server can read.
"""

import argparse
import logging
import sys

# Ensure repo root is on sys.path so imports work regardless of launch method.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from transcription_client import TranscriptionClient
from text_typer import TextTyper

try:
    fh = logging.FileHandler("/tmp/stt_client.log")
except PermissionError:
    fh = logging.NullHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        fh,
    ],
)


def main():
    parser = argparse.ArgumentParser(
        description="Send audio file to speech-to-text server and type result."
    )
    parser.add_argument("audio_file", help="Path to audio file.")
    parser.add_argument(
        "--language",
        default="en",
        help="ISO 639-1 code (e.g. en, cs),  default: en",
    )
    args = parser.parse_args()
    language = (args.language or "en").strip().lower()

    t_client = TranscriptionClient()
    typer = TextTyper()

    logging.info(
        "Client started - audio=%s, lang=%s, clipb=%s",
        args.audio_file,
        language,
        "on" if typer.clipboard_enabled else "off",
    )

    try:
        text = t_client.transcribe(args.audio_file, language=language)

        typer.type(text)
        logging.info("Done")

    except Exception as e:
        typer._release_modifiers()
        logging.error(f"Client failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
