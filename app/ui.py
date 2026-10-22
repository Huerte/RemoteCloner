"""app/ui.py  -  Small shared UI helpers and widgets."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QFrame, QLabel, QMessageBox, QPushButton, QShortcut, QVBoxLayout)

from app import theme


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
        b.clicked.connect(lambda _checked=False: slot())
    return b


def shortcut(widget, seq, slot, context=Qt.WidgetWithChildrenShortcut):
    sc = QShortcut(QKeySequence(seq), widget)
    sc.setContext(context)
    sc.activated.connect(slot)
    return sc


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
        self.set_token("muted")

    def set_token(self, name):
        self.setStyleSheet(f"background: {theme.tok(name)}; border-radius: 5px;")


class StatePanel(QFrame):
    """Coloured status panel with a message line and optional busy bar."""

    def __init__(self, text=""):
        super().__init__()
        from PyQt5.QtWidgets import QProgressBar
        self.setObjectName("statePanel")
        set_state(self, "idle")
        self.label = QLabel(text)
        self.label.setObjectName("stateText")
        self.label.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)

    def note(self, state, text, busy=False):
        set_state(self, state)
        self.label.setText(text)
        self.bar.setVisible(busy)


class Card(QPushButton):
    """Dashboard tile."""

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
