from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QPlainTextEdit, QVBoxLayout)

from app.bridge import RX, TX
from app.pages.base import Page
from app.store import Store
from app.ui import StatePanel, button, confirm, group, pad, page_header, shortcut
from app.workers import LearnWorker, SendWorker

PRESETS = ["POWER", "MUTE", "VOL_UP", "VOL_DOWN", "CH_UP", "CH_DOWN", "UP", "DOWN", "LEFT",
           "RIGHT", "OK", "MENU", "BACK", "HOME", "INPUT"] + [str(i) for i in range(10)]


class ClonePage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.thread = None
        self.send_thread = None
        self.pending = None
        self.queue = []
        self.batch_on = False
        self._skip_confirm = False

        self.remote = QComboBox()
        self.remote.activated[str].connect(self.pick)
        self.key = QLineEdit()
        self.key.setPlaceholderText("Key name, for example POWER")
        self.key.returnPressed.connect(self.start)
        self.go = button("Listen for signal", self.start, "primary")
        self.cancel = button("Cancel", self.stop, tip="Stop listening (Esc)")
        self.cancel.setEnabled(False)
        shortcut(self, "Esc", self.stop)

        self.panel = StatePanel("Enter a key name, then choose Listen for signal.")
        self.info = QLabel()
        self.info.setObjectName("mono")
        self.info.setWordWrap(True)
        self.info.hide()
        self.panel.layout().insertWidget(1, self.info)

        self.auto = QCheckBox("Save captures automatically")
        self.auto.setChecked(True)
        self.save = button("Save", self.save_pending, "primary")
        self.test = button("Test send", self.test_pending)
        self.discard = button("Discard", self.discard_pending)

        self.batch = QPlainTextEdit()
        self.batch.setPlaceholderText("One key name per line")
        self.batch.setMaximumHeight(120)
        self.keys = QListWidget()
        self.keys.setToolTip("Double-click a key to reuse its name")
        self.keys.itemDoubleClicked.connect(lambda i: self.key.setText(i.text()))

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(group("Remote"))
        row = QHBoxLayout()
        row.addWidget(self.remote, 1)
        row.addWidget(button("New remote", win.new_remote))
        left.addLayout(row)
        left.addWidget(group("Key name"))
        row = QHBoxLayout()
        row.addWidget(self.key, 1)
        row.addWidget(self.go)
        row.addWidget(self.cancel)
        left.addLayout(row)
        left.addWidget(self.panel)
        row = QHBoxLayout()
        row.addWidget(self.auto)
        row.addStretch()
        for b in (self.save, self.test, self.discard):
            row.addWidget(b)
        left.addLayout(row)
        left.addWidget(group("Batch capture"))
        left.addWidget(self.batch)
        row = QHBoxLayout()
        row.addWidget(button("Insert common keys", lambda: self.batch.setPlainText("\n".join(PRESETS))))
        row.addWidget(button("Start batch", self.start_batch))
        left.addLayout(row)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(group("Keys in this remote"))
        right.addWidget(self.keys)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Clone remote", "Name a key, press it on the original remote, "
                                                "and the signal is recorded."))
        h = QHBoxLayout()
        h.setSpacing(24)
        h.addLayout(left, 3)
        h.addLayout(right, 2)
        v.addLayout(h, 1)
        self.pend_ui(False)

    def pend_ui(self, on):
        for b in (self.save, self.test, self.discard):
            b.setEnabled(on)

    @property
    def listening(self):
        return self.thread is not None

    def refresh(self):
        self.fill_combo(self.remote)
        self.keys.clear()
        d = self.win.data()
        if d:
            self.keys.addItems(list(d["keys"]))

    def prefill(self, key):
        """Used by Library > Re-learn."""
        self.key.setText(key)
        self._skip_confirm = True
        self.start()

    def start(self):
        name = Store.key_name(self.key.text())
        if self.thread or not name:
            return
        if not self.win.current:
            self.panel.note("error", "Create a remote first with New remote.")
            return
        if not self.win.ensure_connected(RX):
            return
        skip, self._skip_confirm = self._skip_confirm, False
        if name in self.win.data()["keys"] and not self.batch_on and not skip:
            if not confirm(self, "Overwrite key?", f"{name} already exists in this remote. "
                           "Replace it with the new capture?", "Overwrite"):
                return
        self.key.setText(name)
        self.discard_pending()
        timeout = self.win.settings.learn_timeout
        self.thread = LearnWorker(self.win.bridge, timeout)
        self.thread.done.connect(self.on_done)
        self.thread.failed.connect(self.on_fail)
        self.thread.start()
        self.go.setEnabled(False)
        self.cancel.setEnabled(True)
        self.panel.note("waiting", f"Listening. Point the original remote at the receiver and press "
                                   f"{name} ({timeout} s timeout).", busy=True)

    def idle(self):
        t, self.thread = self.thread, None
        if t:
            t.wait(2000)
        self.go.setEnabled(True)
        self.cancel.setEnabled(False)

    def on_done(self, code):
        cancelled = bool(self.thread and self.thread.cancel.is_set())
        self.idle()
        if code is None:
            self.batch_on = False
            self.queue = []
            if cancelled:
                self.panel.note("idle", "Listening cancelled.")
            else:
                self.panel.note("error", "No signal received. Hold the remote 5-10 cm from the "
                                         "receiver and try again.")
            return
        self.pending = code
        self.info.setText(Store.code_summary(code))
        self.info.show()
        self.panel.note("success", "Signal captured.")
        if self.auto.isChecked():
            self.save_pending()
        else:
            self.pend_ui(True)

    def on_fail(self, msg):
        self.idle()
        self.batch_on = False
        self.queue = []
        self.panel.note("error", "Error: " + msg)

    def stop(self):
        self.batch_on = False
        self.queue = []
        if self.thread:
            self.thread.stop()

    def save_pending(self):
        if not self.pending:
            return
        name, d = Store.key_name(self.key.text()), self.win.data()
        d["keys"][name] = self.pending
        self.win.put(d)
        self.panel.note("success", f"Saved {name}.")
        self.pending = None
        self.pend_ui(False)
        self.win.refresh_all()
        if self.batch_on and self.queue:
            self.key.setText(self.queue.pop(0))
            QTimer.singleShot(400, self.start)
        else:
            self.batch_on = False
            self.key.clear()
            self.key.setFocus()

    def test_pending(self):
        if not (self.pending and self.win.ensure_connected(TX)) or self.send_thread:
            return
        self.test.setEnabled(False)
        self.send_thread = SendWorker(self.win.bridge, self.pending, label="test")
        self.send_thread.sent.connect(lambda _l, r: self.test_done("Test signal sent." if r.startswith("OK")
                                                                   else f"Sender replied: {r or 'nothing'}"))
        self.send_thread.failed.connect(lambda _l, e: self.test_done(f"Error: {e}", True))
        self.send_thread.start()

    def test_done(self, text, error=False):
        t, self.send_thread = self.send_thread, None
        if t:
            t.wait(1000)
        self.test.setEnabled(self.pending is not None)
        self.panel.note("error" if error else "idle", text)

    def discard_pending(self):
        self.pending = None
        self.info.hide()
        self.pend_ui(False)

    def start_batch(self):
        names = [Store.key_name(l) for l in self.batch.toPlainText().splitlines() if l.strip()]
        if not names:
            return
        self.queue = names[1:]
        self.batch_on = True
        self.key.setText(names[0])
        self.start()
