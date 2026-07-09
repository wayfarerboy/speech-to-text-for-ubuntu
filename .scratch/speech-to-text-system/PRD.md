# Speech-to-Text for Ubuntu — PRD

**Status:** `ready-for-agent`

## Problem Statement

Ubuntu desktop users who communicate frequently with AI agents or type long text in any application need a fast, hands-free input method. Keyboard typing is slow for extended thoughts, and cloud-based speech-to-text introduces latency, privacy concerns, and network dependency. Existing local solutions are either too slow on CPU-only hardware or lack a practical push-to-talk workflow that integrates cleanly with the desktop.

## Solution

A local push-to-talk speech-to-text system for Ubuntu. The user holds a key, speaks, releases the key, and the transcript is typed into the currently focused application. All transcription runs locally via faster-whisper with no network dependency. The system targets sub-two-second transcription on CPU-only hardware (small model, int8 quantization) while offering an optional larger model for languages that benefit from higher accuracy.

The system has three processes:

- **Key listener** (`servers/key_listener.py`) — runs as root, listens on `/dev/input/event*` for a hotkey (default F16, optional F17 for a secondary language). On key-down: starts `arecord` and a live spectrogram indicator window. On key-up: stops recording, runs the client script, and blocks until transcription and typing complete.
- **Speech-to-text server** (`servers/speech_to_text_server.py`) — runs as the desktop user, listens on a Unix domain socket (`/tmp/stt_server.sock`). Loads one or two faster-whisper models. Receives JSON requests with an audio file path and language code, returns JSON with segment strings and joined text.
- **Client** (`scripts/speech_to_text_client.py`) — run by the key listener with the recorded WAV and language. Connects to the Unix socket, sends the request, receives the transcript, optionally copies to clipboard, types the text with `xdotool`, and kills the indicator window before typing.

A recording indicator (`scripts/recording_indicator.py`) shows a live rainbow FFT spectrogram during recording and switches to a processing animation during transcription.

## User Stories

