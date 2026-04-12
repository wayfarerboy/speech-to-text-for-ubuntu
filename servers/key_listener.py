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

To automatically start this key listener on boot, you can use the following crontab entry for root:

* * * * * ps -ef | grep "speech-to-text-for-ubuntu/servers/key_listener.py" | grep -v grep > /dev/null || /usr/bin/python3 /home/david/speech-to-text-for-ubuntu/servers/key_listener.py > /dev/null 2>&1 &

This cron job checks every minute if the script is running and if it is not, it starts the script.

"""

import logging
import os
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

# Configuration
# To choose the correct event ID for your device, use the "evtest" tool:
# Run "sudo evtest" in a terminal.
# If you used input-remapper then it can look like this: 
# /dev/input/event15:     input-remapper keyboard
DEVICE_PATH = "/dev/input/event15"

# Just a temporary file to store the audio. 
AUDIO_FILE = "/tmp/stt_recorded_audio.wav"

# The user who runs the X server
USER = "david"

# The user's display, use "echo $DISPLAY;" to check
USER_DISPLAY = ":0"

# The user's Wayland display, use "echo $WAYLAND_DISPLAY;" to check 
# It is empty if you are running (legacy) X11 session 
# It is non-empty if you are running (new) Wayland session
USER_WAYLAND_DISPLAY = ""

# Check using: echo $XAUTHORITY;
# If the Xauthority filename is static, e.g. ~/.Xauthority and NOT something like /tmp/xauth_AVqvHc 
# which contains random string and hence is dynamic then define it here.
# If the Xauthority filename is dynamic then set this variable to empty string.
STATIC_XAUTHORITY = ""

# This variable is irrelevant and not used when STATIC_XAUTHORITY is non-empty
# We will get XAUTHORITY variable from a running process (e.g., /usr/bin/ksmserver) owned by USER.
# Find a process that is always running in single instance and owned by USER and has 
# XAUTHORITY variable defined in its environment (see /proc/{pid}/environ)
PROCESS_FOR_XAUTH_COPY = "/usr/bin/ksmserver" # for KDE, /usr/libexec/gsd-media-keys for GNOME

# The script that will process the stored audio and generate text from it. 
SPEECHTOTEXT_SCRIPT = "/home/david/speech-to-text-for-ubuntu/scripts/speech_to_text_client.py"

# PRIMARY_LANGUAGE on KEY_F16; 
# optional SECONDARY_LANGUAGE on KEY_F17.
# Leave SECONDARY_LANGUAGE empty ("") to listen only for KEY_F16.
PRIMARY_LANGUAGE = "en"
SECONDARY_LANGUAGE = "cs"

def setup_environment():
    pw_record = pwd.getpwnam(USER)
    env = os.environ.copy()
    env.update({
        "HOME": f"/home/{USER}",
        "XDG_CACHE_HOME": f"/home/{USER}/.cache",
        "XDG_RUNTIME_DIR": f"/run/user/{pw_record.pw_uid}",
        "DISPLAY": f"{USER_DISPLAY}",
        "WAYLAND_DISPLAY": f"{USER_WAYLAND_DISPLAY}",
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
    device = InputDevice(DEVICE_PATH)
    recording_process = None
    recording_language = PRIMARY_LANGUAGE
    recording_started_at = None

    if SECONDARY_LANGUAGE:
        logging.info("Listening for KEY_F16/KEY_F17 on %s", DEVICE_PATH)
    else:
        logging.info("Listening for KEY_F16 on %s", DEVICE_PATH)

    active_keys = (
        ("KEY_F16", "KEY_F17")
        if SECONDARY_LANGUAGE
        else ("KEY_F16",)
    )

    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)
                
                # Ignore key repeats
                if key.keystate == 2:
                    continue
                
                if key.keycode in active_keys:
                    if key.keystate == key.key_down and recording_process is None:
                        recording_language = (
                            SECONDARY_LANGUAGE
                            if SECONDARY_LANGUAGE and key.keycode == "KEY_F17"
                            else PRIMARY_LANGUAGE
                        )
                        # Start recording
                        logging.info(
                            "Starting audio recording (key=%s, audio=%s)",
                            key.keycode,
                            AUDIO_FILE,
                        )
                        recording_process = subprocess.Popen([
                            "sudo", "-u", USER, "-E",
                            "arecord",
                            "-f", "S16_LE", # nothing to do with KEY_F16
                            "-r", "16000",
                            "-c", "1",
                            AUDIO_FILE
                        ], env=env)
                        logging.info(f"Recording started with PID {recording_process.pid}")
                    
                    elif key.keystate == key.key_up and recording_process:
                        # Stop recording and process
                        logging.info("Stopping audio recording")
                        recording_process.terminate()
                        recording_process.wait()
                        logging.info(f"Recording saved to {AUDIO_FILE}")
                        recording_started_at = time.monotonic()
                        
                        # Process audio
                        logging.info(
                            "Running speech-to-text (language=%s, audio=%s)",
                            recording_language,
                            AUDIO_FILE,
                        )
                        try:
                            subprocess.run([
                                "sudo", "-u", USER, "-E",
                                "python3",
                                SPEECHTOTEXT_SCRIPT,
                                AUDIO_FILE,
                                "--language",
                                recording_language,
                            ], env=env, check=True)
                            elapsed = (
                                time.monotonic() - recording_started_at
                                if recording_started_at is not None
                                else None
                            )
                            if elapsed is not None:
                                logging.info("Speech-to-text completed in %.2f seconds", elapsed)
                            else:
                                logging.info("Speech-to-text completed")
                        except subprocess.CalledProcessError as e:
                            logging.error("Speech-to-text failed: %s", e)
                        finally:
                            recording_process = None
                            recording_language = PRIMARY_LANGUAGE
                            recording_started_at = None
                        
    except KeyboardInterrupt:
        logging.info("Shutting down due to keyboard interrupt")
        if recording_process:
            recording_process.terminate()
    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    main()

