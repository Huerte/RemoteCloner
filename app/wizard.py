"""app/wizard.py  -  First-run quick setup: choose boards, see wiring, then install or connect."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QStackedWidget, QVBoxLayout)

from app.boards import all_boards, get_board, wiring_rows
from app.bridge import RX, TX
from app.ui import button, page_header


class SetupWizard(QDialog):
    """Result attributes after exec_(): action in {"install", "connect", None}."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.action = None
        self.setWindowTitle("Quick setup")
        self.resize(620, 460)
        self.stack = QStackedWidget()

        # step 1 ------------------------------------------------------------
        s1 = QLabel("RemoteCloner uses <b>two boards</b>:<br><br>"
                    "&bull; a <b>receiver</b> with an IR receiver module (VS1838B or TSOP38238) that captures "
                    "signals from your original remote,<br>"
                    "&bull; a <b>sender</b> with an IR LED and a transistor that replays them.<br><br>"
                    "Supported boards: Arduino Uno, Nano, Mega, Leonardo, Micro, ESP32 (DevKit, S2, S3, C3) "
                    "and ESP8266.<br><br>This quick setup picks your boards and shows the wiring.")
        s1.setWordWrap(True)
        s1.setTextFormat(Qt.RichText)
        self.stack.addWidget(self._wrap("Welcome", "Two boards, one for each job.", s1))

        # step 2 ------------------------------------------------------------
        self.combos = {}
        self.wire = {}
        form = QFormLayout()
        form.setVerticalSpacing(10)
        box = QVBoxLayout()
        for role, title in ((RX, "Receiver board"), (TX, "Sender board")):
            c = QComboBox()
            for b in all_boards():
                c.addItem(b.name, b.id)
            c.setCurrentIndex(max(c.findData(win.settings.role_board(role)), 0))
            c.currentIndexChanged.connect(self.update_wiring)
            self.combos[role] = c
            self.wire[role] = QLabel()
            self.wire[role].setObjectName("muted")
            self.wire[role].setWordWrap(True)
            form.addRow(title, c)
            form.addRow("", self.wire[role])
        w2 = self._wrap("Choose your boards", "The wiring shown here matches each board's pins.", None, form)
        self.stack.addWidget(w2)
        self.update_wiring()

        # step 3 ------------------------------------------------------------
        s3 = QLabel("Next, install the firmware on each board (a few seconds each). "
                    "If a board already runs the RemoteCloner firmware you can connect it directly.")
        s3.setWordWrap(True)
        self.never = QCheckBox("Do not show this again")
        self.never.setChecked(True)
        v3 = QVBoxLayout()
        v3.addWidget(s3)
        v3.addWidget(self.never)
        self.stack.addWidget(self._wrap("Ready", "Install the firmware, or connect boards that already have it.",
                                        None, v3))

        self.back = button("Back", self.prev)
        self.next = button("Next", self.advance, "primary")
        self.install = button("Install firmware", lambda: self.finish("install"), "primary")
        self.connect_btn = button("Connect boards", lambda: self.finish("connect"))
        self.skip = button("Skip", self.reject)
        row = QHBoxLayout()
        row.addWidget(self.skip)
        row.addStretch()
        for b in (self.back, self.next, self.connect_btn, self.install):
            row.addWidget(b)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.addWidget(self.stack, 1)
        outer.addLayout(row)
        self.sync()

    def _wrap(self, title, sub, widget=None, layout=None):
        from PyQt5.QtWidgets import QWidget
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addLayout(page_header(title, sub))
        if widget is not None:
            v.addWidget(widget)
        if layout is not None:
            v.addLayout(layout)
        v.addStretch()
        return w

    def update_wiring(self):
        for role, label in self.wire.items():
            b = get_board(self.combos[role].currentData())
            rows = wiring_rows(b.id, role)
            label.setText("; ".join(f"{s} -> {p}" for s, p, _ in rows) +
                          (f"  ({b.raw_buffer}-pulse buffer)" if b.raw_buffer < 750 else ""))

    def sync(self):
        i, n = self.stack.currentIndex(), self.stack.count()
        self.back.setVisible(i > 0)
        self.next.setVisible(i < n - 1)
        self.install.setVisible(i == n - 1)
        self.connect_btn.setVisible(i == n - 1)

    def prev(self):
        self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
        self.sync()

    def advance(self):
        self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
        self.sync()

    def finish(self, action):
        s = self.win.settings
        for role, c in self.combos.items():
            s.save_role(role, board=c.currentData())
            s.set(f"baud_{role}", 0)
        if self.never.isChecked():
            s.set("wizard_done", True)
        self.action = action
        self.accept()

    def reject(self):
        if self.never.isChecked():
            self.win.settings.set("wizard_done", True)
        super().reject()
