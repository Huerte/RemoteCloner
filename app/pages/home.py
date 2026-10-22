from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout

from app.pages.base import Page
from app.ui import Card, pad, page_header, plural

CARDS = [
    ("clone", "Clone remote", "Name a key, press it on the original remote and record the signal. "
                             "Batch mode records a whole list."),
    ("library", "Library", "Rename, edit, duplicate, import and export remotes and their keys."),
    ("control", "Control panel", "Send keys and run macros made of key sequences and delays."),
    ("connection", "Connection", "Choose the receiver and sender boards and read the serial log."),
    ("firmware", "Set up board", "Install the receiver or sender firmware on an Arduino or ESP board. "
                                 "No Arduino IDE needed."),
    ("help", "Help", "Wiring diagrams for every board, quick start and troubleshooting."),
]


class HomePage(Page):
    def __init__(self, win):
        super().__init__(win)
        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("RemoteCloner", "Clone, organise, edit and replay infrared remotes."))
        grid = QGridLayout()
        grid.setSpacing(16)
        for i, (key, title, text) in enumerate(CARDS):
            card = Card(title, text)
            card.setToolTip(f"Open {title} (Ctrl+{win.index_of(key) + 1})")
            card.clicked.connect(lambda _=False, k=key: win.goto(k))
            grid.addWidget(card, i // 2, i % 2)
        self.stats = QLabel()
        self.stats.setObjectName("muted")
        v.addLayout(grid)
        v.addWidget(self.stats)
        v.addStretch()

    def refresh(self):
        names = self.win.store.names()
        try:
            total = sum(len(self.win.store.load(n)["keys"]) for n in names)
        except Exception:
            total = 0
        self.stats.setText(f"{plural(len(names), 'remote')} with {plural(total, 'stored key')}."
                           if names else "No remotes yet. Open Clone remote to record your first keys.")
