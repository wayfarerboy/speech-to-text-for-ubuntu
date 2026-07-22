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

    def __init__(self, clipboard_enabled=None, env=None, user_uid=None, user_gid=None):
        self.clipboard_enabled = (
            clipboard_enabled
            if clipboard_enabled is not None
            else bool(str(config.COPY_TO_CLIPBOARD).strip())
        )
        self._env = env or os.environ
        self._uid = user_uid
        self._gid = user_gid

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

        # Release modifiers BEFORE typing — clean slate.
        # xdotool --clearmodifiers can inject modifier restore events
        # that collide with typed text on cold X11 start.
        self._release_modifiers()

        try:
            result = self._xdotool(
                ["type", "--delay", "5", text_to_type],
                timeout=config.TYPING_TIMEOUT,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("xdotool typed %d chars successfully", len(text))
            if result.stderr:
                logger.info("xdotool stderr: %s", result.stderr.strip())
        except subprocess.TimeoutExpired:
            logger.warning(
                "xdotool timed out after %ss — falling back to clipboard",
                config.TYPING_TIMEOUT,
            )
            self._safe_clipboard_fallback(text)
        except subprocess.CalledProcessError as e:
            logger.warning(
                "xdotool exited %s (stderr: %s) — falling back to clipboard",
                e.returncode, e.stderr.strip() if e.stderr else "none",
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

    def _run_as_user(self, cmd, timeout=None, **kwargs):
        """Run a command as the desktop user, not root."""
        popen_kwargs: dict = {"env": self._env}
        if "stdout" not in kwargs and "capture_output" not in kwargs:
            popen_kwargs["stdout"] = subprocess.DEVNULL
        if "stderr" not in kwargs and "capture_output" not in kwargs:
            popen_kwargs["stderr"] = subprocess.PIPE
        popen_kwargs.update(kwargs)
        if timeout is not None:
            popen_kwargs["timeout"] = timeout
        # Only demote if we're actually running as a different user (e.g. root).
        # When already the target user, preexec_fn is unnecessary and can break
        # when running via sg/newgrp (which locks the GID).
        if self._uid is not None and self._gid is not None and os.geteuid() != self._uid:
            def _drop():
                os.setgid(self._gid)
                os.setuid(self._uid)
            popen_kwargs["preexec_fn"] = _drop
        return subprocess.run(cmd, **popen_kwargs)

    def _xdotool(self, args, **kwargs):
        """Shortcut for xdotool commands run as the user."""
        return self._run_as_user(["xdotool"] + args, **kwargs)

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
            self._run_as_user(
                cmd,
                input=text,
                check=True,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except FileNotFoundError:
            logger.warning("Clipboard command not found: %s", cmd[0])
            return False
        except subprocess.CalledProcessError as e:
            logger.warning("Clipboard copy failed (exit %s)", e.returncode)
            return False

    def _release_modifiers(self):
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
            self._xdotool(
                ["keyup"] + modifiers,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass  # best-effort, never block
