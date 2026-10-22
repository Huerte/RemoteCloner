import sys

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout

from app import __version__
from app.pages.base import Page
from app.ui import button, pad, page_header


class SettingsPage(Page):
    THEMES = [("Dark", "dark"), ("Light", "light"), ("Follow system", "system")]
    SCALES = [("Small (11 px)", "small"), ("Normal (13 px)", "normal"), ("Large (15 px)", "large")]

    def __init__(self, win):
        super().__init__(win)
        s = win.settings
        self.theme = QComboBox()
        for label, val in self.THEMES:
            self.theme.addItem(label, val)
        self.scale = QComboBox()
        for label, val in self.SCALES:
            self.scale.addItem(label, val)
        self.theme.setCurrentIndex(max(self.theme.findData(s.theme), 0))
        self.scale.setCurrentIndex(max(self.scale.findData(s.font_scale), 0))
        self.theme.activated.connect(self.apply)
        self.scale.activated.connect(self.apply)

        self.auto = QCheckBox("Reconnect to the last used boards when the app starts")
        self.auto.setChecked(s.autoconnect)
        self.auto.toggled.connect(lambda on: s.set("autoconnect", on))
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(s.learn_timeout)
        self.timeout.valueChanged.connect(lambda v: s.set("learn_timeout", v))

        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Settings", "Appearance and behaviour. Changes apply immediately."))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Theme", self.theme)
        form.addRow("Text size", self.scale)
        form.addRow("Capture timeout", self.timeout)
        form.addRow("", self.auto)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Open remotes folder", self.open_folder))
        row.addWidget(button("Run quick setup again", win.run_wizard))
        row.addStretch()
        v.addLayout(row)
        about = QLabel(f"RemoteCloner {__version__}  ·  Python {sys.version.split()[0]}")
        about.setObjectName("muted")
        v.addWidget(about)
        v.addStretch()

    def apply(self):
        self.win.settings.set("theme", self.theme.currentData())
        self.win.settings.set("font_scale", self.scale.currentData())
        self.win.apply_appearance()

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.win.store.dir)))
