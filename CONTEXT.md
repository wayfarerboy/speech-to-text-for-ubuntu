# Speech-to-Text for Ubuntu

Push-to-talk speech-to-text for Ubuntu desktops. Press a hotkey, speak, release — transcribed text is typed into the focused window.

## Language

**Transcription Session**:
One complete push-to-talk cycle: key press → recording → transcription → text input.
_Avoid_: Recording, session (overloaded)

**Key Listener**:
The root-privileged process that reads `/dev/input` events and spawns coordinators. Never blocks on transcription or typing.
_Avoid_: Hotkey daemon, input watcher

**Coordinator**:
A short-lived per-session process (runs as the desktop user) that transcribes audio via the STT server and types the result into the focused window. Timeout-killed if it hangs.
_Avoid_: Worker, client, transcription runner

**STT Server**:
The long-lived Whisper model server listening on a Unix socket. Loads models once at startup, handles transcription requests.
_Avoid_: Speech-to-text server, Whisper server

**Indicator**:
The persistent semi-transparent overlay window showing recording spectrogram and processing animation. Signal-driven (SIGUSR1/SIGUSR2/SIGTERM).
_Avoid_: Recording indicator, overlay

**Inputter**:
The typing mechanism that injects text into the focused window via `xdotool` (X11) or `wtype` (Wayland). Part of the coordinator, not a separate process.
_Avoid_: Text typer, key injector
