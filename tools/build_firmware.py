#!/usr/bin/env python3
"""
tools/build_firmware.py  -  Build the receiver/sender firmware with arduino-cli and
write firmware/manifest.json (SHA-256 of every image).

  python tools/build_firmware.py                    # build everything
  python tools/build_firmware.py --chip esp32       # one chip
  python tools/build_firmware.py --manifest-only    # just re-hash firmware/ (no compiler)

Pins and raw-buffer sizes come from app/boards.py, so the app and the firmware agree.
Requires arduino-cli with the cores and library below:
  arduino-cli core install arduino:avr esp32:esp32 esp8266:esp8266
  arduino-cli lib install IRremote@4.7.1
(Board manager URLs for esp32 and esp8266 must be configured in arduino-cli.)

AVR boards produce <role>_<chip>.hex. ESP32 boards produce the merged image
(bootloader + partitions + app, flashed at 0x0) as <role>_<chip>.bin. The ESP8266 image
is the single app binary, also flashed at 0x0.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.boards import all_boards   # noqa: E402  (no Qt imports in this module)

FW_VERSION = "1.1"
IRREMOTE_VERSION = "4.7.1"
SKETCH = {"receiver": ROOT / "arduino" / "ir_receiver", "sender": ROOT / "arduino" / "ir_sender"}
FIRMWARE = ROOT / "firmware"

# chip -> fully qualified board name for arduino-cli (one build per chip, shared by boards of that chip)
FQBN = {
    "atmega328p": "arduino:avr:uno",
    "atmega2560": "arduino:avr:mega:cpu=atmega2560",
    "atmega32u4": "arduino:avr:leonardo",
    "esp32": "esp32:esp32:esp32",
    "esp32s3": "esp32:esp32:esp32s3:CDCOnBoot=cdc",
    "esp32c3": "esp32:esp32:esp32c3:CDCOnBoot=cdc",
    "esp32s2": "esp32:esp32:esp32s2:CDCOnBoot=cdc",
    "esp8266": "esp8266:esp8266:nodemcuv2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pick_output(out: Path, is_esp: bool, chip: str) -> Path:
    if is_esp and chip != "esp8266":
        found = sorted(out.glob("*.merged.bin"))
    elif is_esp:
        found = sorted(p for p in out.glob("*.bin") if "merged" not in p.name)
    else:
        found = sorted(p for p in out.glob("*.hex") if "with_bootloader" not in p.name)
    if not found:
        raise RuntimeError(f"no firmware image found in {out}")
    return found[0]


def build_one(cli: str, board, role: str) -> Path:
    pin = board.rx_pin if role == "receiver" else board.tx_pin
    pin_macro = "IR_RECEIVE_PIN" if role == "receiver" else "IR_SEND_PIN"
    flags = (f"-DRAW_BUFFER_LENGTH={board.raw_buffer} -D{pin_macro}={pin} "
             f"-DSERIAL_BAUD={board.serial_baud_default} -DCHIP_NAME={board.chip}")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        cmd = [cli, "compile", "--fqbn", FQBN[board.chip], "--output-dir", str(out),
               "--build-property", f"build.extra_flags={flags}", str(SKETCH[role])]
        print(" ".join(cmd))
        subprocess.run(cmd, check=True)
        image = pick_output(out, board.is_esp, board.chip)
        dest = FIRMWARE / f"{board.firmware_stem(role)}{image.suffix}"
        shutil.copy(image, dest)
        return dest


def write_manifest(versions: dict[str, str]) -> None:
    files = {}
    for p in sorted(FIRMWARE.glob("*.hex")) + sorted(FIRMWARE.glob("*.bin")):
        stem = p.stem
        files[stem] = {"file": p.name, "sha256": sha256(p), "bytes": p.stat().st_size,
                       "fw": versions.get(stem, "unknown")}
    old = {}
    if (FIRMWARE / "manifest.json").exists():
        try:
            old = json.loads((FIRMWARE / "manifest.json").read_text())
        except Exception:
            pass
    manifest = {"generated": datetime.date.today().isoformat(), "irremote": IRREMOTE_VERSION or old.get("irremote"),
                "files": files}
    (FIRMWARE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote manifest.json ({len(files)} images)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chip", help="build only this chip (e.g. esp32)")
    ap.add_argument("--manifest-only", action="store_true")
    args = ap.parse_args()
    FIRMWARE.mkdir(exist_ok=True)

    old_versions = {}
    if (FIRMWARE / "manifest.json").exists():
        try:
            old_versions = {k: v.get("fw", "unknown")
                            for k, v in json.loads((FIRMWARE / "manifest.json").read_text())["files"].items()}
        except Exception:
            pass

    if args.manifest_only:
        write_manifest(old_versions)
        return 0

    cli = shutil.which("arduino-cli")
    if not cli:
        print("arduino-cli not found. Install it from https://arduino.github.io/arduino-cli/ and retry.")
        return 1
    versions = dict(old_versions)
    seen = set()
    for board in all_boards():
        if board.chip in seen or (args.chip and board.chip != args.chip):
            continue
        seen.add(board.chip)
        for role in ("receiver", "sender"):
            dest = build_one(cli, board, role)
            versions[dest.stem] = FW_VERSION
    write_manifest(versions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
