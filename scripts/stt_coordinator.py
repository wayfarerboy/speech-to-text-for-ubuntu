#!/usr/bin/env python3
"""Coordinator — transcribe, type, hide indicator.

Run by the key listener when a recording completes.  Invoked as the
desktop user, *not* root::

    stt_coordinator.py <audio_file> --language <lang> --indicator-pid <pid>

Responsibilities (in order):

1. Send audio to the STT server for transcription.
2. Signal the recording indicator to hide (SIGTERM).
3. Type the result via xdotool (with timeout + clipboard fallback).

Exits 0 on success, non-zero on failure.
"""

import argparse
import logging
import os
import signal
import sys

from transcription_client import TranscriptionClient
from text_typer import TextTyper

logger = logging.getLogger(__name__)


def parse_args(argv=None):
    """Parse CLI arguments.  *argv* defaults to ``sys.argv``.

    When *argv* is provided it should be a full ``sys.argv``-style list
    (argv[0] is the program name, stripped before parsing).
    """
    parser = argparse.ArgumentParser(
        description="Transcribe audio, type result, hide indicator."
    )
    parser.add_argument(
        "audio_file",
        help="Absolute path to the recorded WAV file.",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="ISO 639-1 language code (default: en).",
    )
    parser.add_argument(
        "--indicator-pid",
        type=int,
        default=None,
        help="PID of the recording indicator process to SIGTERM.",
    )
    args_to_parse = argv[1:] if argv is not None else None
    return parser.parse_args(args_to_parse)


def main(audio_file, language="en", indicator_pid=None):
    """Run the coordinator workflow.

    Returns:
        0 on success, non-zero on failure.
    """
    language = language or "en"

    try:
        # 1. Transcribe
        client = TranscriptionClient()
        text = client.transcribe(audio_file, language)

        # 2. Type
        typer = TextTyper()
        typer.type(text)

    except (FileNotFoundError, RuntimeError) as e:
        logger.error("Transcription failed: %s", e)
        _hide_indicator(indicator_pid)
        return 1
    except Exception as e:
        logger.error("Coordinator failed: %s", e)
        _hide_indicator(indicator_pid)
        return 1
    else:
        _hide_indicator(indicator_pid)
        return 0


def _hide_indicator(pid):
    """Send SIGTERM to the indicator process. Best-effort, never raises."""
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        logger.debug("Indicator PID %s not found (already exited?)", pid)
    except Exception as e:
        logger.warning("Failed to signal indicator PID %s: %s", pid, e)


def run():
    """Entry point: parse args, run main, exit."""
    args = parse_args()
    exit_code = main(
        audio_file=args.audio_file,
        language=args.language,
        indicator_pid=args.indicator_pid,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run()
