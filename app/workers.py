"""
app/workers.py  -  QThread workers for every blocking serial / flash-prep operation.
Workers emit typed signals; the UI updates widgets on the main thread.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from PyQt5.QtCore import QThread, pyqtSignal

from app.bridge import Bridge


class LearnWorker(QThread):
    """Capture one IR key from the receiver."""
    done = pyqtSignal(object)      # code dict or None
    failed = pyqtSignal(str)

    def __init__(self, bridge: Bridge, timeout: float = 20, parent=None):
        super().__init__(parent)
        self.bridge, self.timeout = bridge, timeout
        self.cancel = threading.Event()

    def run(self):
        try:
            self.done.emit(self.bridge.learn(self.cancel, self.timeout))
        except Exception as exc:
            self.failed.emit(str(exc))

    def stop(self):
        self.cancel.set()


class ConnectWorker(QThread):
    """Open a port, verify the role, then read the INFO line (if the firmware has one)."""
    connected = pyqtSignal(str, object)   # role, info dict or None
    failed = pyqtSignal(str, str)         # role, message

    def __init__(self, bridge: Bridge, role: str, port: str, baud: int, *,
                 dtr_rts_low: bool = False, settle_ms: int = 2000, parent=None):
        super().__init__(parent)
        self.bridge, self.role, self.port, self.baud = bridge, role, port, baud
        self.dtr_rts_low, self.settle_ms = dtr_rts_low, settle_ms

    def run(self):
        try:
            self.bridge.connect_port(self.role, self.port, self.baud,
                                     dtr_rts_low=self.dtr_rts_low, settle_ms=self.settle_ms)
            self.connected.emit(self.role, self.bridge.query_info(self.role))
        except Exception as exc:
            self.failed.emit(self.role, str(exc))


class BaudDetectWorker(QThread):
    progress = pyqtSignal(int, int, int)   # baud, index, total
    found = pyqtSignal(str, str, int)      # role, port, baud
    not_found = pyqtSignal(str, str)       # role, port

    def __init__(self, bridge: Bridge, role: str, port: str, bauds: List[int], *,
                 dtr_rts_low: bool = False, settle_ms: int = 300, parent=None):
        super().__init__(parent)
        self.bridge, self.role, self.port, self.bauds = bridge, role, port, bauds
        self.dtr_rts_low, self.settle_ms = dtr_rts_low, settle_ms

    def run(self):
        baud = self.bridge.detect_baud(self.role, self.port, self.bauds,
                                       dtr_rts_low=self.dtr_rts_low, settle_ms=self.settle_ms,
                                       progress_cb=lambda b, i, n: self.progress.emit(b, i, n))
        if baud is not None:
            self.found.emit(self.role, self.port, baud)
        else:
            self.not_found.emit(self.role, self.port)


class SendWorker(QThread):
    sent = pyqtSignal(str, str)    # key label, firmware reply
    failed = pyqtSignal(str, str)  # key label, message

    def __init__(self, bridge: Bridge, code: Dict[str, Any], mode: str = "raw",
                 repeats: int = 0, label: str = "", parent=None):
        super().__init__(parent)
        self.bridge, self.code, self.mode, self.repeats, self.label = bridge, code, mode, repeats, label

    def run(self):
        try:
            self.sent.emit(self.label, self.bridge.send(self.code, self.mode, self.repeats))
        except Exception as exc:
            self.failed.emit(self.label, str(exc))


class MacroWorker(QThread):
    step_done = pyqtSignal(str)
    step_error = pyqtSignal(str)
    completed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, bridge: Bridge, steps: List[str], keys: Dict[str, Any],
                 mode: str = "raw", repeats: int = 0, parent=None):
        super().__init__(parent)
        self.bridge, self.steps, self.keys, self.mode, self.repeats = bridge, steps, keys, mode, repeats
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _sleep(self, seconds: float) -> bool:
        """Sleep in small slices; return False if stopped."""
        end = time.time() + seconds
        while time.time() < end:
            if self._stop.is_set():
                return False
            time.sleep(0.02)
        return True

    def run(self):
        for step in self.steps:
            if self._stop.is_set():
                self.cancelled.emit()
                return
            s = step.strip()
            if not s:
                continue
            if s.isdigit():
                if not self._sleep(int(s) / 1000.0):
                    self.cancelled.emit()
                    return
                self.step_done.emit(f"delay {s} ms")
                continue
            key = s.upper().replace(" ", "_")
            if key not in self.keys:
                self.step_error.emit(f"Unknown key: {s}")
                continue
            try:
                self.bridge.send(self.keys[key], self.mode, self.repeats)
                self.step_done.emit(key)
            except Exception as exc:
                self.step_error.emit(f"{key}: {exc}")
                continue
            if not self._sleep(0.15):
                self.cancelled.emit()
                return
        self.completed.emit()


class TouchResetWorker(QThread):
    """Leonardo/Micro 1200-bps touch reset; waits for the bootloader port."""
    done = pyqtSignal(object)   # new port name or None

    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.port = port

    def run(self):
        from app.flasher import touch_reset_1200
        self.done.emit(touch_reset_1200(self.port))
