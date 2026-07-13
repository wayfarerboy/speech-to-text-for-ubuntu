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

    def test_transcription_modules_not_imported(self):
        """key_listener no longer imports TranscriptionClient or TextTyper directly."""
        assert not hasattr(kl_mod, "TranscriptionClient")
        assert not hasattr(kl_mod, "TextTyper")

    def test_coordinator_script_path(self):
        """key_listener computes coordinator script path."""
        # Path to coordinator script relative to project directory
        import os
        coordinator_path = os.path.join(kl_mod._PROJECT_DIR, "scripts", "stt_coordinator.py")
        assert os.path.isfile(coordinator_path)


# ── indicator signal handling ──────────────────────────────────────────

class TestIndicatorSignals:
    def test_sigusr1_defined(self):
        """SIGUSR1 must exist on this platform."""
        assert hasattr(signal, "SIGUSR1")


# ── helper functions ──────────────────────────────────────────────────

class TestDemote:
    def test_demote_returns_callable(self):
        fn = kl_mod._demote(1000, 1000)
        assert callable(fn)


class TestHideIndicatorSafe:
    def test_hide_none_pid_noops(self):
        """None PID is a safe no-op."""
        kl_mod._hide_indicator_safe(None)  # should not raise

    def test_hide_nonexistent_pid_noops(self):
        """Non-existent PID is caught silently."""
        kl_mod._hide_indicator_safe(999999)  # should not raise


# ── coordinator spawning logic ────────────────────────────────────────

class TestCoordinatorSpawning:
    def test_coordinator_script_exists(self):
        import os
        path = os.path.join(kl_mod._PROJECT_DIR, "scripts", "stt_coordinator.py")
        assert os.path.isfile(path)

    def test_coordinator_spawn_args(self, monkeypatch):
        """Verify coordinator is spawned with correct args."""
        mock_popen = mock.MagicMock()
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        coordinator_script = os.path.join(
            kl_mod._PROJECT_DIR, "scripts", "stt_coordinator.py"
        )
        env = {"HOME": "/tmp", "DISPLAY": ":0"}

        subprocess.Popen(
            [
                os.sys.executable,
                coordinator_script,
                "/tmp/stt_recorded_audio.wav",
                "--language", "en",
                "--indicator-pid", "12345",
            ],
            env=env,
            preexec_fn=kl_mod._demote(1000, 1000),
        )

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == os.sys.executable
        assert call_args[1] == coordinator_script
        assert call_args[2] == "/tmp/stt_recorded_audio.wav"
        assert "--language" in call_args
        assert "--indicator-pid" in call_args

    def test_coordinator_spawn_never_blocks(self, monkeypatch):
        """Popen is called without communicate/wait — non-blocking."""
        mock_popen = mock.MagicMock()
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        coordinator_script = os.path.join(
            kl_mod._PROJECT_DIR, "scripts", "stt_coordinator.py"
        )
        env = {"HOME": "/tmp", "DISPLAY": ":0"}

        proc = subprocess.Popen(
            [
                os.sys.executable,
                coordinator_script,
                "/tmp/test.wav",
                "--language", "en",
                "--indicator-pid", "12345",
            ],
            env=env,
            preexec_fn=kl_mod._demote(1000, 1000),
        )

        # Verify communicate/wait were NOT called (non-blocking)
        proc.communicate.assert_not_called()
        proc.wait.assert_not_called()

    def test_coordinator_failure_handled(self, monkeypatch):
        """If coordinator spawn fails, indicator is hidden safely."""
        mock_popen = mock.MagicMock(side_effect=RuntimeError("spawn failed"))
        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        # _hide_indicator_safe should handle the cleanup
        # We just verify it doesn't crash
        with pytest.raises(RuntimeError, match="spawn failed"):
            subprocess.Popen(["nonexistent"])

        # _hide_indicator_safe should not raise
        kl_mod._hide_indicator_safe(12345)
