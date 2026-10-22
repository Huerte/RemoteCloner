from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit,
                             QVBoxLayout)

from app.boards import all_boards, find_by_vid_pid, get_board, wiring_rows
from app.bridge import RX, TX, port_items, port_usb_id
from app.flasher import (FlashProcess, avr_args, esp_args, esptool_available, find_avrdude,
                         firmware_status)
from app.pages.base import Page
from app.ui import StatePanel, button, confirm, group, pad, page_header
from app.workers import TouchResetWorker

ROLE_TITLE = {RX: "Receiver (capture)", TX: "Sender (transmit)"}


class FirmwarePage(Page):
    """Installs the bundled receiver/sender firmware with avrdude (AVR) or esptool (ESP)."""

    def __init__(self, win):
        super().__init__(win)
        self.flash = FlashProcess(self)
        self.flash.line_out.connect(lambda l: self.logw.appendPlainText(l))
        self.flash.succeeded.connect(self.on_success)
        self.flash.failed.connect(self.on_failure)
        self.touch = None
        self.job = None

        self.role = QComboBox()
        for r in (RX, TX):
            self.role.addItem(ROLE_TITLE[r], r)
        self.board = QComboBox()
        for b in all_boards():
            self.board.addItem(b.name, b.id)
        self.port = QComboBox()
        self.port.setMinimumWidth(280)
        self.slow = QCheckBox("Slower flash speed (try this if installing fails)")
        self.guess = QLabel()
        self.guess.setObjectName("muted")
        self.wiring = QLabel()
        self.wiring.setObjectName("muted")
        self.wiring.setWordWrap(True)
        self.ready = QLabel()
        self.ready.setWordWrap(True)
        self.ready.setObjectName("muted")
        self.install_btn = button("Install firmware", self.install, "primary")
        self.next_btn = button("Open Connection page", lambda: win.goto("connection"))
        self.next_btn.hide()
        self.panel = StatePanel("Choose the board and its port, then select Install firmware.")
        self.logw = QPlainTextEdit()
        self.logw.setObjectName("log")
        self.logw.setReadOnly(True)
        self.logw.setMaximumBlockCount(500)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Set up board", "Install the receiver or sender firmware on a board. "
                                                "This replaces the program that is on the board."))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)
        row = QHBoxLayout()
        row.addWidget(self.port)
        row.addWidget(button("Refresh ports", self.refresh))
        row.addWidget(self.guess, 1)
        form.addRow("This board will be the", self.role)
        form.addRow("Board type", self.board)
        form.addRow("Port", row)
        v.addLayout(form)
        v.addWidget(self.slow)
        v.addWidget(self.wiring)
        v.addWidget(self.ready)
        row = QHBoxLayout()
        row.addWidget(self.install_btn)
        row.addWidget(self.next_btn)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(self.panel)
        v.addWidget(group("Installer output"))
        v.addWidget(self.logw, 1)

        self.role.currentIndexChanged.connect(self.describe)
        self.board.currentIndexChanged.connect(self.describe)
        self.port.currentIndexChanged.connect(self.guess_board)
        i = self.board.findData(win.settings.role_board(RX))
        self.board.setCurrentIndex(max(i, 0))
        self.describe()

    # selection helpers ---------------------------------------------------
    def selected(self):
        return self.role.currentData(), get_board(self.board.currentData())

    def select(self, role=None, board_id=None):
        if role:
            self.role.setCurrentIndex(max(self.role.findData(role), 0))
        if board_id:
            self.board.setCurrentIndex(max(self.board.findData(board_id), 0))

    def describe(self):
        role, b = self.selected()
        rows = wiring_rows(b.id, role)
        text = "Wiring: " + "; ".join(f"{sig} -> {pin}" + (f" ({note})" if note else "")
                                      for sig, pin, note in rows)
        if b.bootloader_note:
            text += "\n" + b.bootloader_note
        self.wiring.setText(text)
        path, err = firmware_status(b, role)
        self.ready.setText(f"Firmware ready: {path.name}" if path else err)
        self.install_btn.setEnabled(path is not None and not self.busy_now())

    def guess_board(self):
        dev = self.port.currentData()
        ids = port_usb_id(dev) if dev else None
        b = find_by_vid_pid(*ids) if ids else None
        self.guess.setText(f"USB id suggests: {b.name} (a guess, please check)" if b else "")

    def refresh(self):
        keep = self.port.currentData()
        self.port.clear()
        items = port_items()
        for label, dev in items:
            self.port.addItem(label, dev)
        i = self.port.findData(keep)
        if i >= 0:
            self.port.setCurrentIndex(i)
        if not items and not self.busy_now():
            self.panel.note("idle", "No serial ports found. Plug in the board and choose Refresh ports.")
        self.describe()
        self.guess_board()

    def busy_now(self):
        return self.flash.running or self.touch is not None

    def busy(self, on):
        self.install_btn.setEnabled(not on)
        for w in (self.role, self.board, self.port, self.slow):
            w.setEnabled(not on)
        if not on:
            self.describe()

    # install ---------------------------------------------------------------
    def install(self):
        role, board = self.selected()
        port = self.port.currentData()
        if not port:
            self.panel.note("error", "No serial port selected. Plug in the board and choose Refresh ports.")
            return
        if self.win.pages["clone"].listening:
            self.panel.note("error", "Cancel the capture in Clone remote before installing firmware.")
            return
        path, err = firmware_status(board, role)
        if err:
            self.panel.note("error", err)
            return
        if board.is_esp:
            if not esptool_available():
                self.panel.note("error", "esptool is not installed. Run:  pip install esptool")
                return
        elif not find_avrdude()[0]:
            self.panel.note("error", "The installer (avrdude) was not found. Put avrdude.exe in the "
                                     "tools/avrdude folder next to main.py.")
            return
        if not confirm(self, "Install firmware", f"Install the {role} firmware on {board.name} at {port}? "
                       "The program currently on the board will be replaced.", "Install"):
            return
        self.win.bridge.disconnect_port(port)
        self.win.info.clear()
        self.win.set_status()
        self.logw.clear()
        self.next_btn.hide()
        self.busy(True)
        self.job = (role, board, port, path)
        if board.avr_touch_reset:
            self.panel.note("waiting", "Resetting the board into its bootloader…", busy=True)
            self.touch = TouchResetWorker(port)
            self.touch.done.connect(self.after_touch)
            self.touch.start()
        else:
            self.run_tool(port)

    def after_touch(self, new_port):
        t, self.touch = self.touch, None
        if t:
            t.wait(1000)
        if not new_port:
            self.busy(False)
            self.panel.note("error", "The bootloader port did not appear. Press RESET twice quickly "
                                     "and try again.")
            return
        self.run_tool(new_port)

    def run_tool(self, port):
        role, board, _orig, path = self.job
        self.job = (role, board, _orig, path)
        baud = board.flash_baud_fallback if self.slow.isChecked() else board.flash_baud
        if board.is_esp:
            program, args = esp_args(board, port, path, baud)
        else:
            program, conf = find_avrdude()
            args = avr_args(board, port, path, conf, baud)
        self.panel.note("waiting", f"Installing the {role} firmware. Do not unplug the board.", busy=True)
        self.flash.start(program, args, role, board.name, self.job[2])

    def on_success(self, role, board_name, port):
        self.busy(False)
        _r, board, orig_port, _p = self.job
        self.win.settings.save_role(role, port=orig_port, board=board.id)
        self.win.pages["connection"].choose(role, board_id=board.id, port=orig_port)
        self.panel.note("success", f"Installed the {role} firmware on {board_name}. "
                                   "Open the Connection page to connect it.")
        self.next_btn.show()

    def on_failure(self, reason):
        self.busy(False)
        self.panel.note("error", reason)

    def shutdown(self):
        self.flash.abort()
        if self.touch:
            self.touch.wait(11000)
