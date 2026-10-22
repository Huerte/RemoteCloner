from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                             QVBoxLayout)

from app.boards import all_boards, get_board
from app.bridge import RX, TX, port_items
from app.pages.base import Page
from app.ui import StatusDot, button, group, pad, page_header
from app.workers import BaudDetectWorker

ROLE_TITLE = {RX: "Receiver (capture)", TX: "Sender (transmit)"}


class ConnectionPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.rows = {}
        self.detect_thread = None
        self.hint = QLabel("No serial ports found. Plug in the board and choose Refresh ports.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.progress = QLabel()
        self.progress.setObjectName("muted")
        self.logw = QPlainTextEdit()
        self.logw.setObjectName("log")
        self.logw.setReadOnly(True)
        self.logw.setMaximumBlockCount(500)
        win.bridge.log.connect(self.logw.appendPlainText)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Connection", "Connect the receiver board (capture) and the sender board "
                                              "(transmit). Each runs its own sketch."))
        top = QHBoxLayout()
        top.addWidget(button("Refresh ports", self.refresh))
        top.addWidget(button("Ping", self.ping, tip="Ask every connected board to identify itself"))
        top.addWidget(self.progress, 1)
        v.addLayout(top)

        for role in (RX, TX):
            row = dict(dot=StatusDot(), board=QComboBox(), port=QComboBox(), baud=QComboBox(),
                       btn=button("Connect", lambda r=role: self.toggle(r)),
                       detect=button("Detect baud", lambda r=role: self.detect(r),
                                     tip="Try each baud rate until the board answers"),
                       state=QLabel())
            row["state"].setObjectName("muted")
            row["baud"].setMinimumWidth(200)
            for b in all_boards():
                row["board"].addItem(b.name, b.id)
            idx = row["board"].findData(win.settings.role_board(role))
            row["board"].setCurrentIndex(max(idx, 0))
            row["board"].currentIndexChanged.connect(lambda _=0, r=role: self.board_changed(r))
            self.rows[role] = row
            title = QLabel(ROLE_TITLE[role])
            title.setObjectName("h2")
            head = QHBoxLayout()
            head.setSpacing(10)
            head.addWidget(row["dot"])
            head.addWidget(title)
            head.addWidget(row["state"], 1)
            ctl = QHBoxLayout()
            ctl.setSpacing(10)
            ctl.addWidget(row["board"], 2)
            ctl.addWidget(row["port"], 3)
            ctl.addWidget(row["baud"], 1)
            ctl.addWidget(row["btn"])
            ctl.addWidget(row["detect"])
            v.addSpacing(6)
            v.addLayout(head)
            v.addLayout(ctl)
            self.fill_bauds(role)
        v.addWidget(self.hint)
        head = QHBoxLayout()
        head.addWidget(group("Serial log"))
        head.addStretch()
        head.addWidget(button("Clear log", self.logw.clear))
        v.addLayout(head)
        v.addWidget(self.logw, 1)

    # board / baud ---------------------------------------------------------
    def board(self, role):
        return get_board(self.rows[role]["board"].currentData())

    def fill_bauds(self, role):
        b, combo = self.board(role), self.rows[role]["baud"]
        saved = self.win.settings.role_baud(role) or b.serial_baud_default
        combo.blockSignals(True)
        combo.clear()
        for baud in b.serial_bauds:
            combo.addItem(b.baud_label(baud), baud)
        i = combo.findData(saved)
        combo.setCurrentIndex(i if i >= 0 else max(combo.findData(b.serial_baud_default), 0))
        combo.blockSignals(False)

    def board_changed(self, role):
        self.win.settings.save_role(role, board=self.board(role).id)
        self.win.settings.set(f"baud_{role}", 0)
        self.fill_bauds(role)

    def choose(self, role, *, board_id=None, port=None):
        """Called by the setup wizard / firmware page to pre-select values."""
        row = self.rows[role]
        if board_id:
            row["board"].setCurrentIndex(max(row["board"].findData(board_id), 0))
        if port:
            self.win.settings.save_role(role, port=port)
            i = row["port"].findData(port)
            if i >= 0:
                row["port"].setCurrentIndex(i)

    # view -----------------------------------------------------------------
    def refresh(self):
        items = port_items()
        for index, role in enumerate((RX, TX)):
            row = self.rows[role]
            keep = row["port"].currentData() or self.win.settings.role_port(role)
            row["port"].clear()
            for label, dev in items:
                row["port"].addItem(label, dev)
            i = row["port"].findData(keep)
            row["port"].setCurrentIndex(i if i >= 0 else min(index, row["port"].count() - 1))
        self.hint.setVisible(not items)
        self.update_state()

    def update_state(self):
        for role, row in self.rows.items():
            on = self.win.bridge.has(role)
            connecting = self.win.is_connecting(role)
            row["btn"].setText("Disconnect" if on else "Connecting…" if connecting else "Connect")
            row["btn"].setEnabled(not connecting)
            row["dot"].set_token("ok" if on else "warn" if connecting else "muted")
            for k in ("board", "port", "baud", "detect"):
                row[k].setEnabled(not on and not connecting and not self.detect_thread)
            info = self.win.info.get(role) if on else None
            if on:
                bits = [f"Connected on {self.win.bridge.port_of(role)}"]
                if info:
                    bits += [f"firmware {info['fw']}" if "fw" in info else "",
                             f"raw buffer {info['buf']}" if "buf" in info else "",
                             f"chip {info['chip']}" if "chip" in info else ""]
                else:
                    bits.append("firmware 1.0 (no INFO command)")
                row["state"].setText("  ·  ".join(b for b in bits if b))
            else:
                row["state"].setText("")

    def toggle(self, role):
        bridge, row = self.win.bridge, self.rows[role]
        if bridge.has(role):
            bridge.disconnect(role)
            self.win.info.pop(role, None)
            self.win.set_status()
            return
        port = row["port"].currentData()
        if not port:
            QMessageBox.information(self, "No port selected", "Choose a serial port first.")
            return
        self.win.connect_role(role, port, row["baud"].currentData(), self.board(role))

    def ping(self):
        if not self.win.bridge.connected:
            QMessageBox.information(self, "Not connected", "Connect a board first.")
            return
        self.win.bridge.ping()

    # baud detect ------------------------------------------------------------
    def detect(self, role):
        port = self.rows[role]["port"].currentData()
        if not port or self.detect_thread:
            return
        b = self.board(role)
        order = [b.serial_baud_default] + [x for x in b.serial_bauds if x != b.serial_baud_default]
        self.detect_thread = BaudDetectWorker(self.win.bridge, role, port, order,
                                              dtr_rts_low=b.reset_dtr_rts, settle_ms=max(b.post_open_settle_ms, 500))
        t = self.detect_thread
        t.progress.connect(lambda baud, i, n: self.progress.setText(f"Trying {baud} baud ({i + 1} of {n})…"))
        t.found.connect(self.detect_found)
        t.not_found.connect(self.detect_missing)
        self.update_state()
        t.start()

    def detect_over(self):
        t, self.detect_thread = self.detect_thread, None
        if t:
            t.wait(1500)
        self.update_state()

    def detect_found(self, role, _port, baud):
        self.detect_over()
        combo = self.rows[role]["baud"]
        if combo.findData(baud) < 0:
            combo.addItem(str(baud), baud)
        combo.setCurrentIndex(combo.findData(baud))
        self.progress.setText(f"The board answered at {baud} baud. Choose Connect.")

    def detect_missing(self, _role, _port):
        self.detect_over()
        self.progress.setText("No baud rate got a reply. Check the firmware is installed and the port is right.")

    def shutdown(self):
        if self.detect_thread:
            self.detect_thread.wait(8000)
