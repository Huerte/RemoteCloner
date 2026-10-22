from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from app.bridge import TX
from app.pages.base import Page
from app.ui import button, confirm, group, pad, page_header
from app.workers import MacroWorker, SendWorker

KEY_MIN_WIDTH = 130


class ControlPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.send_thread = None
        self.macro_thread = None
        self.keys = []
        self.remote = QComboBox()
        self.remote.activated[str].connect(self.pick)
        self.mode = QComboBox()
        self.mode.addItems(["Raw replay (most compatible)", "Decoded (compact, if protocol known)"])
        self.rep = QSpinBox()
        self.rep.setRange(0, 10)
        self.msg = QLabel()
        self.msg.setObjectName("muted")
        self.empty = QLabel("No keys to send yet. Record keys in Clone remote first.")
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignCenter)
        w = QWidget()
        self.grid = QGridLayout(w)
        self.grid.setAlignment(Qt.AlignTop)
        self.grid.setSpacing(10)
        self.scroll = QScrollArea()
        self.scroll.setWidget(w)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.viewport().setAutoFillBackground(False)
        self.mcombo = QComboBox()
        self.mcombo.setMinimumWidth(140)
        self.mcombo.activated[str].connect(self.load_macro)
        self.macro = QLineEdit()
        self.macro.setPlaceholderText("POWER, 500, VOL_UP   (numbers are delays in ms)")
        self.run_btn = button("Run", self.run_macro, "primary")
        self.stop_btn = button("Stop", self.stop_macro)
        self.stop_btn.setEnabled(False)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Control panel", "Send keys from a stored remote or run a saved macro."))
        row = QHBoxLayout()
        for label, widget in (("Remote", self.remote), ("Mode", self.mode), ("Repeats", self.rep)):
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(self.scroll, 1)
        v.addWidget(self.empty, 1)
        v.addWidget(self.msg)
        v.addWidget(group("Macro"))
        row = QHBoxLayout()
        row.addWidget(self.mcombo)
        row.addWidget(self.macro, 1)
        row.addWidget(self.run_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(button("Save macro", self.save_macro))
        row.addWidget(button("Delete macro", self.del_macro, "danger"))
        v.addLayout(row)

    def mode_s(self):
        return "decoded" if self.mode.currentIndex() == 1 else "raw"

    def refresh(self):
        self.fill_combo(self.remote)
        d = self.win.data()
        self.keys = list(d["keys"]) if d else []
        self.mcombo.clear()
        if d:
            self.mcombo.addItems(list(d["macros"]))
        self.empty.setText(self.win.load_error or "No keys to send yet. Record keys in Clone remote first.")
        self.empty.setVisible(not self.keys)
        self.scroll.setVisible(bool(self.keys))
        self.layout_keys()

    def layout_keys(self):
        """(Re)build the key grid with as many columns as fit the current width."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cols = max(2, (self.scroll.viewport().width() - 10) // (KEY_MIN_WIDTH + 10))
        self.cols = cols
        for i, k in enumerate(self.keys):
            b = QPushButton(k)
            b.setObjectName("key")
            b.setToolTip(k)
            b.clicked.connect(lambda _=False, k=k: self.fire(k))
            self.grid.addWidget(b, i // cols, i % cols)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.keys:
            cols = max(2, (self.scroll.viewport().width() - 10) // (KEY_MIN_WIDTH + 10))
            if cols != getattr(self, "cols", None):
                self.layout_keys()

    # single key ---------------------------------------------------------
    def fire(self, k):
        if self.send_thread or self.macro_thread or not self.win.ensure_connected(TX):
            return
        d = self.win.data()
        if not d or k not in d["keys"]:
            return
        self.send_thread = SendWorker(self.win.bridge, d["keys"][k], self.mode_s(), self.rep.value(), k)
        self.send_thread.sent.connect(self.fired)
        self.send_thread.failed.connect(lambda l, e: self.fired(l, None, e))
        self.send_thread.start()

    def fired(self, k, reply, error=None):
        t, self.send_thread = self.send_thread, None
        if t:
            t.wait(1000)
        if error:
            self.msg.setText(f"{k}: {error}")
        else:
            self.msg.setText(f"Sent {k}." if reply.startswith("OK")
                             else f"{k}: no confirmation from the sender ({reply or 'no reply'}).")

    # macros -------------------------------------------------------------
    def load_macro(self, name):
        d = self.win.data()
        if d:
            self.macro.setText(d["macros"].get(name, ""))

    def save_macro(self):
        d = self.win.data()
        n, ok = QInputDialog.getText(self, "Save macro", "Macro name:", text=self.mcombo.currentText())
        n = n.strip()
        if d is not None and ok and n:
            d["macros"][n] = self.macro.text()
            self.win.put(d)
            self.refresh()
            self.mcombo.setCurrentText(n)

    def del_macro(self):
        d, n = self.win.data(), self.mcombo.currentText()
        if d and n in d["macros"] and confirm(self, "Delete macro", f"Delete macro “{n}”?"):
            d["macros"].pop(n)
            self.win.put(d)
            self.refresh()

    def run_macro(self):
        d = self.win.data()
        if not d or self.macro_thread or self.send_thread or not self.win.ensure_connected(TX):
            return
        steps = [s.strip() for s in self.macro.text().split(",") if s.strip()]
        if not steps:
            self.msg.setText("The macro is empty.")
            return
        self.macro_thread = MacroWorker(self.win.bridge, steps, d["keys"], self.mode_s(), self.rep.value())
        t = self.macro_thread
        t.step_done.connect(lambda s: self.msg.setText(f"Ran {s}."))
        t.step_error.connect(lambda s: self.msg.setText(f"Macro problem: {s}"))
        t.completed.connect(lambda: self.macro_over("Macro finished."))
        t.cancelled.connect(lambda: self.macro_over("Macro stopped."))
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        t.start()

    def macro_over(self, text):
        t, self.macro_thread = self.macro_thread, None
        if t:
            t.wait(1000)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.msg.setText(text)

    def stop_macro(self):
        if self.macro_thread:
            self.macro_thread.stop()

    def shutdown(self):
        if self.macro_thread:
            self.macro_thread.stop()
            self.macro_thread.wait(1500)
        if self.send_thread:
            self.send_thread.wait(2500)