1. As a desktop user, I want to hold a key, speak, and have my words typed into the focused application, so that I can input text without using the keyboard.
2. As a multilingual user, I want to switch between languages by pressing different hotkeys, so that the transcription engine receives the correct language code without autodetection delay.
3. As a user who speaks a language that needs higher accuracy, I want a larger Whisper model to be used for my language while English stays fast with a smaller model, so that I get both speed and accuracy where each matters.
4. As a user, I want the transcript also copied to my clipboard, so that I can paste it elsewhere or preserve it even if the typing target loses focus.
5. As a user, I want a visual indicator that shows recording is active, so that I know the system is listening before I start speaking.
6. As a user, I want the indicator to change to a processing animation when I release the key, so that I know transcription is in progress and when it finishes.
7. As a non-root desktop user, I want the system to be safe — only the key listener (which must read input devices) runs as root; transcription and typing run as my user.
8. As a user who reboots occasionally, I want both the server and key listener to auto-start on boot, so that the system is always available without manual intervention.
9. As a user on X11, I want transcripts typed reliably with `xdotool` and modifier keys cleaned up after typing, so that stuck modifiers don't interfere with subsequent keyboard use.
10. As a user on Wayland, I want clipboard copy to use `wl-copy` automatically when `WAYLAND_DISPLAY` is set.
11. As a user on X11, I want clipboard copy to use `xclip` automatically when `DISPLAY` is set.
12. As a user who remaps keys with input-remapper, I want the key listener to find the virtual input-remapper keyboard device by name at runtime (retrying if the device isn't ready yet at boot), so that I don't need to hardcode an event number that changes between boots.

## Implementation Decisions

### Architecture: three-process design

The key listener, server, and client are separate processes. The key listener must be root (evdev access) but delegates all transcription work to the client, which runs as the desktop user via the environment inherited from setup_environment(). The server is a long-lived process to avoid model reload on every request.

### Unix domain socket as IPC

Client and server communicate over a Unix domain socket at `/tmp/stt_server.sock` using JSON. One request per connection: the client connects, sends the payload, shuts down its write half, then reads the response. The socket is created with mode 0o600.

### Dual-model design

The server loads a primary model (e.g. `small`) and optionally a secondary model (e.g. `medium`). The language code in the request determines which model is used: languages listed in `SECONDARY_MODEL_LANGUAGES` use the secondary model; all others use the primary. This lets the user keep English fast and Czech accurate, without runtime model switching.

### Recording format

Audio is recorded by `arecord` at 16kHz mono 16-bit PCM (S16_LE) to a temporary WAV file at `/tmp/stt_recorded_audio.wav`. This is the format faster-whisper expects and keeps files small.

### Environment bridging

The key listener (root) builds an environment for the client process by copying the desktop user's `DISPLAY`, `WAYLAND_DISPLAY`, `PULSE_SERVER`, `PULSE_RUNTIME_PATH`, and `XAUTHORITY`. `XAUTHORITY` is obtained either from a statically configured path or by reading `/proc/<pid>/environ` of a running user process (e.g. `ksmserver` on KDE).

### Typing via xdotool

Transcripts are typed with `xdotool type --clearmodifiers`. A trailing space is appended. After typing, a belt-and-suspenders `xdotool keyup` releases all modifier keys (Control, Alt, Shift, Super, Meta) to prevent stuck modifiers, which is a known issue on XWayland/Wayland.

### Recording indicator

The indicator is a `tkinter` overlay window with `overrideredirect(True)`, `-topmost`, and window-level alpha for semi-transparency. It uses `sounddevice` to capture live audio in a callback, computes FFT magnitudes per frame, applies EMA smoothing, maps frequencies to rainbow colors, and mirrors low-frequency bars for a symmetric visual. A `SIGUSR1` signal switches it from spectrogram to processing animation; `SIGTERM` kills it before the client types.

### Initial prompts for Whisper

The server passes language-specific `initial_prompt` strings to faster-whisper to bias transcription style: English prompts request clean transcription (no filler words, false starts); Czech prompts do the same in Czech.

### Device discovery with retry

The key listener finds the input device by matching the name (e.g. "input-remapper keyboard") against `/sys/class/input/event*/device/name`, retrying up to 10 times with a 2-second delay. This handles the case where input-remapper's virtual device is not yet created when the listener starts at boot.

## Testing Decisions

### What makes a good test

Tests verify external behavior at module seams — function inputs/outputs, subprocess command structure, socket protocol, and signal handling. Internal implementation details (e.g. Whisper internals, tkinter widget tree) are not tested directly. Tests use mocking for heavy or external dependencies: `faster_whisper` at import time, `subprocess.run` for xdotool/clipboard calls, `os.kill` for indicator signaling.

### Modules tested

- **`servers/key_listener.py`** — `find_device_by_name()` with real and fake devices; `setup_environment()` verifies environment variables; script paths point to real files; arecord subprocess can be spawned and terminated; client command structure includes `--indicator-pid` flag; `SIGUSR1` is available on the platform.
- **`servers/speech_to_text_server.py`** — `load_audio()` loads mono and stereo WAVs (converts stereo to mono), raises on missing file; `choose_model()` routes language to primary/secondary model; `handle_request()` returns `ok`/error response with mocked transcription; `recv_json()`/`send_json()` round-trip over a socketpair.
- **`scripts/speech_to_text_client.py`** — `send_request()` round-trips over a mocked socketpair, raises on missing file; `_clipboard_enabled()` respects config; `_copy_to_clipboard()` selects xclip/wl-copy based on environment; `type_text()` runs xdotool with correct arguments and appends space, does nothing for empty text; `release_modifiers()` sends keyup for all modifiers, never raises; argument parsing defaults language to `en` and parses `--indicator-pid`.

### Prior art

Tests use pytest with `unittest.mock` for mocking and `socket.socketpair()` for socket protocol tests — patterns consistent with the `conftest.py` that safely handles logging FileHandler in test environments.

## Out of Scope

- GUI configuration tool — configuration is done by editing Python source files directly.
- systemd service files — auto-start uses cron-based keepalive, not systemd units.
- Packaging as a .deb or snap — installation is manual via git clone and pip.
- Wayland-native typing — typing uses `xdotool`, which is X11-native (works on XWayland but may have edge cases on pure Wayland).
- Audio device selection — uses the default PulseAudio source; no UI or config for choosing a specific microphone.
- Multi-user support — assumes one desktop user per machine.
- Model download management — faster-whisper downloads models on first use; no progress UI or offline bundle.

## Further Notes

The project is MIT-licensed by CDNsun s.r.o. Tested on Kubuntu 24.04 LTS, Kali 2026.1, and Ubuntu 24.04 LTS. The recommended input device setup uses `input-remapper` to remap a side mouse button (`BTN_SIDE`) to F16, avoiding conflicts with browser navigation. `evtest` is the recommended tool for identifying the correct input device path.
