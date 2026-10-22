"""
app/bridge.py  -  Serial bridge for RemoteCloner (UI-free apart from a log signal).

- Opens/closes ports with ESP-safe DTR/RTS handling.
- Thread-safe command/reply via a per-link lock.
- learn (capture), send (raw / decoded), INFO query (firmware 1.1+), baud detect.
All blocking work must be called from worker threads (see workers.py).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import serial
from serial.tools import list_ports
from PyQt5.QtCore import QObject, pyqtSignal

RX = "receiver"
TX = "sender"
ROLES = (RX, TX)


class PortError(RuntimeError):
    """A port cannot be opened or does not respond."""


class RoleError(RuntimeError):
    """The board runs the wrong sketch for the requested role."""


class Link:
    """One open serial port shared by one or both roles."""

    def __init__(self, ser: serial.Serial, tag: str):
        self.ser = ser
        self.tag = tag
        self.lock = threading.Lock()


def _open_port(port: str, baud: int, *, dtr_rts_low: bool, settle_ms: int) -> serial.Serial:
    """ESP boards: build the Serial without a port, drop DTR/RTS, then open, so the
    chip is not put into download mode by pyserial asserting the lines."""
    if dtr_rts_low:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baud
        ser.timeout = 0.3
        ser.dtr = False
        ser.rts = False
        ser.open()
    else:
        ser = serial.Serial(port, baud, timeout=0.3)
    time.sleep(settle_ms / 1000.0)
    return ser


def port_items() -> List[Tuple[str, str]]:
    """(label, device) for every serial port."""
    items = []
    for p in list_ports.comports():
        desc = p.description if p.description and p.description != "n/a" else ""
        items.append((f"{p.device}  -  {desc}" if desc else p.device, p.device))
    return items


def port_usb_id(device: str) -> Optional[Tuple[int, int]]:
    for p in list_ports.comports():
        if p.device == device and p.vid is not None and p.pid is not None:
            return p.vid, p.pid
    return None


class Bridge(QObject):
    log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._links: Dict[str, Optional[Link]] = {RX: None, TX: None}

    # state -------------------------------------------------------------
    def has(self, role: str) -> bool:
        link = self._links[role]
        return link is not None and link.ser.is_open

    @property
    def connected(self) -> bool:
        return self.has(RX) or self.has(TX)

    def port_of(self, role: str) -> Optional[str]:
        link = self._links[role]
        return link.tag if link else None

    # open / close ------------------------------------------------------
    def connect_port(self, role: str, port: str, baud: int, *, dtr_rts_low: bool = False,
                     settle_ms: int = 2000) -> None:
        """Open a port and verify the board runs the sketch for `role`.
        Raises PortError or RoleError. Run on a worker thread."""
        self.disconnect(role)
        try:
            ser = _open_port(port, baud, dtr_rts_low=dtr_rts_low, settle_ms=settle_ms)
        except serial.SerialException as exc:
            raise PortError(f"Could not open {port}: {exc}\n"
                            "Check that no other program (for example the Arduino IDE serial "
                            "monitor) is using the port.") from exc

        link = Link(ser, port)
        try:
            ser.reset_input_buffer()
            reply = self._cmd(link, "P", timeout=2)
        except Exception as exc:
            ser.close()
            raise PortError(f"No reply from the board on {port} at {baud} baud.\n"
                            "Install the firmware on the Set up board page, check the cable, "
                            "and make sure the baud rate matches the firmware.") from exc

        if "PONG RECEIVER" in reply:
            found = {RX}
        elif "PONG SENDER" in reply:
            found = {TX}
        elif "PONG" in reply:
            found = {RX, TX}          # combined legacy sketch
        else:
            ser.close()
            raise PortError(f"Unexpected reply from {port}: {reply!r}\n"
                            "The board may have different firmware installed, or the baud rate is wrong.")

        if role not in found:
            ser.close()
            other = TX if TX in found else RX
            raise RoleError(f"This board runs the {other} sketch. "
                            f"Select it as the {other} board instead.")
        for r in found:
            self.disconnect(r)
            self._links[r] = link

    def disconnect(self, role: Optional[str] = None) -> None:
        for r in ([role] if role else list(ROLES)):
            link, self._links[r] = self._links[r], None
            if link is not None and link not in self._links.values():
                try:
                    link.ser.close()
                except Exception:
                    pass

    def disconnect_port(self, port: str) -> None:
        """Release a port by device name (used before flashing)."""
        for r in ROLES:
            if self.port_of(r) == port:
                self.disconnect(r)

    def close(self) -> None:
        self.disconnect()

    # serial I/O --------------------------------------------------------
    def _write(self, link: Link, text: str) -> None:
        self.log.emit(f"[{link.tag}] > {text[:120]}")
        link.ser.write((text + "\n").encode())

    def _read_line(self, link: Link, timeout: float) -> str:
        end = time.time() + timeout
        while time.time() < end:
            raw = link.ser.readline().decode(errors="ignore").strip()
            if raw:
                self.log.emit(f"[{link.tag}] < {raw[:120]}")
                return raw
        return ""

    def _cmd(self, link: Link, text: str, timeout: float = 1.0) -> str:
        if not link.lock.acquire(timeout=timeout + 1):
            return ""
        try:
            self._write(link, text)
            return self._read_line(link, timeout)
        finally:
            link.lock.release()

    # commands ----------------------------------------------------------
    def ping(self) -> List[str]:
        seen: List[Link] = []
        for link in self._links.values():
            if link and link not in seen:
                seen.append(link)
        return [self._cmd(link, "P") for link in seen]

    def query_info(self, role: str) -> Optional[Dict[str, str]]:
        """INFO (firmware 1.1+): dict of key=value, or None for v1.0 firmware. Never raises."""
        link = self._links[role]
        if link is None:
            return None
        try:
            reply = self._cmd(link, "I", timeout=1.5)
        except Exception:
            return None
        if not reply.startswith("INFO"):
            return None
        result = {}
        for token in reply[4:].split():
            if "=" in token:
                k, _, v = token.partition("=")
                result[k] = v
        return result or None

    def learn(self, cancel: threading.Event, timeout: float = 20) -> Optional[Dict[str, Any]]:
        """Capture one IR key. Returns a code dict, or None on timeout/cancel."""
        link = self._links[RX]
        if link is None:
            raise PortError("The receiver board is not connected.")
        with link.lock:
            link.ser.reset_input_buffer()
            self._write(link, "L")
            code: Dict[str, Any] = {}
            end = time.time() + timeout
            while time.time() < end and not cancel.is_set():
                line = self._read_line(link, 0.4)
                try:
                    if line.startswith("DEC"):
                        parts = line.split()
                        code.update(proto=int(parts[1]), name=" ".join(parts[2:-2]),
                                    addr=int(parts[-2]), cmd=int(parts[-1]))
                    elif line.startswith("RAW"):
                        _, khz_s, _, data = line.split(" ", 3)
                        code.update(khz=int(khz_s), raw=[int(x) for x in data.split(",")])
                        return code
                except (ValueError, IndexError):
                    continue            # malformed line: keep listening
                if line.startswith("ERR"):
                    raise RuntimeError("The capture was too long for the receiver's buffer "
                                       "(overflow). Use a board with a larger raw buffer."
                                       if "overflow" in line else line)
            self._write(link, "C")
            self._read_line(link, 0.5)
            return None

    def send(self, code: Dict[str, Any], mode: str = "raw", repeats: int = 0) -> str:
        """mode='decoded' uses the compact D command when the protocol is known."""
        link = self._links[TX]
        if link is None:
            raise PortError("The sender board is not connected.")
        if (mode == "decoded" and code.get("name") not in (None, "", "UNKNOWN") and "proto" in code):
            return self._cmd(link, f"D {code['proto']} {code['addr']} {code['cmd']} {repeats}")
        raw = code.get("raw", [])
        if not raw:
            raise ValueError("No raw timings in this key - cannot send.")
        reply = ""
        for _ in range(repeats + 1):
            reply = self._cmd(link, f"S {code.get('khz', 38)} {len(raw)} " + ",".join(map(str, raw)),
                              timeout=2.0)
            if repeats:
                time.sleep(0.05)
        return reply

    def detect_baud(self, role: str, port: str, bauds: List[int], *, dtr_rts_low: bool = False,
                    settle_ms: int = 500, progress_cb=None) -> Optional[int]:
        """First baud rate that gets a PONG, or None."""
        self.disconnect_port(port)
        for i, baud in enumerate(bauds):
            if progress_cb:
                progress_cb(baud, i, len(bauds))
            try:
                ser = _open_port(port, baud, dtr_rts_low=dtr_rts_low, settle_ms=settle_ms)
                ser.reset_input_buffer()
                ser.write(b"P\n")
                time.sleep(0.3)
                reply = ser.read(64).decode(errors="ignore")
                ser.close()
                if "PONG" in reply:
                    return baud
            except Exception:
                pass
        return None
