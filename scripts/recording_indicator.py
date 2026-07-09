#!/usr/bin/env python3
"""
Recording indicator with live audio spectrogram.

Uses tkinter (reliable no-decorations via override-redirect) with
window-level alpha for semi-transparent background.  Rainbow FFT bars
drawn on a dark translucent backdrop.
"""

import math
import os
import re
import signal
import subprocess
import sys
import threading
import tkinter as tk

import numpy as np
import sounddevice as sd

# ── config ───────────────────────────────────────────────────────────
WIDTH = 100
HEIGHT = 32
BAR_COUNT = 30            # more bars = smoother spectrum
Y_OFFSET = 60
SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
FPS = 30
ALPHA = 0.6              # whole-window opacity
SMOOTH = 0.55            # EMA smoothing (higher = more responsive)
DB_FLOOR = -40           # dB floor for log scaling
PROCESS_SPEED = 2.0      # processing-wave scroll speed

# ── audio ring-buffer ─────────────────────────────────────────────────
_audio_buffer = np.zeros(BLOCK_SIZE, dtype=np.float32)
_buffer_lock = threading.Lock()
_stream = None


def audio_callback(indata, frames, time_info, status):
    global _audio_buffer
    if status:
        return
    with _buffer_lock:
        mono = indata[:, 0].astype(np.float32).copy() if indata.ndim > 1 else indata.astype(np.float32).copy()
        _audio_buffer[: len(mono)] = mono


def start_audio():
    global _stream
    try:
        _stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            callback=audio_callback,
            dtype=np.float32,
        )
        _stream.start()
    except Exception as e:
        print(f"Audio stream failed: {e}", file=sys.stderr)


def stop_audio():
    global _stream
    if _stream:
        try:
            _stream.stop()
            _stream.close()
        except Exception:
            pass
        _stream = None


# ── rainbow colour map ────────────────────────────────────────────────
def freq_to_color(i: int, total: int) -> str:
    hue = 0.66 - (i / max(total - 1, 1)) * 0.66
    h = hue * 6.0
    c = 1.0
    x = c * (1.0 - abs((h % 2.0) - 1.0))
    if h < 1:
        r, g, b = c, x, 0.0
    elif h < 2:
        r, g, b = x, c, 0.0
    elif h < 3:
        r, g, b = 0.0, c, x
    elif h < 4:
        r, g, b = 0.0, x, c
    elif h < 5:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


_prev_mags = None

def smooth_mags(mags: np.ndarray, alpha: float = SMOOTH) -> np.ndarray:
    global _prev_mags
    if _prev_mags is None or len(_prev_mags) != len(mags):
        _prev_mags = mags.copy()
        return mags
    _prev_mags = alpha * mags + (1.0 - alpha) * _prev_mags
    return _prev_mags


# ── monitor detection ─────────────────────────────────────────────────
def get_active_monitor_geometry(root: tk.Tk):
    px = root.winfo_pointerx()
    py = root.winfo_pointery()

    try:
        monitors = subprocess.check_output(
            ["/usr/bin/xrandr", "--query"], timeout=3, text=True,
        )
        for line in monitors.splitlines():
            if " connected" not in line:
                continue
            m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
            if m:
                mw, mh, mx, my = map(int, m.groups())
                if mx <= px < mx + mw and my <= py < my + mh:
                    return (mx, my, mw, mh)
    except Exception:
        pass

    try:
        monitors = subprocess.check_output(
            ["/usr/bin/xrandr", "--query"], timeout=3, text=True,
        )
        for line in monitors.splitlines():
            if " connected primary" in line:
                m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
                if m:
                    mw, mh, mx, my = map(int, m.groups())
                    return (mx, my, mw, mh)
    except Exception:
        pass

    return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())


