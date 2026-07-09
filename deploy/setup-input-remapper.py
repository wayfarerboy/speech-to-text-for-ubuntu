#!/usr/bin/env python3
"""
Set up input-remapper preset for speech-to-text trigger keys.

Detects keyboard devices, computes the origin_hash, and creates a preset
that maps your chosen key to KEY_F16 (and optionally KEY_F17).

Usage:
  sudo python3 deploy/setup-input-remapper.py
"""

import hashlib
import json
import os
import struct
import subprocess
import sys

CONFIG_DIR = os.path.expanduser("~/.config/input-remapper-2")
PRESETS_DIR = os.path.join(CONFIG_DIR, "presets")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def get_device_hash(device_path: str) -> str:
    """Compute input-remapper origin_hash from a /dev/input/event* device."""
    name = os.path.basename(device_path)
    base = f"/sys/class/input/{name}/device/id"
    bus = int(open(f"{base}/bustype").read().strip(), 16)
    vendor = int(open(f"{base}/vendor").read().strip(), 16)
    product = int(open(f"{base}/product").read().strip(), 16)
    version = int(open(f"{base}/version").read().strip(), 16)
    return hashlib.md5(struct.pack("HHHH", bus, vendor, product, version)).hexdigest()


def list_keyboard_devices():
    """Return [(event_path, device_name), ...] for likely keyboard devices."""
    import glob
    devices = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            name_path = f"/sys/class/input/{os.path.basename(path)}/device/name"
            with open(name_path) as f:
                name = f.read().strip()
            # Filter to input devices that are likely keyboards
            if any(kw in name.lower() for kw in ("keyboard", "translated set", "gpio-keys")):
                devices.append((path, name))
        except (IOError, OSError):
            continue
    return devices


def pick_key_code():
    """Ask user what physical key to map."""
    print("\nCommon key codes:")
    print("  226 = KEY_MEDIA  (dedicated media key)")
    print("  275 = BTN_SIDE   (side mouse button)")
    print("  276 = BTN_EXTRA  (extra mouse button)")
    print("  142 = KEY_SLEEP")
    print("  150 = KEY_WWW")
    print("\nRun 'sudo evtest' and press your key to find the code if unsure.")
    code = input("\nKey code to map → KEY_F16 [default: 226]: ").strip()
    return int(code) if code else 226


def main():
    if os.geteuid() != 0:
        print("Must run as root (sudo).", file=sys.stderr)
        sys.exit(1)

    print("=== input-remapper setup for speech-to-text ===\n")

    # 1. Find keyboard device
    devices = list_keyboard_devices()
    if not devices:
        print("No keyboard devices found.", file=sys.stderr)
        sys.exit(1)

    print("Keyboard devices found:")
    for i, (path, name) in enumerate(devices):
        print(f"  [{i}] {path} — {name}")

    choice = input(f"\nPick device [0-{len(devices)-1}, default: 0]: ").strip()
    idx = int(choice) if choice else 0
    device_path, device_name = devices[idx]
    print(f"  Using: {device_path} ({device_name})")

    # 2. Compute hash
    origin_hash = get_device_hash(device_path)
    print(f"  origin_hash: {origin_hash}")

    # 3. Pick key code
    key_code = pick_key_code()

    # 4. Ask about second language
    second = input("\nAdd a second key for secondary language? (y/n) [n]: ").strip().lower()

    # 5. Create preset
    safe_name = device_name.replace("/", "_").replace(" ", "_")
    preset_dir = os.path.join(PRESETS_DIR, safe_name)
    os.makedirs(preset_dir, exist_ok=True)

    mappings = [
        {
            "input_combination": [
                {
                    "type": 1,  # EV_KEY
                    "code": key_code,
                    "origin_hash": origin_hash,
                }
            ],
            "target_uinput": "keyboard",
            "output_symbol": "KEY_F16",
            "mapping_type": "key_macro",
        }
    ]

    if second == "y":
        code2 = input("Key code for KEY_F17: ").strip()
        mappings.append(
            {
                "input_combination": [
                    {
                        "type": 1,
                        "code": int(code2),
                        "origin_hash": origin_hash,
                    }
                ],
                "target_uinput": "keyboard",
                "output_symbol": "KEY_F17",
                "mapping_type": "key_macro",
            }
        )

    preset_path = os.path.join(preset_dir, "transcribe.json")
    with open(preset_path, "w") as f:
        json.dump(mappings, f, indent=4)
    print(f"\n  Wrote preset: {preset_path}")

    # 6. Enable autoload
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            config = json.load(f)

    config.setdefault("autoload", {})[device_name] = "transcribe"

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    print(f"  Autoload enabled in {CONFIG_FILE}")

    # 7. Reload input-remapper
    try:
        subprocess.run(
            ["input-remapper-control", "--command", "autoload"],
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("\n  input-remapper reloaded.")
    except Exception:
        print("\n  Could not reload input-remapper automatically.")
        print("  Restart input-remapper or run: input-remapper-control --command autoload")

    print("\n=== Done ===")
    print(f"Pressing key code {key_code} will now trigger KEY_F16 → speech-to-text.")


if __name__ == "__main__":
    main()
