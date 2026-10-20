#!/usr/bin/env python3
import sys, json, time, threading, shutil, tempfile
from pathlib import Path
import serial
from serial.tools import list_ports
from PyQt5.QtCore import Qt, QThread, QObject, pyqtSignal, QSettings, QTimer, QPointF, QProcess
from PyQt5.QtGui import QColor, QKeySequence, QPalette, QPainter, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QListWidget, QStackedWidget, QHBoxLayout, QVBoxLayout,
    QGridLayout, QFormLayout, QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QInputDialog,
    QFileDialog, QDialog, QDialogButtonBox, QProgressBar, QScrollArea, QAbstractItemView,
    QFrame, QShortcut)

DIR = Path(__file__).with_name("remotes")
FIRMWARE_DIR = Path(__file__).with_name("firmware")
AVRDUDE_DIR = Path(__file__).parent / "tools" / "avrdude"
PRESETS = ["POWER", "MUTE", "VOL_UP", "VOL_DOWN", "CH_UP", "CH_DOWN", "UP", "DOWN", "LEFT",
           "RIGHT", "OK", "MENU", "BACK", "HOME", "INPUT"] + [str(i) for i in range(10)]

# Each board runs one sketch: the receiver captures, the sender transmits.
RX, TX = "receiver", "sender"
PORT_KEY = {RX: "port_rx", TX: "port_tx"}
ROLE_TITLE = {RX: "Receiver (capture)", TX: "Sender (transmit)"}
WIRING = {RX: "Wiring: the IR receiver module (VS1838B or TSOP38238) output pin goes to D11.",
          TX: "Wiring: the IR LED goes to D3 through an NPN transistor (for example 2N2222) "
              "and a resistor of about 100 ohms."}

# Boards the app can flash. The firmware files are named <role>_<mcu>.hex in the firmware folder.
BOARDS = {
    "Arduino Uno": dict(mcu="atmega328p", part="m328p", prog="arduino", baud=115200),
    "Arduino Nano (new bootloader)": dict(mcu="atmega328p", part="m328p", prog="arduino", baud=115200),
    "Arduino Nano (old bootloader)": dict(mcu="atmega328p", part="m328p", prog="arduino", baud=57600),
    "Arduino Mega 2560": dict(mcu="atmega2560", part="m2560", prog="wiring", baud=115200),
}


def find_avrdude():
    """Return (executable, config file or None). Prefers the copy bundled in tools/avrdude."""
    exe = AVRDUDE_DIR / ("avrdude.exe" if sys.platform == "win32" else "avrdude")
    if exe.exists():
        conf = AVRDUDE_DIR / "avrdude.conf"
        return str(exe), (str(conf) if conf.exists() else None)
    return shutil.which("avrdude"), None


def port_items():
    """(label, device) pairs for every serial port."""
    items = []
    for p in list_ports.comports():
        desc = p.description if p.description and p.description != "n/a" else ""
        items.append((f"{p.device} - {desc}" if desc else p.device, p.device))
    return items

# ---------------------------------------------------------------- design system
TOKENS = dict(
    bg="#1a1d21", panel="#20242a", field="#16191d", line="#343a42", hover="#2a2f36",
    text="#e4e6e8", muted="#8f979f", accent="#23808f", accent_hi="#2a95a7", focus="#4fb3c6",
    select="#1f4650", ok="#4cae7a", warn="#d9a441", err="#e5534b")
T = TOKENS

QSS = """
* { font-size: 13px; }
QToolTip { background: @panel; color: @text; border: 1px solid @line; padding: 4px 6px; }
QFrame#sidebar { background: @panel; border: 0; border-right: 1px solid @line; }
QStatusBar { background: @panel; border-top: 1px solid @line; }
QStatusBar::item { border: 0; }

QLabel#brand { font-size: 15px; font-weight: 600; padding: 0 20px; }
QLabel#h1 { font-size: 22px; font-weight: 600; }
QLabel#muted { color: @muted; }
QLabel#empty { color: @muted; font-size: 14px; padding: 32px; }
QLabel#group { color: @muted; font-weight: 600; }
QLabel#stateText { font-size: 14px; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QLabel#cardText { color: @muted; }
QLabel#mono, QPlainTextEdit#log {
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: 12px; }
QLabel#mono { color: @muted; }

QLineEdit, QPlainTextEdit, QListWidget, QTableWidget {
    background: @field; border: 1px solid @line; border-radius: 6px; padding: 6px 10px;
    selection-background-color: @accent; selection-color: #ffffff; }
QListWidget, QTableWidget { padding: 4px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: @focus; }

QComboBox, QSpinBox {
    background: @field; border: 1px solid @line; border-radius: 6px; padding: 5px 10px;
    min-height: 20px; }
QComboBox:focus, QSpinBox:focus { border-color: @focus; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: 0; }
QComboBox::down-arrow { image: url(@arrow_down); width: 10px; height: 6px; margin-right: 8px; }
QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 22px; border: 0; background: transparent; }
QSpinBox::up-button { subcontrol-position: top right; }
QSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-arrow { image: url(@arrow_up); width: 8px; height: 5px; }
QSpinBox::down-arrow { image: url(@arrow_down); width: 8px; height: 5px; }
QComboBox QAbstractItemView { background: @field; border: 1px solid @line; outline: 0;
    selection-background-color: @select; padding: 4px; }

QPushButton { background: @panel; border: 1px solid @line; border-radius: 6px;
    padding: 7px 14px; min-height: 18px; }
QPushButton:hover { background: @hover; }
QPushButton:pressed { background: @field; }
QPushButton:focus { border-color: @focus; }
QPushButton:disabled { color: #5d656e; background: @field; border-color: #272c32; }
QPushButton#primary { background: @accent; border-color: @accent; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: @accent_hi; border-color: @accent_hi; }
QPushButton#primary:disabled { background: #1c3a41; border-color: #1c3a41; color: #6f8a91; }
QPushButton#danger { color: @err; border-color: #4a2d30; }
QPushButton#danger:hover { background: #2a1f21; }
QPushButton#card { background: @panel; border: 1px solid @line; border-radius: 8px; text-align: left;
    padding: 0; min-height: 110px; }
QPushButton#card:hover { background: @hover; border-color: @focus; }

QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:hover { background: @hover; }
QListWidget::item:selected { background: @select; color: #ffffff; }
QListWidget#nav { background: transparent; border: 0; outline: 0; padding: 0; }
QListWidget#nav::item { padding: 10px 20px; border-radius: 0; border-left: 3px solid transparent; color: @muted; }
QListWidget#nav::item:hover { background: @hover; color: @text; }
QListWidget#nav::item:selected { background: @select; border-left: 3px solid @focus; color: #ffffff; }

QTableWidget { gridline-color: transparent; alternate-background-color: #1c2025; outline: 0; }
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected { background: @select; color: #ffffff; }
QHeaderView::section { background: @panel; color: @muted; padding: 8px; border: 0;
    border-bottom: 1px solid @line; font-weight: 600; }

QFrame#statePanel { background: @panel; border: 1px solid @line; border-left: 4px solid #4b5563; border-radius: 6px; }
QFrame#statePanel[state="waiting"] { border-left-color: @warn; }
QFrame#statePanel[state="success"] { border-left-color: @ok; }
QFrame#statePanel[state="error"] { border-left-color: @err; }
QProgressBar { background: #2a303a; border: 0; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: @focus; border-radius: 2px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a414d; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #4a5260; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #3a414d; border-radius: 5px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
"""