# ── main ──────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.title("stt-indicator")
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    # Semi-transparent window
    root.configure(bg="black")
    root.attributes("-alpha", ALPHA)

    # Position
    root.update_idletasks()
    mx, my, mw, mh = get_active_monitor_geometry(root)
    root.withdraw()
    x = mx + (mw - WIDTH) // 2
    y = my + mh - HEIGHT - Y_OFFSET
    root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
    root.deiconify()

    # Canvas
    canvas = tk.Canvas(
        root, width=WIDTH, height=HEIGHT,
        bg="black", bd=0, highlightthickness=0,
    )
    canvas.pack(fill="both", expand=True)

    # Mode: "recording" → live spectrogram; "processing" → animated wave
    mode = "recording"
    frame_count = 0

    # Start audio
    start_audio()

    def draw():
        nonlocal frame_count
        frame_count += 1

        canvas.delete("all")

        if mode == "recording":
            # ── live spectrogram ─────────────────────────────
            with _buffer_lock:
                chunk = _audio_buffer.copy()

            windowed = chunk * np.hanning(len(chunk))
            fft = np.abs(np.fft.rfft(windowed))
            usable = fft[: len(fft) // 2]

            if len(usable) < BAR_COUNT:
                root.after(1000 // FPS, draw)
                return

            bins = np.array_split(usable, BAR_COUNT)
            mags = np.array([b.mean() for b in bins])
            mags = np.maximum(mags, 1e-8)
            mags_db = 20.0 * np.log10(mags)
            mags_db = np.clip(mags_db, DB_FLOOR, 0)
            mags_db = (mags_db - DB_FLOOR) / (-DB_FLOOR)
            speech_boost = np.linspace(1.5, 0.4, BAR_COUNT)
            mags_db = mags_db * speech_boost
            mags_db = np.clip(mags_db, 0, 1)
            mags = smooth_mags(mags_db)

            half = BAR_COUNT // 2
            low_half = mags[:half]
            mirrored = np.concatenate([low_half[::-1], low_half])

            bar_w = WIDTH / len(mirrored)
            mid_y = HEIGHT // 2
            max_bar_h = (HEIGHT - 6) // 2

            for i, mag in enumerate(mirrored):
                bar_h = max(1, int(mag * max_bar_h))
                x0 = i * bar_w
                x1 = x0 + bar_w
                y_top = mid_y - bar_h
                y_bot = mid_y + bar_h
                dist = abs(i - len(mirrored) // 2)
                color = freq_to_color(len(mirrored) // 2 - dist, len(mirrored) // 2 + 1)
                canvas.create_rectangle(x0, y_top, x1, mid_y, fill=color, outline="", width=0)
                canvas.create_rectangle(x0, mid_y, x1, y_bot, fill=color, outline="", width=0)

        else:
            # ── processing: sine-wave scroll (mirror-symmetric, centre-heavy) ─
            n = BAR_COUNT // 2
            mags = []
            for i in range(n):
                phase = (i / n) * math.pi * 1.8 + frame_count * 0.06
                mag = max(0.08, (math.sin(phase) + 1) / 2)
                mag *= 1.0 - (i / n) * 0.6  # speech-like: centre-heavy
                mags.append(mag)

            half = len(mags)
            low = mags
            mirrored = list(low[::-1]) + list(low)
            bar_w = WIDTH / len(mirrored)
            mid_y = HEIGHT // 2
            max_bar_h = (HEIGHT - 4) // 2

            for i, mag in enumerate(mirrored):
                bar_h = max(1, int(mag * max_bar_h))
                x0 = i * bar_w
                x1 = x0 + bar_w
                y_top = mid_y - bar_h
                y_bot = mid_y + bar_h
                color = "#ffffff"
                canvas.create_rectangle(x0, y_top, x1, mid_y, fill=color, outline="", width=0)
                canvas.create_rectangle(x0, mid_y, x1, y_bot, fill=color, outline="", width=0)

        root.after(1000 // FPS, draw)

    root.after(100, draw)

    def switch_to_processing(*_):
        nonlocal mode
        mode = "processing"
        stop_audio()

    def on_term(*_):
        stop_audio()
        root.destroy()

    signal.signal(signal.SIGUSR1, switch_to_processing)
    signal.signal(signal.SIGTERM, on_term)
    root.mainloop()
    stop_audio()


if __name__ == "__main__":
    main()
