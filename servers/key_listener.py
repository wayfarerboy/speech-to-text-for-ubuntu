#!/usr/bin/env python3
"""
Speech-to-text key listener

This script listens for a specific key press to start audio recording and stops on key release.
In other words, it listens and records when the key is pressed and stops when the key is released.

It is recommended to use keys (e.g. F16, and optionally F17 for a secondary language)
that are not otherwise used by your system or applications, otherwise you may experience interference.

Suppose you want to use the side mouse button (BTN_SIDE) to trigger speech-to-text.
However, some programs (Chrome) already use this button for navigation (go "back").
To avoid conflicts, use input-remapper to remap BTN_SIDE to F16.

Any key on the keyboard or button on the mouse can be remapped to F16 or F17.

This script must be run as root in order to access input devices (e.g., /dev/input/event*).
Running as a regular user will result in permission errors.

To automatically start this key listener on boot, run `deploy/deploy-services.sh`
to install and enable a systemd system unit with `Restart=always`. The unit
waits for the graphical session to be ready before starting.

"""

import logging
import os
import signal
import sys
import subprocess
import pwd
import time


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/stt_key_listener.log')
    ]
)

try:
    from evdev import InputDevice, categorize, ecodes
except ImportError:
    print("Error: evdev library not found")
    sys.exit(1)

# Configuration — all configurable values live in config.py.
# Ensure repo root is on sys.path so import config works regardless of
# how this script is launched (systemd, full path, relative path, etc.).
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config

# Re-exported for test visibility (tests reference e.g. kl_mod.USER_DISPLAY).
DEVICE_NAME = config.DEVICE_NAME
AUDIO_FILE = config.AUDIO_FILE
USER = config.USER
USER_DISPLAY = config.USER_DISPLAY
USER_WAYLAND_DISPLAY = config.USER_WAYLAND_DISPLAY
STATIC_XAUTHORITY = config.STATIC_XAUTHORITY
PROCESS_FOR_XAUTH_COPY = config.PROCESS_FOR_XAUTH_COPY
PRIMARY_LANGUAGE = config.PRIMARY_LANGUAGE
SECONDARY_LANGUAGE = config.SECONDARY_LANGUAGE

# Paths derived from this script's location (no hardcoded home directories).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)  # up from servers/

INDICATOR_SCRIPT = os.path.join(_PROJECT_DIR, "scripts", "recording_indicator.py")

# Recording session (slimmed to recording-only; transcription/typing offloaded to coordinator).
from push_to_talk_session import PushToTalkSession
from push_to_talk_session_streaming import PushToTalkSessionStreaming
from indicator_adapter import ProcessIndicator

def find_device_by_name(name, retries=10, delay=2):
    """Find /dev/input/event* device matching the given name.
    
    Retries because input-remapper may not have created the virtual device yet
    when this service starts.
    """
    import glob
    for attempt in range(retries):
        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                with open(f"/sys/class/input/{os.path.basename(path)}/device/name") as f:
                    if f.read().strip() == name:
                        logging.info("Found device '%s' at %s", name, path)
                        return path
            except (IOError, OSError):
                continue
        if attempt < retries - 1:
            logging.warning(
                "Device '%s' not found, retrying in %ds (%d/%d)",
                name, delay, attempt + 1, retries,
            )
            time.sleep(delay)
    raise FileNotFoundError(f"Device '{name}' not found after {retries} attempts")

def _demote(uid, gid):
    """Return a preexec_fn that drops privileges to *uid*/*gid*."""
    def _drop():
        os.setgid(gid)
        os.setuid(uid)
    return _drop


