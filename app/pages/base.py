"""Base class for pages: shared access to the main window and remote selection."""

from PyQt5.QtWidgets import QWidget


class Page(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win

    def refresh(self):
        pass

    def fill_combo(self, combo):
        combo.blockSignals(True)
        combo.clear()
        names = self.win.store.names()
        combo.addItems(names)
        if self.win.current not in names:
            self.win.current = names[0] if names else None
        if self.win.current:
            combo.setCurrentText(self.win.current)
        combo.blockSignals(False)

    def pick(self, name):
        self.win.current = name
        self.win.refresh_all()
