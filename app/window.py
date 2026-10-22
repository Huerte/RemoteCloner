"""app/window.py  -  Main window: navigation, shared state, connection management."""

from __future__ import annotations

from typing import Dict, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                             QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from app import theme
from app.boards import Board, board_or_default
from app.bridge import RX, TX, Bridge, port_items
from app.pages.clone import ClonePage
from app.pages.connection import ConnectionPage
from app.pages.control import ControlPage
from app.pages.firmware import FirmwarePage
from app.pages.help_page import HelpPage
from app.pages.home import HomePage
from app.pages.library import LibraryPage
from app.pages.settings_page import SettingsPage
from app.settings import AppSettings
from app.store import Store
from app.ui import StatusDot, shortcut
from app.wizard import SetupWizard
from app.workers import ConnectWorker

# (key, label, page class) in navigation order.
NAV = [("home", "Home", HomePage), ("clone", "Clone remote", ClonePage), ("library", "Library", LibraryPage),
       ("control", "Control panel", ControlPage), ("connection", "Connection", ConnectionPage),
       ("firmware", "Set up board", FirmwarePage), ("settings", "Settings", SettingsPage),
       ("help", "Help", HelpPage)]


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RemoteCloner")
        self.resize(1120, 700)
        self.setMinimumSize(980, 600)
        self.settings = AppSettings()
        self.store = Store()
        self.bridge = Bridge(self)
        self.info: Dict[str, dict] = {}
        self._connecting: Dict[str, ConnectWorker] = {}
        self.current: Optional[str] = self.settings.get("remote", None) or None

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.addItems([label for _, label, _ in NAV])
        self.stack = QStackedWidget()
        self.keys = [k for k, _, _ in NAV]
        self.pages = {}
        for key, _label, cls in NAV:
            page = cls(self)
            self.pages[key] = page
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.goto)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 22, 0, 12)
        sv.setSpacing(14)
        brand = QLabel("RemoteCloner")
        brand.setObjectName("brand")
        sv.addWidget(brand)
        sv.addWidget(self.nav, 1)
        c = QWidget()
        h = QHBoxLayout(c)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(c)

        self.dot, self.conn = StatusDot(), QLabel()
        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(8, 0, 8, 0)
        bl.setSpacing(8)
        bl.addWidget(self.dot)
        bl.addWidget(self.conn)
        self.statusBar().addPermanentWidget(box)
        self.set_status()

        for i in range(len(NAV)):
            self.nav.item(i).setToolTip(f"Ctrl+{i + 1}")
            shortcut(self, f"Ctrl+{i + 1}", lambda i=i: self.goto(i), Qt.WindowShortcut)
        shortcut(self, "Ctrl+N", self.new_remote, Qt.WindowShortcut)
        self.nav.setCurrentRow(0)
        QTimer.singleShot(300, self.autoconnect)
        QTimer.singleShot(600, self.maybe_wizard)

    # navigation -------------------------------------------------------------
    def index_of(self, key: str) -> int:
        return self.keys.index(key)

    def goto(self, where):
        i = self.index_of(where) if isinstance(where, str) else where
        if not 0 <= i < len(self.keys):
            return
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(i)
        self.nav.blockSignals(False)
        self.stack.setCurrentIndex(i)
        self.pages[self.keys[i]].refresh()

    def refresh_all(self):
        if self.current:
            self.settings.set("remote", self.current)
        self.pages[self.keys[self.stack.currentIndex()]].refresh()

    # remotes ----------------------------------------------------------------
    load_error = None   # set by data() when the current remote file cannot be read

    def data(self):
        self.load_error = None
        if not self.current:
            return None
        try:
            return self.store.load(self.current)
        except Exception as exc:
            self.load_error = (f"“{self.current}” could not be read ({exc}). "
                               "The file is damaged. Fix or delete it in the remotes folder.")
            return None

    def put(self, d):
        if self.current:
            self.store.save(self.current, d)

    def new_remote(self):
        n, ok = QInputDialog.getText(self, "New remote", "Remote name (for example Living room TV):")
        n = Store.safe_name(n)
        if not (ok and n):
            return
        if self.store.exists(n):
            QMessageBox.information(self, "Remote exists", "A remote with that name already exists.")
            return
        self.store.create(n)
        self.current = n
        self.refresh_all()

    # appearance -------------------------------------------------------------
    def apply_appearance(self):
        theme.apply_theme(QApplication.instance(), self.settings.theme, self.settings.font_scale)
        self.set_status()
        self.pages["help"].render()

    # connection ---------------------------------------------------------------
    def is_connecting(self, role: str) -> bool:
        return role in self._connecting

    def set_status(self):
        rx, tx = self.bridge.has(RX), self.bridge.has(TX)
        text = {(True, True): "Receiver and sender connected",
                (True, False): "Receiver connected, sender not connected",
                (False, True): "Sender connected, receiver not connected",
                (False, False): "No boards connected"}[(rx, tx)]
        if self._connecting:
            text = "Connecting…"
        self.dot.set_token("ok" if rx and tx else "warn" if rx or tx or self._connecting else "muted")
        self.conn.setText(text)
        self.pages["connection"].update_state()

    def connect_role(self, role: str, port: str, baud: Optional[int], board: Optional[Board] = None,
                     quiet: bool = False):
        """Connect on a worker thread so the UI never freezes during the board reset delay."""
        if role in self._connecting:
            return
        board = board or board_or_default(self.settings.role_board(role))
        baud = baud or board.serial_baud_default
        w = ConnectWorker(self.bridge, role, port, baud, dtr_rts_low=board.reset_dtr_rts,
                          settle_ms=board.post_open_settle_ms)
        self._connecting[role] = w
        w.connected.connect(lambda r, info, p=port, b=baud, bd=board: self._connected(r, info, p, b, bd))
        w.failed.connect(lambda r, msg, q=quiet: self._connect_failed(r, msg, q))
        self.set_status()
        w.start()

    def _finish_connect(self, role):
        w = self._connecting.pop(role, None)
        if w:
            w.wait(1500)

    def _connected(self, role, info, port, baud, board):
        self._finish_connect(role)
        self.info[role] = info or {}
        self.settings.save_role(role, port=port, board=board.id, baud=baud)
        self.set_status()

    def _connect_failed(self, role, msg, quiet):
        self._finish_connect(role)
        self.info.pop(role, None)
        self.set_status()
        if not quiet:
            QMessageBox.warning(self, "Connection failed", msg)

    def autoconnect(self):
        if not self.settings.autoconnect:
            return
        available = {dev for _label, dev in port_items()}
        for role in (RX, TX):
            port = self.settings.role_port(role)
            if port and port in available and not self.bridge.has(role):
                self.connect_role(role, port, self.settings.role_baud(role), quiet=True)

    def ensure_connected(self, role: str) -> bool:
        if self.bridge.has(role):
            return True
        QMessageBox.information(self, f"{role.capitalize()} not connected",
                                f"Connect the {role} board first. Choose its port on the Connection page.")
        self.goto("connection")
        return False

    # wizard -------------------------------------------------------------------
    def maybe_wizard(self):
        if not self.settings.wizard_done and not any(self.settings.role_port(r) for r in (RX, TX)):
            self.run_wizard()

    def run_wizard(self):
        dlg = SetupWizard(self)
        if not dlg.exec_():
            return
        conn, fw = self.pages["connection"], self.pages["firmware"]
        for role in (RX, TX):
            conn.choose(role, board_id=self.settings.role_board(role))
        if dlg.action == "install":
            fw.select(RX, self.settings.role_board(RX))
            self.goto("firmware")
        else:
            self.goto("connection")

    # shutdown -----------------------------------------------------------------
    def closeEvent(self, e):
        clone = self.pages["clone"]
        if clone.thread:
            clone.thread.stop()
            clone.thread.wait(1500)
        for key in ("control", "connection", "firmware"):
            self.pages[key].shutdown()
        for w in list(self._connecting.values()):
            w.wait(5000)
        self.bridge.close()
        e.accept()
