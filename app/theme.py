"""
app/theme.py  -  Design tokens, QSS stylesheet and theme management.

Themes: dark (default), light, system (follows the OS palette).
Font scale: small 11 px, normal 13 px, large 15 px.
Arrow PNGs are written to a temp dir (QSS can only reference files).
Call apply_theme() on startup and whenever the user changes theme or font scale.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QPainter, QPalette, QPixmap, QPolygonF
from PyQt5.QtWidgets import QApplication, QStyleFactory

DARK = dict(
    bg="#1a1d21", panel="#20242a", field="#16191d", line="#343a42", hover="#2a2f36",
    text="#e4e6e8", muted="#8f979f", accent="#23808f", accent_hi="#2a95a7", focus="#4fb3c6",
    select="#1f4650", ok="#4cae7a", warn="#d9a441", err="#e5534b",
    tag_bg="#1f4650", tag_text="#7fcfdb", accent_dis="#1c3a41", accent_dis_text="#6f8a91",
)
LIGHT = dict(
    bg="#f4f6f8", panel="#ffffff", field="#edf0f3", line="#d0d7df", hover="#e8ecf0",
    text="#1a1d21", muted="#6b7280", accent="#1a6b78", accent_hi="#207585", focus="#2790a0",
    select="#cde8ee", ok="#2e7d55", warn="#a86e00", err="#c0392b",
    tag_bg="#cde8ee", tag_text="#185c6a", accent_dis="#a9cdd4", accent_dis_text="#f4f6f8",
)
_FONT_SIZES = {"small": 11, "normal": 13, "large": 15}

# Tokens currently in effect; widgets read colours through tok().
ACTIVE: Dict[str, str] = dict(DARK)


def tok(name: str) -> str:
    return ACTIVE[name]


_QSS = """
* { font-size: @font_sizepx; }
QToolTip { background: @panel; color: @text; border: 1px solid @line; padding: 4px 6px; border-radius: 4px; }

QFrame#sidebar { background: @panel; border: 0; border-right: 1px solid @line; }
QStatusBar { background: @panel; border-top: 1px solid @line; }
QStatusBar::item { border: 0; }
QMenu { background: @panel; color: @text; border: 1px solid @line; padding: 4px; border-radius: 6px; }
QMenu::item { padding: 6px 16px 6px 10px; border-radius: 4px; }
QMenu::item:selected { background: @select; }
QMenu::item:disabled { color: @muted; }
QMenu::separator { height: 1px; background: @line; margin: 4px 0; }

QLabel#brand { font-size: @brand_sizepx; font-weight: 600; padding: 0 20px; }
QLabel#h1 { font-size: @h1_sizepx; font-weight: 600; }
QLabel#h2 { font-size: @h2_sizepx; font-weight: 600; }
QLabel#muted { color: @muted; }
QLabel#empty { color: @muted; font-size: @h2_sizepx; padding: 32px; }
QLabel#group { color: @muted; font-weight: 600; font-size: @small_sizepx; }
QLabel#stateText { font-size: @h2_sizepx; }
QLabel#cardTitle { font-size: @h2_sizepx; font-weight: 600; }
QLabel#cardText { color: @muted; }
QLabel#mono, QPlainTextEdit#log {
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: @small_sizepx; }
QLabel#mono { color: @muted; }
QLabel#tag { background: @tag_bg; color: @tag_text; border-radius: 3px; padding: 1px 5px;
    font-size: @small_sizepx; font-weight: 600; }

QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTableWidget {
    background: @field; border: 1px solid @line; border-radius: 6px; padding: 6px 10px; color: @text;
    selection-background-color: @accent; selection-color: #ffffff; }
QListWidget, QTableWidget { padding: 4px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: @focus; }
QLineEdit:disabled { color: @muted; background: @field; }

QComboBox, QSpinBox {
    background: @field; border: 1px solid @line; border-radius: 6px; padding: 5px 10px;
    color: @text; min-height: 20px; }
QComboBox:focus, QSpinBox:focus { border-color: @focus; }
QComboBox:disabled, QSpinBox:disabled { color: @muted; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: 0; }
QComboBox::down-arrow { image: url(@arrow_down); width: 10px; height: 6px; margin-right: 8px; }
QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 22px; border: 0; background: transparent; }
QSpinBox::up-button { subcontrol-position: top right; }
QSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-arrow { image: url(@arrow_up); width: 8px; height: 5px; }
QSpinBox::down-arrow { image: url(@arrow_down); width: 8px; height: 5px; }
QComboBox QAbstractItemView { background: @field; border: 1px solid @line; outline: 0;
    selection-background-color: @select; selection-color: @text; color: @text; padding: 4px; }

QPushButton { background: @panel; border: 1px solid @line; border-radius: 6px; color: @text;
    padding: 7px 14px; min-height: 18px; }