def arrow_images():
    """Write small arrow PNGs for combo boxes and spin boxes; QSS can only reference files."""
    out = {}
    for name, pts in (("up", [(0, 6), (10, 6), (5, 0)]), ("down", [(0, 0), (10, 0), (5, 6)])):
        pm = QPixmap(10, 6)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(T["muted"]))
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        painter.end()
        path = Path(tempfile.gettempdir()) / f"irsk_arrow_{name}.png"
        pm.save(str(path))
        out["arrow_" + name] = path.as_posix()
    return out


def build_style():
    s = QSS
    values = {**TOKENS, **arrow_images()}
    for key in sorted(values, key=len, reverse=True):
        s = s.replace("@" + key, values[key])
    return s


def apply_theme(app):
    """Fusion plus a dark palette, so dialogs and native widgets match the stylesheet."""
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {QPalette.Window: "bg", QPalette.WindowText: "text", QPalette.Base: "field",
             QPalette.AlternateBase: "panel", QPalette.Text: "text", QPalette.Button: "panel",
             QPalette.ButtonText: "text", QPalette.ToolTipBase: "panel", QPalette.ToolTipText: "text",
             QPalette.Highlight: "accent", QPalette.PlaceholderText: "muted", QPalette.Link: "focus"}
    for role, key in roles.items():
        pal.setColor(role, QColor(T[key]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#5d656e"))
    app.setPalette(pal)
    app.setStyleSheet(build_style())


# ---------------------------------------------------------------- ui helpers
def pad(layout, spacing=14):
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(spacing)


def set_state(widget, state):
    widget.setProperty("state", state)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def group(text):
    label = QLabel(text)
    label.setObjectName("group")
    return label


def page_header(title, subtitle):
    box = QVBoxLayout()
    box.setSpacing(2)
    head = QLabel(title)
    head.setObjectName("h1")
    sub = QLabel(subtitle)
    sub.setObjectName("muted")
    sub.setWordWrap(True)
    box.addWidget(head)
    box.addWidget(sub)
    return box


def button(text, slot=None, role="", tip=""):
    b = QPushButton(text)
    if role:
        b.setObjectName(role)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    return b


def shortcut(widget, seq, slot, context=Qt.WidgetWithChildrenShortcut):
    sc = QShortcut(QKeySequence(seq), widget)
    sc.setContext(context)
    sc.activated.connect(slot)


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def confirm(parent, title, text, action="Delete"):
    """Destructive confirmation: the button names the action and Cancel is the default."""
    box = QMessageBox(QMessageBox.Warning, title, text, QMessageBox.NoButton, parent)
    yes = box.addButton(action, QMessageBox.DestructiveRole)
    box.setDefaultButton(box.addButton("Cancel", QMessageBox.RejectRole))
    box.exec_()
    return box.clickedButton() is yes


class StatusDot(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(10, 10)
        self.set_color(T["muted"])

    def set_color(self, color):
        self.setStyleSheet(f"background: {color}; border-radius: 5px;")


class Card(QPushButton):
    """Dashboard tile with a title and a short description."""

    def __init__(self, title, text):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(110)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(6)
        head = QLabel(title)
        head.setObjectName("cardTitle")
        body = QLabel(text)
        body.setObjectName("cardText")
        body.setWordWrap(True)
        for w in (head, body):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            v.addWidget(w)
        v.addStretch()


# ---------------------------------------------------------------- storage
class Store:
    def __init__(self):
        DIR.mkdir(exist_ok=True)

    def names(self): return sorted(p.stem for p in DIR.glob("*.json"))
    def path(self, n): return DIR / f"{n}.json"

    def load(self, n):
        d = json.loads(self.path(n).read_text())
        if "keys" not in d:                      # migrate plain {KEY: code} files
            d = {"keys": d}
        d.setdefault("notes", ""); d.setdefault("macros", {})
        return d

    def save(self, n, d): self.path(n).write_text(json.dumps(d, indent=2))
    def create(self, n): self.save(n, {"notes": "", "keys": {}, "macros": {}})
    def delete(self, n): self.path(n).unlink(missing_ok=True)
    def rename(self, o, n): self.path(o).rename(self.path(n))
    def duplicate(self, o, n): shutil.copy(self.path(o), self.path(n))


def safe(name): return "".join(c for c in name.strip() if c.isalnum() or c in " _-")
def keyname(t): return t.strip().upper().replace(" ", "_")


def summary(c):
    return (f"Protocol {c.get('name', 'RAW')}, address {c.get('addr', '-')}, command {c.get('cmd', '-')}\n"
            f"{len(c.get('raw', []))} pulses at {c.get('khz', 38)} kHz")


# ---------------------------------------------------------------- serial bridge
class Link:
    """One open serial port. A board running the combined legacy sketch fills both roles."""

    def __init__(self, ser, tag):
        self.ser, self.tag, self.lock = ser, tag, threading.Lock()


class Bridge(QObject):
    log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.links = {RX: None, TX: None}

    def has(self, role):
        link = self.links[role]
        return link is not None and link.ser.is_open

    @property
    def connected(self): return self.has(RX) or self.has(TX)

    def connect_port(self, role, port, baud):
        """Open a port and check that the board runs the sketch for this role."""
        self.disconnect(role)
        link = Link(serial.Serial(port, baud, timeout=0.3), port)
        try:
            time.sleep(2)                        # the board resets when the port opens
            link.ser.reset_input_buffer()
            reply = self.cmd(link, "P", 2)
        except Exception:
            link.ser.close(); raise
        if "PONG RECEIVER" in reply: found = {RX}
        elif "PONG SENDER" in reply: found = {TX}
        elif "PONG" in reply: found = {RX, TX}   # combined legacy sketch
        else:
            link.ser.close()
            raise RuntimeError("No reply from the board. Install the firmware on the Set up board page "
                               "and check that the baud rate is 115200.")
        if role not in found:
            link.ser.close()
            other = TX if TX in found else RX
            raise RuntimeError(f"This board runs the {other} sketch. Select it as the {other} port instead.")
        for r in found:
            self.disconnect(r); self.links[r] = link

    def disconnect(self, role=None):
        for r in ([role] if role else [RX, TX]):
            link, self.links[r] = self.links[r], None
            if link and link not in self.links.values():
                try: link.ser.close()
                except Exception: pass

    def close(self): self.disconnect()

    def _w(self, link, t):
        self.log.emit(f"[{link.tag}] > " + t[:120]); link.ser.write((t + "\n").encode())

    def _r(self, link, timeout):
        end = time.time() + timeout
        while time.time() < end:
            l = link.ser.readline().decode(errors="ignore").strip()
            if l: self.log.emit(f"[{link.tag}] < " + l[:120]); return l
        return ""

    def cmd(self, link, t, timeout=1):
        if not link.lock.acquire(timeout=timeout + 1): return ""
        try: self._w(link, t); return self._r(link, timeout)
        finally: link.lock.release()

    def ping(self):
        seen = []
        for link in self.links.values():
            if link and link not in seen: seen.append(link)
        return [self.cmd(l, "P") for l in seen]

    def learn(self, cancel, timeout=20):
        link = self.links[RX]
        if link is None: raise RuntimeError("The receiver board is not connected.")
        with link.lock:
            link.ser.reset_input_buffer(); self._w(link, "L")
            code, end = {}, time.time() + timeout
            while time.time() < end and not cancel.is_set():
                l = self._r(link, 0.4)
                if l.startswith("DEC"):
                    p = l.split()
                    code.update(proto=int(p[1]), name=" ".join(p[2:-2]), addr=int(p[-2]), cmd=int(p[-1]))
                elif l.startswith("RAW"):
                    _, khz, _, data = l.split(" ", 3)
                    code.update(khz=int(khz), raw=[int(x) for x in data.split(",")]); return code
                elif l.startswith("ERR"): raise RuntimeError(l)
            self._w(link, "C"); self._r(link, 0.5)
            return None

    def send(self, code, mode="raw", repeats=0):
        link = self.links[TX]
        if link is None: raise RuntimeError("The sender board is not connected.")
        if mode == "decoded" and code.get("name") not in (None, "", "UNKNOWN") and "proto" in code:
            return self.cmd(link, f"D {code['proto']} {code['addr']} {code['cmd']} {repeats}")
        raw, r = code["raw"], ""
        for _ in range(repeats + 1):
            r = self.cmd(link, f"S {code.get('khz', 38)} {len(raw)} " + ",".join(map(str, raw)), 2)
            if repeats: time.sleep(0.05)
        return r


class LearnThread(QThread):
    done = pyqtSignal(object); failed = pyqtSignal(str)

    def __init__(self, bridge, timeout):
        super().__init__(); self.b, self.t, self.cancel = bridge, timeout, threading.Event()

    def run(self):
        try: self.done.emit(self.b.learn(self.cancel, self.t))
        except Exception as e: self.failed.emit(str(e))


# ---------------------------------------------------------------- base page
class Page(QWidget):
    def __init__(self, win): super().__init__(); self.win = win
    def refresh(self): pass

    def fill_combo(self, combo):
        combo.blockSignals(True); combo.clear()
        names = self.win.store.names(); combo.addItems(names)
        if self.win.current not in names: self.win.current = names[0] if names else None
        if self.win.current: combo.setCurrentText(self.win.current)
        combo.blockSignals(False)

    def pick(self, name): self.win.current = name; self.win.refresh_all()


# ---------------------------------------------------------------- home
class HomePage(Page):
    def __init__(self, win):
        super().__init__(win)
        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("IRRemoteCloner", "Clone, organise, edit and replay infrared remotes."))
        grid = QGridLayout()
        grid.setSpacing(16)
        cards = [("Clone remote", "Name a key, press it on the original remote and record the signal. "
                                  "Batch mode records a whole list.", 1),
                 ("Library", "Rename, edit, duplicate, import and export remotes and their keys.", 2),
                 ("Control panel", "Send keys and run macros made of key sequences and delays.", 3),
                 ("Connection", "Choose the receiver and sender boards and read the serial log.", 4),
                 ("Set up board", "Install the receiver or sender firmware on an Arduino. "
                                  "No Arduino IDE needed.", 5)]
        for i, (title, text, idx) in enumerate(cards):
            card = Card(title, text)
            card.setToolTip(f"Open {title} (Ctrl+{idx + 1})")
            card.clicked.connect(lambda _, x=idx: win.goto(x))
            grid.addWidget(card, i // 2, i % 2)
        self.stats = QLabel()
        self.stats.setObjectName("muted")
        v.addLayout(grid)
        v.addWidget(self.stats)
        v.addStretch()

    def refresh(self):
        n = self.win.store.names()
        total = sum(len(self.win.store.load(x)["keys"]) for x in n)
        self.stats.setText(f"{plural(len(n), 'remote')} with {plural(total, 'stored key')}." if n else
                           "No remotes yet. Open Clone remote to record your first keys.")


# ---------------------------------------------------------------- clone
class ClonePage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.thread = None
        self.pending = None
        self.queue = []
        self.batch_on = False

        self.remote = QComboBox()
        self.remote.activated[str].connect(self.pick)
        self.key = QLineEdit()
        self.key.setPlaceholderText("Key name, for example POWER")
        self.key.returnPressed.connect(self.start)
        self.go = button("Listen for signal", self.start, "primary")
        self.cancel = button("Cancel", self.stop, tip="Stop listening (Esc)")
        self.cancel.setEnabled(False)
        shortcut(self, "Esc", self.stop)

        self.status = QLabel("Enter a key name, then choose Listen for signal.")
        self.status.setObjectName("stateText")
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.hide()
        self.info = QLabel()
        self.info.setObjectName("mono")
        self.info.setWordWrap(True)
        self.info.hide()
        self.panel = QFrame()
        self.panel.setObjectName("statePanel")
        set_state(self.panel, "idle")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(8)
        for w in (self.status, self.bar, self.info):
            pl.addWidget(w)

        self.auto = QCheckBox("Save captures automatically")
        self.auto.setChecked(True)
        self.save = button("Save", self.save_pending, "primary")
        self.test = button("Test send", self.test_pending)
        self.discard = button("Discard", self.discard_pending)

        self.batch = QPlainTextEdit()
        self.batch.setPlaceholderText("One key name per line")
        self.batch.setMaximumHeight(120)
        pre = button("Insert common keys", lambda: self.batch.setPlainText("\n".join(PRESETS)))
        self.runb = button("Start batch", self.start_batch)

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
        row.addWidget(pre)
        row.addWidget(self.runb)
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

    def pend_ui(self, on): [b.setEnabled(on) for b in (self.save, self.test, self.discard)]

    def note(self, state, text):
        set_state(self.panel, state)
        self.status.setText(text)

    def refresh(self):
        self.fill_combo(self.remote); self.keys.clear()
        d = self.win.data()
        if d: self.keys.addItems(list(d["keys"]))

    def start(self):
        name = keyname(self.key.text())
        if self.thread or not name: return
        if not self.win.current: self.note("error", "Create a remote first with New remote."); return
        if not self.win.ensure_connected(RX): return
        if name in self.win.data()["keys"] and not self.batch_on:
            if not confirm(self, "Overwrite key?", f"{name} already exists in this remote. "
                           "Replace it with the new capture?", "Overwrite"): return
        self.key.setText(name); self.discard_pending()
        self.thread = LearnThread(self.win.bridge, 20)
        self.thread.done.connect(self.on_done); self.thread.failed.connect(self.on_fail); self.thread.start()
        self.go.setEnabled(False); self.cancel.setEnabled(True); self.bar.show()
        self.note("waiting", f"Listening. Point the original remote at the receiver and press {name} "
                             "(20 s timeout).")

    def idle(self):
        self.thread = None; self.go.setEnabled(True); self.cancel.setEnabled(False); self.bar.hide()

    def on_done(self, code):
        cancelled = bool(self.thread and self.thread.cancel.is_set())
        self.idle()
        if code is None:
            self.batch_on = False
            if cancelled: self.note("idle", "Listening cancelled.")
            else: self.note("error", "No signal received. Hold the remote 5-10 cm from the receiver "
                                     "and try again.")
            return
        self.pending = code; self.info.setText(summary(code)); self.info.show(); self.note("success", "Signal captured.")
        if self.auto.isChecked(): self.save_pending()
        else: self.pend_ui(True)

    def on_fail(self, msg): self.idle(); self.batch_on = False; self.note("error", "Error: " + msg)

    def stop(self):
        self.batch_on = False; self.queue = []
        if self.thread: self.thread.cancel.set()

    def save_pending(self):
        if not self.pending: return
        name, d = keyname(self.key.text()), self.win.data()
        d["keys"][name] = self.pending; self.win.put(d)
        self.note("success", f"Saved {name}."); self.pending = None; self.pend_ui(False); self.win.refresh_all()
        if self.batch_on and self.queue:
            self.key.setText(self.queue.pop(0)); QTimer.singleShot(400, self.start)
        else:
            self.batch_on = False; self.key.clear(); self.key.setFocus()

    def test_pending(self):
        if self.pending and self.win.ensure_connected(TX):
            try: self.win.bridge.send(self.pending); self.note("idle", "Test signal sent.")
            except Exception as e: self.note("error", f"Error: {e}")

    def discard_pending(self): self.pending = None; self.info.hide(); self.pend_ui(False)

    def start_batch(self):
        names = [keyname(l) for l in self.batch.toPlainText().splitlines() if l.strip()]
        if not names: return
        self.queue = names[1:]; self.batch_on = True; self.key.setText(names[0]); self.start()


# ---------------------------------------------------------------- edit dialog
class EditDialog(QDialog):
    def __init__(self, name="", code=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit key" if name else "Add key")
        self.resize(540, 480)
        c = code or {}
        f = QFormLayout(self)
        f.setContentsMargins(24, 20, 24, 20)
        f.setVerticalSpacing(10)
        self.name = QLineEdit(name); self.pname = QLineEdit(c.get("name", "UNKNOWN"))
        self.khz = QSpinBox(); self.khz.setRange(20, 60); self.khz.setValue(c.get("khz", 38)); self.khz.setSuffix(" kHz")
        self.proto = QSpinBox(); self.proto.setRange(0, 99); self.proto.setValue(c.get("proto", 0))
        self.addr = QSpinBox(); self.addr.setRange(0, 65535); self.addr.setValue(c.get("addr", 0))
        self.cmd = QSpinBox(); self.cmd.setRange(0, 65535); self.cmd.setValue(c.get("cmd", 0))
        self.note = QLineEdit(c.get("note", ""))
        self.raw = QPlainTextEdit(",".join(map(str, c.get("raw", []))))
        self.raw.setObjectName("log")
        for label, w in [("Key name", self.name), ("Protocol name", self.pname), ("Protocol id", self.proto),
                         ("Address", self.addr), ("Command", self.cmd), ("Carrier frequency", self.khz),
                         ("Note", self.note), ("Raw timings (µs, comma separated)", self.raw)]:
            f.addRow(label, w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = bb.button(QDialogButtonBox.Ok)
        ok.setText("Save"); ok.setObjectName("primary")
        bb.accepted.connect(self.check); bb.rejected.connect(self.reject); f.addRow(bb)

    def check(self):
        try:
            raw = [int(x) for x in self.raw.toPlainText().replace(",", " ").split()]
            if len(raw) < 2 or not keyname(self.name.text()): raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Invalid key", "Enter a key name and at least two numeric raw timings."); return
        self.key = keyname(self.name.text())
        self.code = dict(proto=self.proto.value(), name=self.pname.text() or "UNKNOWN", addr=self.addr.value(),
                         cmd=self.cmd.value(), khz=self.khz.value(), raw=raw, note=self.note.text())
        self.accept()


# ---------------------------------------------------------------- library
class LibraryPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.rlist = QListWidget()
        self.rlist.currentRowChanged.connect(self.on_remote)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Search keys")
        self.search.textChanged.connect(self.fill_table)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Key", "Protocol", "Address", "Command", "Pulses", "Note"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.edit_key)
        shortcut(self.table, "Del", self.del_key, Qt.WidgetShortcut)
        self.empty = QLabel()
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Notes about this remote (brand, model, room)")
        self.notes.editingFinished.connect(self.save_notes)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(group("Remotes"))
        left.addWidget(self.rlist)
        for text, fn, role in [("New remote", win.new_remote, "primary"), ("Rename", self.ren_remote, ""),
                               ("Duplicate", self.dup_remote, ""), ("Import…", self.imp, ""),
                               ("Export…", self.exp, ""), ("Delete", self.del_remote, "danger")]:
            left.addWidget(button(text, fn, role))

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self.notes)
        right.addWidget(self.search)
        right.addWidget(self.table, 1)
        right.addWidget(self.empty, 1)
        row = QHBoxLayout()
        for text, fn, role in [("Add key", self.add_key, "primary"), ("Edit", self.edit_key, ""),
                               ("Rename", self.ren_key, ""), ("Re-learn", self.relearn, ""),
                               ("Test send", self.test_key, ""), ("Duplicate", self.dup_key, ""),
                               ("Delete", self.del_key, "danger")]:
            row.addWidget(button(text, fn, role))
        right.addLayout(row)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Library", "Manage remotes and the keys stored in each one."))
        h = QHBoxLayout()
        h.setSpacing(24)
        h.addLayout(left, 1)
        h.addLayout(right, 4)
        v.addLayout(h, 1)

    def refresh(self):
        self.rlist.blockSignals(True); self.rlist.clear(); names = self.win.store.names(); self.rlist.addItems(names)
        if self.win.current in names: self.rlist.setCurrentRow(names.index(self.win.current))
        self.rlist.blockSignals(False); self.notes.setText((self.win.data() or {}).get("notes", "")); self.fill_table()

    def on_remote(self, row):
        if row >= 0: self.win.current = self.rlist.item(row).text(); self.refresh()

    def fill_table(self):
        d = self.win.data(); self.table.setRowCount(0)
        q = self.search.text().lower()
        for k, c in (d["keys"].items() if d else []):
            if q and q not in k.lower() and q not in c.get("note", "").lower(): continue
            r = self.table.rowCount(); self.table.insertRow(r)
            for i, v in enumerate([k, c.get("name", "RAW"), c.get("addr", ""), c.get("cmd", ""), len(c.get("raw", [])), c.get("note", "")]):
                self.table.setItem(r, i, QTableWidgetItem(str(v)))
        n = self.table.rowCount()
        self.table.setVisible(n > 0)
        self.empty.setVisible(n == 0)
        self.empty.setText("No remote selected. Create one with New remote." if not d else
                           "No keys match your search." if q else
                           "This remote has no keys yet. Use Add key, or record them in Clone remote.")

    def sel(self):
        r = self.table.currentRow()
        return self.table.item(r, 0).text() if r >= 0 else None

    def save_notes(self):
        d = self.win.data()
        if d: d["notes"] = self.notes.text(); self.win.put(d)

    # remotes
    def ren_remote(self):
        old = self.win.current
        if not old: return
        n, ok = QInputDialog.getText(self, "Rename remote", "New name:", text=old); n = safe(n)
        if ok and n and n != old: self.win.store.rename(old, n); self.win.current = n; self.win.refresh_all()

    def dup_remote(self):
        old = self.win.current
        if not old: return
        n, ok = QInputDialog.getText(self, "Duplicate remote", "Name of the copy:", text=old + "_copy"); n = safe(n)
        if ok and n: self.win.store.duplicate(old, n); self.win.current = n; self.win.refresh_all()

    def del_remote(self):
        n = self.win.current
        if n and confirm(self, "Delete remote", f"Delete “{n}” and all its keys? This cannot be undone."):
            self.win.store.delete(n); self.win.current = None; self.win.refresh_all()

    def imp(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import remote", "", "JSON (*.json)")
        if not p: return
        try: json.loads(Path(p).read_text())
        except Exception as e: QMessageBox.warning(self, "Import failed", f"This file is not valid JSON: {e}"); return
        dest = self.win.store.path(safe(Path(p).stem))
        if dest.exists() and not confirm(self, "Replace remote", f"A remote named “{dest.stem}” already exists. "
                                         "Replace it?", "Replace"): return
        shutil.copy(p, dest); self.win.current = dest.stem; self.win.refresh_all()

    def exp(self):
        n = self.win.current
        if not n: return
        p, _ = QFileDialog.getSaveFileName(self, "Export remote", f"{n}.json", "JSON (*.json)")
        if p: shutil.copy(self.win.store.path(n), p)

    # keys
    def add_key(self):
        if not self.win.current: return
        dlg = EditDialog(parent=self)
        if dlg.exec_():
            d = self.win.data(); d["keys"][dlg.key] = dlg.code; self.win.put(d); self.refresh()

    def edit_key(self):
        k = self.sel()
        if not k: return
        d = self.win.data(); dlg = EditDialog(k, d["keys"][k], self)
        if dlg.exec_():
            d["keys"].pop(k); d["keys"][dlg.key] = dlg.code; self.win.put(d); self.refresh()

    def ren_key(self):
        k = self.sel()
        if not k: return
        n, ok = QInputDialog.getText(self, "Rename key", "New name:", text=k); n = keyname(n)
        if ok and n and n != k:
            d = self.win.data(); d["keys"] = {(n if x == k else x): v for x, v in d["keys"].items()}
            self.win.put(d); self.refresh()

    def dup_key(self):
        k = self.sel()
        if k: d = self.win.data(); d["keys"][k + "_COPY"] = dict(d["keys"][k]); self.win.put(d); self.refresh()

    def del_key(self):
        k = self.sel()
        if k and confirm(self, "Delete key", f"Delete {k}? This cannot be undone."):
            d = self.win.data(); d["keys"].pop(k); self.win.put(d); self.refresh()

    def test_key(self):
        k = self.sel()
        if k and self.win.ensure_connected(TX):
            try: self.win.bridge.send(self.win.data()["keys"][k])
            except Exception as e: QMessageBox.warning(self, "Send failed", str(e))

    def relearn(self):
        k = self.sel()
        if k: self.win.goto(1); self.win.pages[1].key.setText(k); self.win.pages[1].start()


# ---------------------------------------------------------------- control + macros
class ControlPage(Page):
    def __init__(self, win):
        super().__init__(win)
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
        sc = QScrollArea()
        sc.setWidget(w)
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.viewport().setAutoFillBackground(False)
        self.mcombo = QComboBox()
        self.mcombo.activated[str].connect(self.load_macro)
        self.macro = QLineEdit()
        self.macro.setPlaceholderText("POWER, 500, VOL_UP   (numbers are delays in ms)")

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Control panel", "Send keys from a stored remote or run a saved macro."))
        row = QHBoxLayout()
        for label, widget in (("Remote", self.remote), ("Mode", self.mode), ("Repeats", self.rep)):
            row.addWidget(QLabel(label))
            row.addWidget(widget)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(sc, 1)
        v.addWidget(self.empty, 1)
        v.addWidget(self.msg)
        v.addWidget(group("Macro"))
        row = QHBoxLayout()
        row.addWidget(self.mcombo)
        row.addWidget(self.macro, 1)
        row.addWidget(button("Run", self.run_macro, "primary"))
        row.addWidget(button("Save macro", self.save_macro))
        row.addWidget(button("Delete macro", self.del_macro, "danger"))
        v.addLayout(row)

    def mode_s(self): return "decoded" if self.mode.currentIndex() == 1 else "raw"

    def refresh(self):
        self.fill_combo(self.remote)
        while self.grid.count(): self.grid.takeAt(0).widget().deleteLater()
        d = self.win.data(); self.mcombo.clear(); keys = list(d["keys"]) if d else []
        self.empty.setVisible(not keys)
        for i, k in enumerate(keys):
            b = QPushButton(k); b.setMinimumHeight(44); b.clicked.connect(lambda _, k=k: self.fire(k))
            self.grid.addWidget(b, i // 4, i % 4)
        if d: self.mcombo.addItems(list(d["macros"]))

    def fire(self, k):
        if not self.win.ensure_connected(TX): return
        try:
            r = self.win.bridge.send(self.win.data()["keys"][k], self.mode_s(), self.rep.value())
            self.msg.setText(f"Sent {k}." if r.startswith("OK") else
                             f"{k}: no confirmation from the sender ({r or 'no reply'}).")
        except Exception as e: self.msg.setText(f"Error: {e}")

    def load_macro(self, name): self.macro.setText(self.win.data()["macros"].get(name, ""))

    def save_macro(self):
        d = self.win.data()
        n, ok = QInputDialog.getText(self, "Save macro", "Macro name:", text=self.mcombo.currentText()); n = n.strip()
        if d and ok and n: d["macros"][n] = self.macro.text(); self.win.put(d); self.refresh(); self.mcombo.setCurrentText(n)

    def del_macro(self):
        d = self.win.data(); n = self.mcombo.currentText()
        if d and n in d["macros"] and confirm(self, "Delete macro", f"Delete macro “{n}”?"):
            d["macros"].pop(n); self.win.put(d); self.refresh()

    def run_macro(self):
        if not self.win.ensure_connected(TX): return
        d, mode, rep, b = self.win.data(), self.mode_s(), self.rep.value(), self.win.bridge
        steps = [s.strip() for s in self.macro.text().split(",") if s.strip()]

        def work():
            try:
                for s in steps:
                    if s.isdigit(): time.sleep(int(s) / 1000)
                    elif keyname(s) in d["keys"]: b.send(d["keys"][keyname(s)], mode, rep); time.sleep(0.15)
                    else: b.log.emit(f"! unknown macro step: {s}")
            except Exception as e: b.log.emit(f"! {e}")
        threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------------- connection
class ConnectionPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.ports, self.dots, self.states, self.btns = {}, {}, {}, {}
        self.baud = QComboBox()
        self.baud.addItems(["115200", "9600", "57600"])
        self.hint = QLabel("No serial ports found. Plug in the board and choose Refresh.")
        self.hint.setObjectName("muted")
        self.logw = QPlainTextEdit()
        self.logw.setObjectName("log")
        self.logw.setReadOnly(True)
        self.logw.setMaximumBlockCount(500)
        win.bridge.log.connect(self.logw.appendPlainText)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Connection", "Connect the receiver board (capture) and the sender board "
                                              "(transmit). Each runs its own sketch."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Baud rate"))
        row.addWidget(self.baud)
        row.addWidget(button("Refresh ports", self.refresh))
        row.addWidget(button("Ping", self.ping, tip="Ask every connected board to identify itself"))
        row.addStretch()
        v.addLayout(row)
        for role in (RX, TX):
            self.ports[role], self.dots[role] = QComboBox(), StatusDot()
            self.states[role] = QLabel()
            self.states[role].setObjectName("muted")
            self.btns[role] = button("Connect", lambda _, r=role: self.toggle(r))
            self.ports[role].setMinimumWidth(260)
            title = QLabel(ROLE_TITLE[role])
            title.setMinimumWidth(130)
            row = QHBoxLayout()
            row.setSpacing(10)
            for w in (self.dots[role], title, self.ports[role], self.btns[role], self.states[role]):
                row.addWidget(w)
            row.addStretch()
            v.addLayout(row)
        v.addWidget(self.hint)
        head = QHBoxLayout()
        head.addWidget(group("Serial log"))
        head.addStretch()
        head.addWidget(button("Clear log", self.logw.clear))
        v.addLayout(head)
        v.addWidget(self.logw, 1)

    def refresh(self):
        devices = list_ports.comports()
        for index, role in enumerate((RX, TX)):
            combo = self.ports[role]
            keep = combo.currentData() or self.win.cfg.value(PORT_KEY[role], "")
            combo.clear()
            for p in devices:
                desc = p.description if p.description and p.description != "n/a" else ""
                combo.addItem(f"{p.device} - {desc}" if desc else p.device, p.device)
            i = combo.findData(keep)
            combo.setCurrentIndex(i if i >= 0 else min(index, combo.count() - 1))
            on = self.win.bridge.has(role)
            self.btns[role].setText("Disconnect" if on else "Connect")
            self.dots[role].set_color(T["ok"] if on else T["muted"])
            self.states[role].setText("Connected" if on else "Not connected")
        self.hint.setVisible(not devices)

    def toggle(self, role):
        bridge = self.win.bridge
        if bridge.has(role):
            bridge.disconnect(role)
            self.win.set_status()
        else:
            port = self.ports[role].currentData()
            if not port:
                QMessageBox.information(self, "No port selected", "Choose a serial port first.")
                return
            self.win.connect_serial(role, port, int(self.baud.currentText()))
        self.refresh()

    def ping(self):
        if not self.win.bridge.connected:
            QMessageBox.information(self, "Not connected", "Connect a board first.")
            return
        self.win.bridge.ping()


# ---------------------------------------------------------------- firmware
class FirmwarePage(Page):
    """Flashes the bundled receiver or sender firmware with avrdude."""

    def __init__(self, win):
        super().__init__(win)
        self.proc = None
        self.output = ""
        self.role = QComboBox()
        for r in (RX, TX):
            self.role.addItem(ROLE_TITLE[r], r)
        self.role.currentIndexChanged.connect(self.show_wiring)
        self.board = QComboBox()
        self.board.addItems(list(BOARDS))
        self.port = QComboBox()
        self.port.setMinimumWidth(280)
        self.wiring = QLabel()
        self.wiring.setObjectName("muted")
        self.wiring.setWordWrap(True)
        self.install_btn = button("Install firmware", self.install, "primary")
        self.next_btn = button("Open Connection page", lambda: win.goto(4))
        self.next_btn.hide()

        self.status = QLabel("Choose the board and its port, then select Install firmware.")
        self.status.setObjectName("stateText")
        self.status.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.hide()
        self.panel = QFrame()
        self.panel.setObjectName("statePanel")
        set_state(self.panel, "idle")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(8)
        pl.addWidget(self.status)
        pl.addWidget(self.bar)
        self.logw = QPlainTextEdit()
        self.logw.setObjectName("log")
        self.logw.setReadOnly(True)
        self.logw.setMaximumBlockCount(500)

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Set up board", "Install the receiver or sender firmware on an Arduino. "
                                                "This replaces the program that is on the board."))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)
        row = QHBoxLayout()
        row.addWidget(self.port)
        row.addWidget(button("Refresh ports", self.refresh))
        row.addStretch()
        form.addRow("This board will be the", self.role)
        form.addRow("Board type", self.board)
        form.addRow("Port", row)
        v.addLayout(form)
        v.addWidget(self.wiring)
        row = QHBoxLayout()
        row.addWidget(self.install_btn)
        row.addWidget(self.next_btn)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(self.panel)
        v.addWidget(group("Installer output"))
        v.addWidget(self.logw, 1)
        self.show_wiring()

    def show_wiring(self):
        self.wiring.setText(WIRING[self.role.currentData()])

    def refresh(self):
        keep = self.port.currentData()
        self.port.clear()
        items = port_items()
        for label, device in items:
            self.port.addItem(label, device)
        i = self.port.findData(keep)
        if i >= 0:
            self.port.setCurrentIndex(i)
        if not items:
            self.note("idle", "No serial ports found. Plug in the board and choose Refresh ports.")

    def note(self, state, text):
        set_state(self.panel, state)
        self.status.setText(text)

    def busy(self, on):
        self.install_btn.setEnabled(not on)
        self.bar.setVisible(on)
        for w in (self.role, self.board, self.port):
            w.setEnabled(not on)

    def install(self):
        role, name, port = self.role.currentData(), self.board.currentText(), self.port.currentData()
        board = BOARDS[name]
        if not port:
            self.note("error", "No serial port selected. Plug in the board and choose Refresh ports.")
            return
        if self.win.pages[1].thread:
            self.note("error", "Cancel the capture in Clone remote before installing firmware.")
            return
        exe, conf = find_avrdude()
        if not exe:
            self.note("error", "The installer (avrdude) was not found. Put avrdude.exe in the "
                               "tools/avrdude folder next to main.py.")
            return
        hexfile = FIRMWARE_DIR / f"{role}_{board['mcu']}.hex"
        if not hexfile.exists():
            self.note("error", f"Firmware file {hexfile.name} is missing from the firmware folder.")
            return
        if not confirm(self, "Install firmware", f"Install the {role} firmware on {name} at {port}? "
                       "The program currently on the board will be replaced.", "Install"):
            return
        for r in (RX, TX):                       # release the port before flashing
            link = self.win.bridge.links[r]
            if link and link.tag == port:
                self.win.bridge.disconnect(r)
        self.win.set_status()
        args = (["-C", conf] if conf else []) + [
            "-p", board["part"], "-c", board["prog"], "-P", port, "-b", str(board["baud"]),
            "-D", "-U", f"flash:w:{hexfile}:i"]
        self.output = ""
        self.logw.clear()
        self.logw.appendPlainText("avrdude " + " ".join(args))
        self.next_btn.hide()
        self.busy(True)
        self.note("waiting", f"Installing the {role} firmware. Do not unplug the board.")
        self.job = (role, name, port)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyRead.connect(self.read)
        self.proc.errorOccurred.connect(self.failed_to_start)
        self.proc.finished.connect(self.finished)
        self.proc.start(exe, args)

    def read(self):
        text = bytes(self.proc.readAll()).decode(errors="ignore").replace("\r", "\n")
        self.output += text
        for line in text.splitlines():
            line = line.rstrip()
            if not line or ("|" in line and "%" in line and "100%" not in line):
                continue                         # skip the intermediate progress-bar lines
            self.logw.appendPlainText(line)

    def failed_to_start(self, error):
        if error == QProcess.FailedToStart:
            self.busy(False)
            self.note("error", "The installer could not be started. Check the tools/avrdude folder.")

    def finished(self, code, _status):
        self.read()
        self.busy(False)
        role, name, port = self.job
        if code == 0:
            self.win.cfg.setValue(PORT_KEY[role], port)
            self.note("success", f"Installed the {role} firmware on {name}. "
                                 "Open the Connection page to connect it.")
            self.next_btn.show()
            return
        low = self.output.lower()
        if any(s in low for s in ("can't open device", "cannot open", "access is denied", "ioctl", "no such file")):
            why = "The port is busy or missing. Close the Serial Monitor and any other program using it, then try again."
        elif any(s in low for s in ("not in sync", "getsync", "no response", "timeout")):
            why = ("The board did not respond. Check the board type (older Nano boards use the old bootloader) "
                   "and the port, then try again.")
        else:
            why = "The installer reported an error. See the installer output below."
        self.note("error", why)

    def abort(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(1500)


# ---------------------------------------------------------------- main window
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IRRemoteCloner")
        self.resize(1120, 700)
        self.setMinimumSize(980, 600)
        self.store, self.bridge = Store(), Bridge()
        self.cfg = QSettings("IRSwissKnife", "IRSwissKnife")
        self.current = self.cfg.value("remote", None) or None
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.addItems(["Home", "Clone remote", "Library", "Control panel", "Connection", "Set up board"])
        self.stack = QStackedWidget()
        self.pages = [HomePage(self), ClonePage(self), LibraryPage(self), ControlPage(self), ConnectionPage(self),
                      FirmwarePage(self)]
        for p in self.pages: self.stack.addWidget(p)
        self.nav.currentRowChanged.connect(self.goto)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 22, 0, 12)
        sv.setSpacing(14)
        brand = QLabel("IRRemoteCloner")
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

        for i in range(self.nav.count()):
            self.nav.item(i).setToolTip(f"Ctrl+{i + 1}")
            shortcut(self, f"Ctrl+{i + 1}", lambda i=i: self.goto(i), Qt.WindowShortcut)
        shortcut(self, "Ctrl+N", self.new_remote, Qt.WindowShortcut)
        self.nav.setCurrentRow(0)
        QTimer.singleShot(300, self.autoconnect)

    def goto(self, i):
        self.nav.blockSignals(True); self.nav.setCurrentRow(i); self.nav.blockSignals(False)
        self.stack.setCurrentIndex(i); self.pages[i].refresh()

    def refresh_all(self):
        if self.current: self.cfg.setValue("remote", self.current)
        self.pages[self.stack.currentIndex()].refresh()

    def data(self):
        try: return self.store.load(self.current) if self.current else None
        except Exception: return None

    def put(self, d): self.store.save(self.current, d)

    def new_remote(self):
        n, ok = QInputDialog.getText(self, "New remote", "Remote name (for example Living room TV):"); n = safe(n)
        if not (ok and n): return
        if self.store.path(n).exists(): QMessageBox.information(self, "Remote exists", "A remote with that name already exists."); return
        self.store.create(n); self.current = n; self.refresh_all()

    def set_status(self):
        rx, tx = self.bridge.has(RX), self.bridge.has(TX)
        text = {(True, True): "Receiver and sender connected",
                (True, False): "Receiver connected, sender not connected",
                (False, True): "Sender connected, receiver not connected",
                (False, False): "No boards connected"}[(rx, tx)]
        self.dot.set_color(T["ok"] if rx and tx else T["warn"] if rx or tx else T["muted"])
        self.conn.setText(text)

    def connect_serial(self, role, port, baud, quiet=False):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try: self.bridge.connect_port(role, port, baud); self.cfg.setValue(PORT_KEY[role], port)
        except Exception as e:
            if not quiet: QMessageBox.warning(self, "Connection failed", str(e))
        finally: QApplication.restoreOverrideCursor(); self.set_status()

    def autoconnect(self):
        available = [p.device for p in list_ports.comports()]
        saved = {RX: self.cfg.value(PORT_KEY[RX], "") or self.cfg.value("port", ""),
                 TX: self.cfg.value(PORT_KEY[TX], "")}
        for role, port in saved.items():
            if port and port in available and not self.bridge.has(role):
                self.connect_serial(role, port, 115200, True)

    def ensure_connected(self, role):
        if self.bridge.has(role): return True
        QMessageBox.information(self, f"{role.capitalize()} not connected",
                                f"Connect the {role} board first. Choose its port on the Connection page.")
        self.goto(4); return False

    def closeEvent(self, e):
        t = self.pages[1].thread
        if t: t.cancel.set(); t.wait(1500)
        self.pages[5].abort()
        self.bridge.close(); e.accept()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv); apply_theme(app)
    w = Main(); w.show(); sys.exit(app.exec_())
