#!/usr/bin/env python3
"""RemoteCloner - launcher. The application lives in the app/ package."""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app import theme
from app.settings import AppSettings
from app.window import Main


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    s = AppSettings()
    theme.apply_theme(app, s.theme, s.font_scale)
    w = Main()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