QPushButton:hover { background: @hover; }
QPushButton:pressed { background: @field; }
QPushButton:focus { border: 2px solid @focus; padding: 6px 13px; }
QPushButton:disabled { color: @muted; background: @field; border-color: @line; }
QPushButton#primary { background: @accent; border-color: @accent; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: @accent_hi; border-color: @accent_hi; }
QPushButton#primary:disabled { background: @accent_dis; border-color: @accent_dis; color: @accent_dis_text; }
QPushButton#danger { color: @err; border-color: @err; }
QPushButton#danger:hover { background: @field; }
QPushButton#danger:disabled { color: @muted; border-color: @line; }
QPushButton#card { background: @panel; border: 1px solid @line; border-radius: 8px; text-align: left;
    padding: 0; min-height: 110px; color: @text; }
QPushButton#card:hover { background: @hover; border-color: @focus; }
QPushButton#card:focus { border: 2px solid @focus; padding: 0; }
QPushButton#key { min-height: 44px; border-radius: 6px; font-weight: 600; }

QCheckBox { color: @text; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid @line; border-radius: 3px; background: @field; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; }
QCheckBox::indicator:focus { border-color: @focus; }

QListWidget::item { padding: 6px 8px; border-radius: 4px; color: @text; }
QListWidget::item:hover { background: @hover; }
QListWidget::item:selected { background: @select; color: @text; }
QListWidget#nav { background: transparent; border: 0; outline: 0; padding: 0; }
QListWidget#nav::item { padding: 10px 20px; border-radius: 0; border-left: 3px solid transparent; color: @muted; }
QListWidget#nav::item:hover { background: @hover; color: @text; }
QListWidget#nav::item:selected { background: @select; border-left: 3px solid @focus; color: @text; }

QTableWidget { gridline-color: transparent; alternate-background-color: @panel; outline: 0; color: @text; background: @field; }
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected { background: @select; color: @text; }
QHeaderView::section { background: @panel; color: @muted; padding: 8px; border: 0;
    border-bottom: 1px solid @line; font-weight: 600; }

QFrame#statePanel { background: @panel; border: 1px solid @line; border-left: 4px solid @muted; border-radius: 6px; }
QFrame#statePanel[state="waiting"] { border-left-color: @warn; }
QFrame#statePanel[state="success"] { border-left-color: @ok; }
QFrame#statePanel[state="error"] { border-left-color: @err; }
QFrame#statePanel[state="idle"] { border-left-color: @muted; }

QProgressBar { background: @field; border: 0; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: @focus; border-radius: 2px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @line; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: @muted; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: @line; border-radius: 5px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

QDialog { background: @bg; }
QDialogButtonBox QPushButton { min-width: 80px; }
"""


def _arrow_images(tokens: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, pts in (("up", [(0, 6), (10, 6), (5, 0)]), ("down", [(0, 0), (10, 0), (5, 6)])):
        pm = QPixmap(10, 6)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tokens["muted"]))
        p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in pts]))
        p.end()
        path = Path(tempfile.gettempdir()) / f"rc_arrow_{name}.png"
        pm.save(str(path))
        out[f"arrow_{name}"] = path.as_posix()
    return out


def _build_qss(tokens: Dict[str, str], base: int) -> str:
    values = {**tokens, "font_size": str(base), "small_size": str(base - 1), "h2_size": str(base + 1),
              "h1_size": str(base + 8), "brand_size": str(base + 2), **_arrow_images(tokens)}
    s = _QSS
    for key in sorted(values, key=len, reverse=True):     # longest first: accent_hi before accent
        s = s.replace("@" + key, values[key])
    return s


def _make_palette(c: Dict[str, str]) -> QPalette:
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.WindowText, "text"), (QPalette.Base, "field"),
                      (QPalette.AlternateBase, "panel"), (QPalette.Text, "text"), (QPalette.Button, "panel"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "panel"),
                      (QPalette.ToolTipText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.PlaceholderText, "muted"), (QPalette.Link, "focus")):
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    return pal


_NATIVE: list = []     # the OS palette, captured once before we override it


def resolve_tokens(theme: str) -> Dict[str, str]:
    if theme == "light":
        return LIGHT
    if theme == "system" and _NATIVE:
        return DARK if _NATIVE[0].color(QPalette.Window).lightness() < 128 else LIGHT
    return DARK


def apply_theme(app: QApplication, theme: str = "dark", font_scale: str = "normal") -> Dict[str, str]:
    """Apply theme + font scale; returns the active token dict."""
    if not _NATIVE:
        _NATIVE.append(QPalette(app.palette()))
    tokens = resolve_tokens(theme)
    app.setStyle(QStyleFactory.create("Fusion"))
    ACTIVE.clear()
    ACTIVE.update(tokens)
    app.setPalette(_make_palette(tokens))
    app.setStyleSheet(_build_qss(tokens, _FONT_SIZES.get(font_scale, 13)))
    return tokens