def _hide_indicator_safe(pid):
    """Send SIGTERM to indicator PID — best-effort, never raises."""
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def setup_environment():
    pw_record = pwd.getpwnam(USER)
    env = os.environ.copy()
    env.update({
        "HOME": f"/home/{USER}",
        "XDG_CACHE_HOME": f"/home/{USER}/.cache",
        "XDG_RUNTIME_DIR": f"/run/user/{pw_record.pw_uid}",
        "DISPLAY": f"{USER_DISPLAY}",
        "WAYLAND_DISPLAY": f"{USER_WAYLAND_DISPLAY}",
        "PULSE_SERVER": f"unix:/run/user/{pw_record.pw_uid}/pulse/native",
        "PULSE_RUNTIME_PATH": f"/run/user/{pw_record.pw_uid}/pulse",
    })

    # We set env["XAUTHORITY"]
    if STATIC_XAUTHORITY:
        xauth_path = os.path.expanduser(STATIC_XAUTHORITY)
        if not os.path.isfile(xauth_path):
            logging.error(f"STATIC_XAUTHORITY file not found: {xauth_path}")
            sys.exit(1)
        env["XAUTHORITY"] = xauth_path
        logging.info(f"Set XAUTHORITY to {xauth_path} (static)")
    else:
        try:
            pid = subprocess.check_output(
                ["pgrep", "-u", USER, "-f", PROCESS_FOR_XAUTH_COPY],
                universal_newlines=True
            ).strip().split("\n")[0]
            environ_path = f"/proc/{pid}/environ"
            with open(environ_path, "rb") as f:
                env_vars = f.read().split(b"\0")
            xauth = None
            for var in env_vars:
                if var.startswith(b"XAUTHORITY="):
                    xauth = var[len(b"XAUTHORITY="):].decode()
                    break
            if not xauth:
                raise RuntimeError(
                    f"XAUTHORITY not found in environment of {PROCESS_FOR_XAUTH_COPY} (PID {pid})"
                )
            env["XAUTHORITY"] = xauth
            logging.info(
                f"Set XAUTHORITY to {xauth} (from {PROCESS_FOR_XAUTH_COPY}, PID {pid})"
            )
        except Exception as e:
            logging.error(
                f"Could not get XAUTHORITY from process {PROCESS_FOR_XAUTH_COPY} for {USER}: {e}"
            )
            sys.exit(1)

    return env

def main():
    """Main function."""
    # Check if running as root
    if os.geteuid() != 0:
        logging.error("This script must be run as root")
        sys.exit(1)

    # Setup
    env = setup_environment()
    device_path = find_device_by_name(DEVICE_NAME)
    device = InputDevice(device_path)

    # Build key→language map.
    key_map = {"KEY_F16": PRIMARY_LANGUAGE}
    if SECONDARY_LANGUAGE:
        key_map["KEY_F17"] = SECONDARY_LANGUAGE

    # Wire adapters.
    venv_python = os.path.join(env["HOME"], ".venv", "bin", "python3")
    indicator = ProcessIndicator(INDICATOR_SCRIPT, venv_python, env)
    coordinator_script = os.path.join(_PROJECT_DIR, "scripts", "stt_coordinator.py")

    # Record the user's uid/gid for privilege-dropping the coordinator.
    pw_record = pwd.getpwnam(USER)
    user_uid = pw_record.pw_uid
    user_gid = pw_record.pw_gid

    if config.streaming_enabled():
        logging.info("Deepgram streaming enabled — using PushToTalkSessionStreaming")
        from transcription_client import TranscriptionClient
        from text_typer import TextTyper
        session = PushToTalkSessionStreaming(
            transcriber=TranscriptionClient(),
            typer=TextTyper(env=env),
            indicator=indicator,
            audio_file=AUDIO_FILE,
            env=env,
        )
    else:
        session = PushToTalkSession(
            indicator=indicator,
            audio_file=AUDIO_FILE,
            env=env,
        )

    logging.info("Listening for %s on %s", "/".join(key_map), device_path)

    def _spawn_coordinator(language, indicator_pid):
        """Spawn the coordinator as the desktop user (non-blocking)."""
        try:
            subprocess.Popen(
                [
                    sys.executable,
                    coordinator_script,
                    AUDIO_FILE,
                    "--language", language,
                    "--indicator-pid", str(indicator_pid),
                ],
                env=env,
                preexec_fn=_demote(user_uid, user_gid),
            )
        except Exception as e:
            logging.error("Failed to spawn coordinator: %s", e)
            _hide_indicator_safe(indicator_pid)

    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)

                # Ignore key repeats
                if key.keystate == 2:
                    continue

                if key.keycode in key_map:
                    if key.keystate == key.key_down:
                        language = key_map[key.keycode]
                        logging.info(
                            "Starting audio recording (key=%s, language=%s)",
                            key.keycode,
                            language,
                        )
                        session.start(language)

                    elif key.keystate == key.key_up:
                        logging.info("Stopping audio recording")
                        started_at = time.monotonic()
                        try:
                            if isinstance(session, PushToTalkSessionStreaming):
                                # Streaming session handles typing + indicator internally.
                                session.stop()
                            else:
                                language = session.stop()
                                if language is not None:
                                    indicator_pid = indicator.pid
                                    _spawn_coordinator(language, indicator_pid)
                            elapsed = time.monotonic() - started_at
                            logging.info(
                                "Recording stopped in %.2f seconds (coordinator spawned)",
                                elapsed,
                            )
                        except Exception as e:
                            logging.error("Stop recording failed: %s", e)

    except KeyboardInterrupt:
        logging.info("Shutting down due to keyboard interrupt")
    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main()

