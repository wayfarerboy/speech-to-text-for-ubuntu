"""TextTyper — type text into the focused window with xdotool."""

import logging
import os
import subprocess

import config

logger = logging.getLogger(__name__)


class TextTyper:
    """Type text at the current keyboard focus via xdotool.

    Interface: ``type(text)``.
    """

    def __init__(self, clipboard_enabled=None, env=None):
        self.clipboard_enabled = (
            clipboard_enabled
            if clipboard_enabled is not None
            else bool(str(config.COPY_TO_CLIPBOARD).strip())
        )
        self._env = env or os.environ

    def type(self, text):
        """Type *text* into the focused window, append a space,
        and optionally copy to clipboard.

        On xdotool timeout or failure: logs a warning, falls back
        to clipboard, and never raises.
        """
        text = text.strip()
        if not text:
            return

        text_to_type = text + " "
        if self.clipboard_enabled:
            try:
                self._copy_to_clipboard(text)
            except Exception:
                pass  # best-effort, never block typing

        try:
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", text_to_type],
                check=True,
                capture_output=True,
                text=True,
                timeout=config.TYPING_TIMEOUT,
                env=self._env,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "xdotool timed out after %ss — falling back to clipboard",
                config.TYPING_TIMEOUT,
            )
            self._safe_clipboard_fallback(text)
        except subprocess.CalledProcessError as e:
            logger.warning(
                "xdotool exited %s — falling back to clipboard",
                e.returncode,
            )
            self._safe_clipboard_fallback(text)
        except Exception as e:
            logger.warning("xdotool failed: %s — falling back to clipboard", e)
            self._safe_clipboard_fallback(text)
        finally:
            self._release_modifiers()

    def _safe_clipboard_fallback(self, text):
        """Try clipboard fallback; log if it also fails. Never raises."""
        try:
            self._copy_to_clipboard(text)
        except Exception as e:
            logger.warning("Clipboard fallback also failed: %s", e)

    # ── internal ──────────────────────────────────────────────────

    def _copy_to_clipboard(self, text):
        env = self._env
        if env.get("WAYLAND_DISPLAY"):
            cmd = ["wl-copy"]
        elif env.get("DISPLAY"):
            cmd = ["xclip", "-selection", "clipboard"]
        else:
            logger.warning("No clipboard tool available.")
            return False
        try:
            subprocess.run(
                cmd,
                input=text,
                check=True,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._env,
            )
            return True
        except FileNotFoundError:
            logger.warning("Clipboard command not found: %s", cmd[0])
            return False
        except subprocess.CalledProcessError as e:
            logger.warning("Clipboard copy failed (exit %s)", e.returncode)
            return False

    @staticmethod
    def _release_modifiers():
        """Release all modifier keys — belt-and-suspenders after xdotool.

        xdotool's --clearmodifiers is unreliable on XWayland/Wayland.
        """
        modifiers = [
            "Control_L", "Control_R",
            "Alt_L", "Alt_R",
            "Shift_L", "Shift_R",
            "Super_L", "Super_R",
            "Meta_L", "Meta_R",
        ]
        try:
            subprocess.run(
                ["xdotool", "keyup"] + modifiers,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass  # best-effort, never block
