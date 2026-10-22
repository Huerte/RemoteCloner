"""
app/flasher.py  -  Firmware flashing for AVR (avrdude) and ESP (esptool).

FlashProcess wraps QProcess so the UI connects to the same line_out / succeeded /
failed signals for both tools. firmware/manifest.json locates .hex/.bin files and
their SHA-256 hashes; a missing or mismatching file is reported before flashing.

ESP images are the *merged* binaries (bootloader + partitions + app) written at 0x0.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import QObject, QProcess, pyqtSignal

from app.boards import Board

AVRDUDE_DIR = Path(__file__).parent.parent / "tools" / "avrdude"
FIRMWARE_DIR = Path(__file__).parent.parent / "firmware"


def load_manifest() -> dict:
    p = FIRMWARE_DIR / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def firmware_path(board: Board, role: str) -> Path:
    ext = "bin" if board.is_esp else "hex"
    return FIRMWARE_DIR / f"{board.firmware_stem(role)}.{ext}"


def verify_sha256(path: Path, expected: str) -> bool:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower() == expected.lower()


def firmware_status(board: Board, role: str) -> Tuple[Optional[Path], Optional[str]]:
    """(path, error). path is set when the file exists and its hash matches the manifest."""
    p = firmware_path(board, role)
    manifest = load_manifest()
    key = board.firmware_stem(role)
    if not p.exists():
        if board.is_esp:
            return None, (f"The {role} firmware for {board.name} has not been built yet.\n"
                          "Build it with:  python tools/build_firmware.py  (needs arduino-cli), "
                          "or download the firmware from the repository's releases.")
        if manifest and key not in manifest.get("files", {}):
            return None, (f"Firmware for {board.name} ({role}) has not been built yet.\n"
                          "Run:  python tools/build_firmware.py")
        return None, (f"Firmware file '{p.name}' is missing from the firmware folder.\n"
                      "Restore it with:  git checkout -- firmware")
    info = manifest.get("files", {}).get(key, {})
    if info.get("sha256") and not verify_sha256(p, info["sha256"]):
        return None, (f"Firmware file '{p.name}' does not match its checksum in the manifest. "
                      "Rebuild the firmware or restore the file from git.")
    return p, None


# avrdude ---------------------------------------------------------------
def find_avrdude() -> Tuple[Optional[str], Optional[str]]:
    exe = AVRDUDE_DIR / ("avrdude.exe" if sys.platform == "win32" else "avrdude")
    if exe.exists():
        conf = AVRDUDE_DIR / "avrdude.conf"
        return str(exe), (str(conf) if conf.exists() else None)
    return shutil.which("avrdude"), None


def avr_args(board: Board, port: str, hex_path: Path, conf: Optional[str],
             baud: Optional[int] = None) -> List[str]:
    args: List[str] = ["-C", conf] if conf else []
    return args + ["-p", board.avr_part, "-c", board.avr_prog, "-P", port,
                   "-b", str(baud or board.flash_baud), "-D", "-U", f"flash:w:{hex_path}:i"]


# esptool ---------------------------------------------------------------
def esptool_available() -> bool:
    """True when `python -m esptool` can run (esptool is a pip dependency)."""
    import importlib.util
    return importlib.util.find_spec("esptool") is not None


def esp_args(board: Board, port: str, bin_path: Path,
             baud: Optional[int] = None) -> Tuple[str, List[str]]:
    """(program, args) for esptool write_flash of a merged image at 0x0."""
    program = sys.executable
    args = ["-m", "esptool", "--chip", board.esp_chip or "auto", "--port", port,
            "--baud", str(baud or board.flash_baud), "--before", "default_reset",
            "--after", "hard_reset", "write_flash", "-z", "0x0", str(bin_path)]
    return program, args


# Leonardo / Micro 1200-bps touch reset ----------------------------------
def touch_reset_1200(port: str, timeout: float = 10.0) -> Optional[str]:
    """Open at 1200 baud to enter the bootloader; return the (possibly new) port or None."""
    import serial
    from serial.tools import list_ports

    before = {p.device for p in list_ports.comports()}
    try:
        with serial.Serial(port, 1200, timeout=0.1) as ser:
            ser.dtr = False
            time.sleep(0.1)
    except Exception:
        pass
    # Give the board time to drop off the bus; otherwise the old port still
    # looks present and we would return it before the bootloader shows up.
    deadline = time.time() + timeout
    vanished = False
    while time.time() < deadline:
        time.sleep(0.2)
        after = {p.device for p in list_ports.comports()}
        new_ports = after - before
        if new_ports:
            return sorted(new_ports)[0]      # bootloader enumerated on a new name
        if port not in after:
            vanished = True
        elif vanished:
            return port                       # same name came back (Linux/macOS)
    # Timed out: some systems never drop the port, so fall back to the original.
    after = {p.device for p in list_ports.comports()}
    return port if port in after else None


class FlashProcess(QObject):
    """QProcess wrapper. Signals: line_out(str), succeeded(role, board, port), failed(reason)."""

    line_out = pyqtSignal(str)
    succeeded = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc: Optional[QProcess] = None
        self._raw = ""
        self._role = self._board_name = self._port = ""
        self._reported = False

    @property
    def running(self) -> bool:
        return bool(self._proc and self._proc.state() != QProcess.NotRunning)

    def start(self, program: str, args: List[str], role: str, board_name: str, port: str):
        if self.running:
            return
        self._raw, self._reported = "", False
        self._role, self._board_name, self._port = role, board_name, port
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.MergedChannels)
        self._proc.readyRead.connect(self._on_read)
        self._proc.errorOccurred.connect(self._on_error)
        self._proc.finished.connect(self._on_finished)
        self.line_out.emit(f"{program} {' '.join(args)}")
        self._proc.start(program, args)

    def abort(self):
        if self.running:
            self._reported = True
            self._proc.kill()
            self._proc.waitForFinished(1500)

    def _on_read(self):
        text = bytes(self._proc.readAll()).decode(errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
        self._raw += text
        for line in text.splitlines():
            line = line.rstrip()
            if line and not ("|" in line and "%" in line and "100%" not in line):
                self.line_out.emit(line)

    def _on_error(self, error):
        if error == QProcess.FailedToStart and not self._reported:
            self._reported = True
            self.failed.emit("The flash tool could not be started.\n"
                             "For AVR boards check the tools/avrdude folder.\n"
                             "For ESP boards install esptool:  pip install esptool")

    def _on_finished(self, code, _status):
        self._on_read()
        if self._reported:
            return
        self._reported = True
        if code == 0:
            self.succeeded.emit(self._role, self._board_name, self._port)
        else:
            self.failed.emit(self._human_error())

    def _human_error(self) -> str:
        low = self._raw.lower()
        if any(s in low for s in ("can't open device", "cannot open", "access is denied",
                                   "ioctl", "no such file or directory", "could not open port",
                                   "permission")):
            return ("The port is busy or missing. Close the Arduino IDE serial monitor and any "
                    "other program using the port, then try again.")
        if any(s in low for s in ("not in sync", "getsync", "no response", "timeout", "stk500_recv")):
            return ("The board did not respond to the installer.\n"
                    "- Check the board type (older Nano boards need 'old bootloader').\n"
                    "- Try a different USB cable or port.\n"
                    "- Press the board's RESET button just before clicking Install.")
        if "failed to connect" in low:
            return ("esptool could not connect to the ESP chip.\n"
                    "- Hold BOOT, press RESET, release BOOT, then click Install.\n"
                    "- Make sure no other program is using the port.")
        if "a fatal error occurred" in low:
            return ("esptool reported a fatal error.\n"
                    "- Hold BOOT (IO0), press RESET, release BOOT, then try again.\n"
                    "- Tick 'Slower flash speed' or try a different USB cable.")
        return "The installer reported an error. See the installer output for details."
