from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout

from app.boards import all_boards, get_board, wiring_rows
from app.pages.base import Page
from app.ui import pad, page_header

TROUBLE = [
    ("The board does not answer when I connect",
     "Install the firmware on the Set up board page, check the USB cable (some are charge-only), "
     "and use Detect baud on the Connection page. Close the Arduino IDE serial monitor."),
    ("Capture says no signal received",
     "Hold the remote 5-10 cm from the receiver and aim at it. Check the receiver OUT pin goes to "
     "the pin shown for your board, and that VCC and GND are connected."),
    ("Sending does nothing",
     "An IR LED needs a transistor driver. Check the LED polarity, view the LED through a phone "
     "camera (it flickers pink or white when sending) and try more repeats in the Control panel."),
    ("Air-conditioner codes fail with overflow or size errors",
     "AC remotes send long signals. Use a Mega 2560 or an ESP32 (750 raw slots) instead of an Uno or Nano (200)."),
    ("ESP board will not flash",
     "Hold BOOT (or FLASH), press RESET, release BOOT, then click Install. Tick Slower flash speed."),
    ("ESP board resets when I connect",
     "Pick the right board type on the Connection page so the app holds DTR/RTS low while opening the port."),
]


class HelpPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.board = QComboBox()
        for b in all_boards():
            self.board.addItem(b.name, b.id)
        self.board.currentIndexChanged.connect(self.render)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        v = QVBoxLayout(self)
        pad(v)
        v.addLayout(page_header("Help", "Quick start, wiring for every board, and fixes for common problems."))
        row = QHBoxLayout()
        row.addWidget(QLabel("Show wiring for"))
        row.addWidget(self.board)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(self.view, 1)
        self.render()

    def refresh(self):
        self.render()

    def render(self):
        from app import theme
        c = theme.ACTIVE
        b = get_board(self.board.currentData())
        rows = ""
        for role, title in (("receiver", "Receiver"), ("sender", "Sender")):
            for sig, pin, note in wiring_rows(b.id, role):
                rows += (f"<tr><td><b>{title}</b></td><td>{sig}</td><td><b>{pin}</b></td>"
                         f"<td>{note}</td></tr>")
        trouble = "".join(f"<p><b>{q}</b><br>{a}</p>" for q, a in TROUBLE)
        note = f"<p>{b.bootloader_note}</p>" if b.bootloader_note else ""
        self.view.setHtml(f"""
<style>body {{ color:{c['text']}; }} td,th {{ padding:4px 12px 4px 0; }} h3 {{ color:{c['focus']}; }}</style>
<h3>Quick start</h3>
<ol>
<li>You need two boards: a <b>receiver</b> (IR receiver module, captures) and a <b>sender</b>
(IR LED with transistor, transmits). One board per role.</li>
<li>Open <b>Set up board</b>, pick the board type and port, and install the receiver firmware,
then the sender firmware.</li>
<li>Open <b>Connection</b> and connect both boards.</li>
<li>Create a remote, open <b>Clone remote</b>, name a key and press it on the original remote.</li>
<li>Replay keys from the <b>Control panel</b>.</li>
</ol>
<h3>Wiring: {b.name}</h3>
<table><tr><th align=left>Board role</th><th align=left>Signal</th><th align=left>Pin</th><th align=left>Note</th></tr>{rows}</table>
<p>Receiver module: VCC to 5 V (3.3 V on ESP), GND to GND. Sender: LED anode through the transistor,
about 100 ohm at the base.</p>{note}
<p>Raw buffer: {b.raw_buffer} pulses. Default serial speed: {b.serial_baud_default} baud.</p>
<h3>Keyboard shortcuts</h3>
<p>Ctrl+1 to Ctrl+8 switch pages, Ctrl+N new remote, Esc cancels a capture, Ctrl+Z undoes a Library change, Del deletes the selected key.</p>
<h3>Troubleshooting</h3>{trouble}""")
