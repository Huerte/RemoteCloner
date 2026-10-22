"""
app/boards.py  -  Data-driven board registry for RemoteCloner.

Every supported board is one Board entry; the UI, the serial bridge and the
flasher read everything they need from it (pins, bauds, flash tool, reset
behaviour, USB ids). Adding a board means adding one entry to _REGISTRY.

Pin choices
-----------
AVR (Uno/Nano/Mega/Leonardo/Micro): D11 receive, D3 send (original design).
ESP32 DevKit (WROOM): GPIO 19 / 18   - no strapping-pin conflicts.
ESP32-S3 / S2       : GPIO 4 / 5     - 19/20 are USB D-/D+.
ESP32-C3            : GPIO 4 / 5     - 11-17 flash, 18-19 USB.
ESP8266             : GPIO 14 (D5) receive / GPIO 4 (D2) send
                      (0/2/15 boot-mode pins, 1/3 UART, 6-11 flash, 16 no PWM/IRQ).

Raw buffer: Uno/Nano/Leonardo 200, Mega/ESP32 750, ESP8266 512.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

ALL_BAUDS: List[int] = [
    300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 74880,
    115200, 230400, 250000, 460800, 500000, 921600, 1000000, 2000000,
]
_AVR_BAUDS = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
_ESP_BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]


class Board:
    """Description of one supported board."""

    def __init__(self, *, id: str, name: str, family: str, chip: str, flash_tool: str,
                 flash_baud: int, flash_baud_fallback: int, serial_baud_default: int,
                 serial_bauds: List[int], rx_pin: int, tx_pin: int, raw_buffer: int,
                 bootloader_note: str, vid_pid: List[Tuple[int, int]], reset_dtr_rts: bool,
                 post_open_settle_ms: int, avr_part: Optional[str] = None,
                 avr_prog: Optional[str] = None, avr_touch_reset: bool = False,
                 esp_chip: Optional[str] = None, pin_names: Optional[Dict[int, str]] = None):
        self.id, self.name, self.family, self.chip = id, name, family, chip
        self.flash_tool = flash_tool
        self.flash_baud, self.flash_baud_fallback = flash_baud, flash_baud_fallback
        self.serial_baud_default, self.serial_bauds = serial_baud_default, serial_bauds
        self.rx_pin, self.tx_pin, self.raw_buffer = rx_pin, tx_pin, raw_buffer
        self.bootloader_note, self.vid_pid = bootloader_note, vid_pid
        self.reset_dtr_rts, self.post_open_settle_ms = reset_dtr_rts, post_open_settle_ms
        self.avr_part, self.avr_prog, self.avr_touch_reset = avr_part, avr_prog, avr_touch_reset
        self.esp_chip = esp_chip
        self.pin_names = pin_names or {}

    @property
    def is_esp(self) -> bool:
        return self.family in ("esp32", "esp8266")

    def firmware_stem(self, role: str) -> str:
        """e.g. 'receiver_atmega328p' or 'sender_esp32'."""
        return f"{role}_{self.chip}"

    def pin_label(self, pin: int) -> str:
        if pin in self.pin_names:
            return self.pin_names[pin]
        return f"D{pin}" if self.family == "avr" else f"GPIO {pin}"

    def baud_label(self, baud: int) -> str:
        return f"{baud}  (recommended)" if baud == self.serial_baud_default else str(baud)

    def __repr__(self) -> str:
        return f"Board(id={self.id!r}, name={self.name!r})"


_TOUCH_NOTE = ("Flashing uses a 1200 bps touch-reset. The app opens the port at 1200 baud to "
               "trigger the bootloader, then waits for the port to reappear.")


def _avr(id, name, chip, part, prog, flash_baud, raw, vid_pid, note="", touch=False):
    return Board(id=id, name=name, family="avr", chip=chip, flash_tool="avrdude",
                 flash_baud=flash_baud, flash_baud_fallback=57600, serial_baud_default=115200,
                 serial_bauds=_AVR_BAUDS, rx_pin=11, tx_pin=3, raw_buffer=raw,
                 bootloader_note=note, vid_pid=vid_pid, reset_dtr_rts=False,
                 post_open_settle_ms=500 if touch else 2000, avr_part=part, avr_prog=prog,
                 avr_touch_reset=touch)


def _esp(id, name, family, chip, rx, tx, raw, vid_pid, note, pin_names=None):
    return Board(id=id, name=name, family=family, chip=chip, flash_tool="esptool",
                 flash_baud=460800, flash_baud_fallback=115200, serial_baud_default=115200,
                 serial_bauds=_ESP_BAUDS, rx_pin=rx, tx_pin=tx, raw_buffer=raw, bootloader_note=note,
                 vid_pid=vid_pid, reset_dtr_rts=True, post_open_settle_ms=100, esp_chip=chip,
                 pin_names=pin_names)


_BOOT = "If flashing fails, hold BOOT (IO0), press and release RESET, then release BOOT and try again."

_REGISTRY: List[Board] = [
    _avr("arduino-uno", "Arduino Uno", "atmega328p", "m328p", "arduino", 115200, 200,
         [(0x2341, 0x0043), (0x2341, 0x0001), (0x1A86, 0x7523)]),
    _avr("arduino-nano-new", "Arduino Nano (new bootloader)", "atmega328p", "m328p", "arduino",
         115200, 200, [(0x1A86, 0x7523), (0x0403, 0x6001)]),
    _avr("arduino-nano-old", "Arduino Nano (old bootloader)", "atmega328p", "m328p", "arduino",
         57600, 200, [(0x1A86, 0x7523), (0x0403, 0x6001)],
         note="This Nano uses a slower (57600 baud) bootloader for flashing only."),
    _avr("arduino-mega2560", "Arduino Mega 2560", "atmega2560", "m2560", "wiring", 115200, 750,
         [(0x2341, 0x0010), (0x2341, 0x0042)]),
    _avr("arduino-leonardo", "Arduino Leonardo", "atmega32u4", "m32u4", "avr109", 57600, 200,
         [(0x2341, 0x0036), (0x2341, 0x8036)], note=_TOUCH_NOTE, touch=True),
    _avr("arduino-micro", "Arduino Micro / Pro Micro", "atmega32u4", "m32u4", "avr109", 57600, 200,
         [(0x2341, 0x0037), (0x1B4F, 0x9205)], note=_TOUCH_NOTE, touch=True),
    _esp("esp32-devkit", "ESP32 DevKit (WROOM)", "esp32", "esp32", 19, 18, 750,
         [(0x10C4, 0xEA60), (0x1A86, 0x7523), (0x0403, 0x6001)], _BOOT),
    _esp("esp32-s3", "ESP32-S3", "esp32", "esp32s3", 4, 5, 750,
         [(0x303A, 0x1001), (0x10C4, 0xEA60)],
         _BOOT + " GPIO 19/20 are USB D-/D+ on the S3 - do not use them for IR."),
    _esp("esp32-c3", "ESP32-C3", "esp32", "esp32c3", 4, 5, 750,
         [(0x303A, 0x1001), (0x10C4, 0xEA60), (0x1A86, 0x55D4)],
         _BOOT + " GPIO 11-17 are flash and 18-19 are USB - do not use them for IR."),
    _esp("esp32-s2", "ESP32-S2", "esp32", "esp32s2", 4, 5, 750,
         [(0x303A, 0x0002), (0x10C4, 0xEA60)],
         _BOOT + " GPIO 19/20 are USB D-/D+ on the S2 - do not use them for IR."),
    _esp("esp8266-nodemcu", "ESP8266 NodeMCU / D1 Mini", "esp8266", "esp8266", 14, 4, 512,
         [(0x1A86, 0x7523), (0x10C4, 0xEA60)],
         "If flashing fails, hold FLASH/PROG, press RESET, release FLASH. GPIO 0/2/15 have boot-mode "
         "requirements and GPIO 16 cannot drive the IR carrier - do not use them.",
         pin_names={14: "GPIO 14 (D5)", 4: "GPIO 4 (D2)"}),
]

_BY_ID: Dict[str, Board] = {b.id: b for b in _REGISTRY}


def all_boards() -> List[Board]:
    return list(_REGISTRY)


def get_board(board_id: str) -> Board:
    return _BY_ID[board_id]


def board_or_default(board_id: Optional[str]) -> Board:
    return _BY_ID.get(board_id or "", _REGISTRY[0])


def board_names() -> List[str]:
    return [b.name for b in _REGISTRY]


def find_by_name(name: str) -> Optional[Board]:
    return next((b for b in _REGISTRY if b.name == name), None)


def find_by_vid_pid(vid: int, pid: int) -> Optional[Board]:
    """First board listing this USB id. Many clones share a CH340/CP210x id, so treat as a hint."""
    return next((b for b in _REGISTRY if (vid, pid) in b.vid_pid), None)


# (board_id, role) -> [(signal, pin label, note)]
_RX_NOTE = "VS1838B / TSOP38238 output"
_TX_NOTE = "NPN transistor base via ~100 ohm"
WIRING_TABLE: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = {}
for _b in _REGISTRY:
    WIRING_TABLE[(_b.id, "receiver")] = [("IR OUT", _b.pin_label(_b.rx_pin), _RX_NOTE)]
    WIRING_TABLE[(_b.id, "sender")] = [("IR LED +", _b.pin_label(_b.tx_pin), _TX_NOTE)]


def wiring_rows(board_id: str, role: str) -> List[Tuple[str, str, str]]:
    return WIRING_TABLE.get((board_id, role), [])
