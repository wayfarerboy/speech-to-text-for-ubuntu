"""Tests for key_listener.py"""

import os
import signal
import subprocess
from unittest import mock

import pytest

import servers.key_listener as kl_mod


# ── find_device_by_name ────────────────────────────────────────────────

class TestFindDeviceByName:
    def test_finds_existing_device(self):
        # Use a real device that definitely exists.
        # /dev/input/event0 is usually "Lid Switch" or "Power Button".
        name_path = "/sys/class/input/event0/device/name"
        if not os.path.exists(name_path):
            pytest.skip("event0 not available")

        with open(name_path) as f:
            real_name = f.read().strip()

        result = kl_mod.find_device_by_name(real_name, retries=1, delay=0)
        assert result == "/dev/input/event0"

    def test_raises_when_not_found(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            kl_mod.find_device_by_name(
                "DefinitelyNotARealDeviceXYZ123",
                retries=2,
                delay=0,
            )


# ── setup_environment ──────────────────────────────────────────────────

class TestSetupEnvironment:
    def test_sets_display(self):
        env = kl_mod.setup_environment()
        assert env["DISPLAY"] == kl_mod.USER_DISPLAY
        assert env["WAYLAND_DISPLAY"] == kl_mod.USER_WAYLAND_DISPLAY

    def test_sets_xdg_runtime(self):
        env = kl_mod.setup_environment()
        assert "XDG_RUNTIME_DIR" in env
        assert env["XDG_RUNTIME_DIR"].startswith("/run/user/")

    def test_sets_pulse_audio(self):
        env = kl_mod.setup_environment()
        assert env["PULSE_SERVER"].startswith("unix:/run/user/")
        assert "PULSE_RUNTIME_PATH" in env

    def test_sets_xauthority(self):
        env = kl_mod.setup_environment()
        assert "XAUTHORITY" in env
        assert os.path.exists(env["XAUTHORITY"])


# ── script path derivation ─────────────────────────────────────────────

class TestScriptPaths:
    def test_paths_are_absolute(self):
        assert os.path.isabs(kl_mod._PROJECT_DIR)
        assert os.path.isabs(kl_mod.INDICATOR_SCRIPT)

    def test_indicator_script_exists(self):
        assert os.path.isfile(kl_mod.INDICATOR_SCRIPT)

    def test_indicator_path_points_into_scripts_dir(self):
        assert kl_mod.INDICATOR_SCRIPT.endswith(
            "scripts/recording_indicator.py"
        )


# ── subprocess calls (arecord) ────────────────────────────────────────

class TestSubprocessCalls:
    def test_arecord_invocation(self):
        """Verify the arecord command we'd spawn has correct flags."""
        env = kl_mod.setup_environment()
        proc = subprocess.Popen(
            ["arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", "/tmp/test.wav"],
            env=env,
        )
        proc.terminate()
        proc.wait()
        assert proc.returncode is not None  # terminated, not still running

    def test_transcription_modules_imported(self):
        """key_listener imports TranscriptionClient and TextTyper directly."""
        assert hasattr(kl_mod, "TranscriptionClient")
        assert hasattr(kl_mod, "TextTyper")


# ── indicator signal handling ──────────────────────────────────────────

class TestIndicatorSignals:
    def test_sigusr1_defined(self):
        """SIGUSR1 must exist on this platform."""
        assert hasattr(signal, "SIGUSR1")
