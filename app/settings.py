"""app/settings.py  -  Typed wrapper around QSettings (org "RemoteCloner")."""

from __future__ import annotations

from PyQt5.QtCore import QSettings

from app.bridge import RX

ORG = "RemoteCloner"


class AppSettings:
    def __init__(self):
        self.q = QSettings(ORG, ORG)
        self._migrate_legacy()

    def _migrate_legacy(self):
        """Pick up values saved under the old 'IRSwissKnife' organisation once."""
        if self.q.value("migrated", False, bool):
            return
        old = QSettings("IRSwissKnife", "IRSwissKnife")
        for key in old.allKeys():
            if not self.q.contains(key):
                self.q.setValue(key, old.value(key))
        self.q.setValue("migrated", True)

    # generic
    def get(self, key, default=None, type=None):
        return self.q.value(key, default, type) if type else self.q.value(key, default)

    def set(self, key, value):
        self.q.setValue(key, value)

    # appearance
    @property
    def theme(self): return self.get("theme", "dark")
    @property
    def font_scale(self): return self.get("font_scale", "normal")

    # behaviour
    @property
    def autoconnect(self): return self.get("autoconnect", True, bool)
    @property
    def learn_timeout(self): return int(self.get("learn_timeout", 20))
    @property
    def wizard_done(self): return self.get("wizard_done", False, bool)

    # per-role connection
    def role_port(self, role):
        legacy = self.get("port", "") if role == RX else ""
        return self.get(f"port_{role}", "") or legacy

    def role_board(self, role): return self.get(f"board_{role}", "arduino-uno")
    def role_baud(self, role): return int(self.get(f"baud_{role}", 0)) or None

    def save_role(self, role, *, port=None, board=None, baud=None):
        if port is not None: self.set(f"port_{role}", port)
        if board is not None: self.set(f"board_{role}", board)
        if baud is not None: self.set(f"baud_{role}", baud)
