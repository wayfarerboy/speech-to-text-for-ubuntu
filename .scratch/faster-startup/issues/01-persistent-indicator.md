# 01: Persistent recording indicator

**Status:** resolved
**Blocked by:** None — can start immediately.

## What to build

The recording indicator currently spawns as a new Python subprocess on every key press, importing tkinter + numpy + sounddevice each time (~250ms). Make it a persistent process that is spawned once at key_listener startup and controlled through signals, so `show("recording")` becomes a near-instant signal delivery instead of a full process launch.

From the user's perspective: the indicator window appears immediately on key press. Recording starts at ~130ms (arecord Popen → capturing) instead of ~250ms.

## Signals (lifecycle contract)

The persistent indicator starts **withdrawn** (hidden), no audio stream active.

| Signal | Effect |
|--------|--------|
| `SIGUSR1` | **Show recording:** deiconify window, start audio stream, spectrogram mode |
| `SIGUSR2` | **Show processing:** switch to processing animation, stop audio stream |
| `SIGTERM` | **Hide:** withdraw window, stop audio, reset to ready state |

The `ProcessIndicator` adapter manages these signals and kills the process on `close()`.

## Acceptance criteria

- [ ] Indicator process spawns once at key_listener startup (hidden)
- [ ] First key press → indicator window appears (recording spectrogram) in <5ms
- [ ] Key release → indicator switches to processing animation
- [ ] Transcription complete → indicator hides (withdrawn, ready for next use)
- [ ] Second key press → indicator shows again (no new process spawned)
- [ ] Key_listener shutdown → indicator process is killed
- [ ] Client script no longer kills the indicator by PID (indicator outlives sessions)
- [ ] Existing tests updated; new tests for signal-based show/hide lifecycle
- [ ] Timing harness shows `indicator.show("recording")` <5ms (was ~250ms)

## Comments

Diagnosis from `_debug/startup_timing_v3.py`:

| Component | Before |
|-----------|--------|
| Indicator cold start | 315 ms |
| Indicator warm start | 218 ms |
| Python imports (tkinter+numpy+sounddevice) | 257 ms |
| arecord startup | ~130 ms |
| End-to-end (keypress → recording) | ~250 ms |

Expected after: indicator <5ms, end-to-end ~130ms.
