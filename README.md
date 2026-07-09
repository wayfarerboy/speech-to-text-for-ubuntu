# Fast push-to-talk speech-to-text for Ubuntu

> **Fork** of [CDNsun/speech-to-text-for-ubuntu](https://github.com/CDNsun/speech-to-text-for-ubuntu) —  
> originally created by [CDNsun s.r.o.](https://cdnsun.com) under the MIT license.
> This fork adds architectural improvements: consolidated configuration,  
> extracted `TranscriptionClient` / `TextTyper` / `PushToTalkSession` modules,  
> and a testable session state machine for the key listener.

This project gives Ubuntu a practical push-to-talk speech-to-text workflow. You hold a key, speak, release the key, and the transcript is typed into the currently focused application.

The main goal is low-latency local transcription that is still usable on ordinary hardware. In practice, this setup can be fast enough for live work even on a laptop without a dedicated GPU. On CPU-only hardware, transcription can still complete in under two seconds, which makes it practical for live communication with an AI agent or any other text interface without typing.

The project is built from four parts. `servers/key_listener.py` listens for a hotkey, starts recording on key press, and stops on key release. `servers/speech_to_text_server.py` runs a local Unix socket server and performs speech-to-text with faster-whisper. `scripts/speech_to_text_client.py` sends the recorded audio to the server, receives the transcript, optionally copies it to the clipboard, and types the text with `xdotool`. `scripts/recording_indicator.py` shows a live audio spectrogram while recording and a processing animation during transcription.

Tested on Kubuntu 24.04 LTS, Kali 2026.1, Ubuntu 24.04 LTS

## How it works

1. You press and hold a hotkey, for example `F16`
2. `key_listener.py` starts recording audio with `arecord` and launches a live spectrogram overlay
3. You release the key
4. The spectrogram switches to a processing animation while transcription runs
5. The key listener calls `speech_to_text_client.py`
6. The client sends the audio file path and language to `speech_to_text_server.py`
7. The server loads the audio and runs faster-whisper
8. The client receives the transcript, kills the indicator overlay
9. The transcript is optionally copied to the clipboard and typed into the active window
10. Modifier keys are automatically released after typing to prevent stuck keys

## Installation on a fresh Ubuntu system

Start by installing the required system packages:

```bash
sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  libsndfile1 \
  xdotool \
  xclip \
  wl-clipboard \
  input-remapper \
  alsa-utils \
  python3-evdev \
  python3-tk \
  evtest
```

`xdotool` is used to type the transcript into the focused window. `xclip` is used for clipboard copy on X11, while `wl-clipboard` provides clipboard support on Wayland. `input-remapper` is strongly recommended for creating a reliable trigger key such as `F16`, and `evtest` helps you find the correct input device path. `python3-tk` is required by the recording indicator overlay. `libsndfile1` is required by the Python `soundfile` package.

Clone the repository. The examples below assume the project is stored in `/home/david/speech-to-text-for-ubuntu` and the virtual environment is `/home/david/venv`. If your username or paths differ, adjust the configuration values in the scripts accordingly.

```bash
cd /home/david
git clone https://github.com/CDNsun/speech-to-text-for-ubuntu.git
cd /home/david/speech-to-text-for-ubuntu
```

Then create a Python virtual environment and install the Python dependencies from `requirements.txt`:

```bash
python3 -m venv /home/david/venv
/home/david/venv/bin/pip install --upgrade pip
/home/david/venv/bin/pip install -r /home/david/speech-to-text-for-ubuntu/requirements.txt
```

The Python packages used by the project are `numpy`, `soundfile`, `faster-whisper`, and `sounddevice`.

## Configure input-remapper

This project is designed around using `input-remapper`. A setup script automates the configuration:

```bash
sudo python3 deploy/setup-input-remapper.py
```

The script:
1. Lists available keyboard devices and lets you pick one
2. Computes the `origin_hash` automatically (no manual hex editing)
3. Creates a preset mapping your chosen key → `KEY_F16` (and optionally `KEY_F17` for a second language)
4. Enables autoload so the preset loads on boot

If you prefer to configure manually, create an input-remapper preset that maps your trigger key to `KEY_F16` / `KEY_F17` and enable autoload. The key listener auto-discovers input-remapper's virtual keyboard device by name.

## Configure the key listener

Open `servers/key_listener.py` and review the configuration values near the top of the file.

In particular, you will usually want to adjust:

- `DEVICE_NAME`, default `"input-remapper keyboard"` — the key listener auto-discovers the event device by name, so this rarely needs changing
- `USER`, for example `david`
- `USER_DISPLAY`, usually `:0`
- `USER_WAYLAND_DISPLAY`, empty for X11 and something like `wayland-0` for Wayland
- `STATIC_XAUTHORITY`, if needed
- `PROCESS_FOR_XAUTH_COPY`, default example `/usr/bin/ksmserver`
- `PRIMARY_LANGUAGE`, default `en`
- `SECONDARY_LANGUAGE`, optional, default `cs`

Script paths (client, indicator) and the Python virtual environment are derived automatically from this script's location and the user's home directory — no hardcoded paths to edit.

The key listener must be run as root because it needs access to `/dev/input/event*`.

## Configure the speech-to-text server

Open `servers/speech_to_text_server.py` and review the Whisper configuration.

The most important settings are:

- `PRIMARY_LANGUAGE_MODEL`, default `small`
- `SECONDARY_LANGUAGE_MODEL`, default `medium`
- `SECONDARY_MODEL_LANGUAGES`, default `("cs",)`
- `COMPUTE_TYPE`, default `int8`
- `WHISPER_CPU_THREADS`, default `8`
- `INITIAL_PROMPT_EN`
- `INITIAL_PROMPT_CS`

The server supports a primary model for the default path and an optional secondary model for selected languages. This allows you to keep the common case fast while still using a larger model where accuracy matters more.

## Why there are two buttons

The second button is optional, but it is a very practical part of the design.

One common setup is to use one button for English and another button for (for example) Czech. In that case, the selected button already tells the system which language is expected, so the correct language code can be passed directly to Whisper. That means the model does not need to rely on language autodetection first.

It is also useful because different languages may benefit from different model sizes. A smaller model may already be fast and accurate enough for English, while a larger model may give better results for Czech. Since larger models are usually slower, this split lets you keep one fast path and one higher-quality path.

Because of that, the two-button design is useful not only as a two-language setup, but also as a two-mode setup. One path can be optimized for speed, while the other can be optimized for accuracy.

By default, the primary model is used for most languages, and the secondary model is used only for the languages listed in `SECONDARY_MODEL_LANGUAGES`.

## Optional clipboard behavior

If you want the transcript to be copied to the clipboard before typing, leave `COPY_TO_CLIPBOARD` enabled in `scripts/speech_to_text_client.py`:

```python
COPY_TO_CLIPBOARD = "yes"
```

If you do not want clipboard copy, set it to an empty string:

```python
COPY_TO_CLIPBOARD = ""
```

## Recording indicator

A visual overlay appears while recording and during transcription. It shows:

- **While holding the key:** a live rainbow spectrogram — mirror-symmetric frequency bars with speech frequencies centred. Requires `python3-tk` and `sounddevice`+`numpy` (installed via the project's `requirements.txt` for the virtual environment).
- **During transcription:** a white sine-wave scroll animation, replacing the spectrogram until the text is pasted.

The indicator is click-through (passes all mouse events to windows underneath), borderless, always-on-top, and automatically positions on the monitor where your pointer is. It disappears before the text is typed so it never obscures the target application.

## Usage

Start the speech-to-text server as your normal desktop user:

```bash
/home/david/venv/bin/python3 /home/david/speech-to-text-for-ubuntu/servers/speech_to_text_server.py
```

This starts a Unix socket server at:

```text
/tmp/stt_server.sock
```

Then start the key listener as root:

```bash
sudo python3 /home/david/speech-to-text-for-ubuntu/servers/key_listener.py
```

Once both processes are running, focus the text field where you want the transcript to appear, press and hold your trigger key, speak, and release the key. The recorded audio is transcribed and the resulting text is typed into the currently focused window.

By default, `F16` is used for the primary language and primary model path, while `F17` can be used for the secondary language and secondary model path. If `SECONDARY_LANGUAGE` is empty, only `F16` is used.

Typing is implemented with `xdotool`, which is primarily an X11-oriented solution. Clipboard copy supports both X11 and Wayland, but automatic typing may be more reliable in X11 sessions.

## Start automatically on boot

Run the deployment script to install and enable both systemd services:

```bash
chmod +x deploy/deploy-services.sh
./deploy/deploy-services.sh
```

This creates and starts two services:

- **User service** `stt-server` — the speech-to-text server, runs as your user
- **System service** `stt-keylistener` — the key listener, runs as root (needed for `/dev/input/` access)

The script is idempotent — safe to re-run after pulling updates or changing paths.

Check status:

```bash
systemctl --user status stt-server
systemctl status stt-keylistener
```

Follow logs:

```bash
journalctl --user -u stt-server -f
sudo journalctl -u stt-keylistener -f
```

## Logs

The scripts write logs to `/tmp/stt_server.log`, `/tmp/stt_client.log`, and `/tmp/stt_key_listener.log`. These are useful when checking whether the workflow is running correctly or when tuning performance.

## Troubleshooting

### Modifier keys get stuck after typing

The client automatically releases all modifier keys (Ctrl, Alt, Shift, Super, Meta) after every typing operation. If keys still get stuck, run:

```bash
xdotool keyup Control_L Control_R Alt_L Alt_R Shift_L Shift_R Super_L Super_R Meta_L Meta_R
```

### XWayland input permission prompt

On KDE Plasma Wayland, xdotool may trigger a permission dialog.  Set
`AllowXwaylandGrab=true` in `~/.config/kwinrc` under the `[Xwayland]`
section, then log out and back in.

### Indicator shows no spectrogram

Ensure `sounddevice` is installed in the project's virtual environment:

```bash
/home/user/venv/bin/pip install sounddevice
```

### Key press not detected

- Verify input-remapper preset is loaded and autoload is enabled.
- Check that the `origin_hash` in the input-remapper preset matches the
  current keyboard (run input-remapper GUI to regenerate if needed).
- Verify the key listener is running: `systemctl status stt-keylistener`.

## Testing

A pytest suite covers the server, client, and key listener modules (40 tests).

```bash
pip install pytest
python3 -m pytest tests/ -v
```

### What's tested

| Module | Coverage |
|---|---|
| `speech_to_text_server.py` | Audio loading (mono/stereo/missing), model selection, request handling, socket JSON I/O |
| `speech_to_text_client.py` | Socket communication, X11/Wayland clipboard, xdotool typing, modifier key release, `--indicator-pid` flag |
| `key_listener.py` | Device discovery by name, environment setup (display, PulseAudio, XDG), script path derivation, subprocess calls |

### What's mocked

- `faster_whisper` (heavy ML dependency, not needed for logic tests)
- `evdev` input devices (requires real hardware and root)
- `xdotool` / `xclip` / `wl-copy` (requires a running X11/Wayland session)
- `arecord` (requires audio hardware)

The recording indicator (`recording_indicator.py`) is not covered by automated tests — it requires a live audio device and a display. It is tested manually.
