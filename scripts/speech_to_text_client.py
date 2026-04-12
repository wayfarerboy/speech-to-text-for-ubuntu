#!/usr/bin/env python3
"""
Speech-to-text client

Connects to speech_to_text_server.py over a Unix socket (SOCKET_PATH).
Sends JSON with an audio file path and an ISO 639-1 language code (default: en),
receives the transcript, optionally copies it to clipboard (store your text prompt),
and types it with xdotool at the current keyboard focus.

Normally key_listener.py records audio on a hotkey, then runs this script with the
wav file and language; the STT server runs as its own process. You can also run this
client manually against any audio path the server can read.

Clipboard copy runs only when COPY_TO_CLIPBOARD is non-empty. For clipboard support,
install xclip (X11) or wl-clipboard (Wayland), depending on your session.

Requirements: 
  sudo apt install xdotool            # for typing the text  
  sudo apt install xclip              # for X11 sessions clipboard
  sudo apt install wl-clipboard       # for Wayland sessions clipboard
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys

SOCKET_PATH = "/tmp/stt_server.sock"

# Non-empty (e.g. "yes") = copy to clipboard before typing; "" = off.
COPY_TO_CLIPBOARD = "yes"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/stt_client.log")
    ]
)

def send_request(audio_file, language="en"):
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    req = {
        "audio_file": audio_file,
        "language": language,
    }

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)

    try:
        client.sendall(json.dumps(req).encode("utf-8"))
        client.shutdown(socket.SHUT_WR)

        data = b""
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk

        return json.loads(data.decode("utf-8"))
    finally:
        client.close()

def _clipboard_enabled():
    return bool(str(COPY_TO_CLIPBOARD).strip())

def _copy_to_clipboard(text):
    if os.environ.get("WAYLAND_DISPLAY"):
        logging.info(
            "Clipboard: using Wayland (WAYLAND_DISPLAY=%s)",
            os.environ.get("WAYLAND_DISPLAY"),
        )
        cmd = ["wl-copy"]
    elif os.environ.get("DISPLAY"):
        logging.info(
            "Clipboard: using X11 (DISPLAY=%s)",
            os.environ.get("DISPLAY"),
        )
        cmd = ["xclip", "-selection", "clipboard"]
    else:
        logging.warning(
            "No clipboard tool available. Install xclip on X11 or wl-clipboard on Wayland."
        )
        return False
    try:
        # Do not use capture_output here to avoid pipe deadlock
        subprocess.run(
            cmd,
            input=text,
            check=True,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        logging.warning("Clipboard command not found: %s", cmd[0])
        return False
    except subprocess.CalledProcessError as e:
        logging.warning("Clipboard copy failed (exit %s)", e.returncode)
        return False

def type_text(text):
    if text:
        text_to_type = text + " "
        preview = text[:60] + ("..." if len(text) > 60 else "")        
        if _clipboard_enabled():
            _copy_to_clipboard(text)
        logging.info(f"Typing: {preview}")    
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", text_to_type],
            check=True,
            capture_output=True,
            text=True,
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
    logging.info(
        "Client started - audio=%s, lang=%s, clipb=%s",
        args.audio_file,
        language,
        "on" if _clipboard_enabled() else "off",
    )

    try:
        resp = send_request(args.audio_file, language=language)
        if not resp.get("ok"):
            logging.error(resp.get("error", "Unknown error"))
            sys.exit(1)

        text = resp.get("text", "").strip()
        type_text(text)
        logging.info("Done")

    except Exception as e:
        logging.error(f"Client failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
