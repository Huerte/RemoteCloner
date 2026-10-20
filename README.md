<div align="center">

# IRRemoteCloner

[![Version](https://img.shields.io/badge/version-1.0-blue.svg)](#)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blueviolet.svg)](#)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB.svg)](https://www.python.org/downloads/)
[![UI](https://img.shields.io/badge/UI-PyQt5-41cd52.svg)](https://pypi.org/project/PyQt5/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A desktop infrared remote cloner. Clone, organise, edit and replay IR remotes from your PC with an Arduino.**

[Report a Bug](https://github.com/Huerte/RemoteCloner/issues) · [Request a Feature](https://github.com/Huerte/RemoteCloner/issues) · [Android version](https://github.com/Huerte/RemoteCloner-Android)

</div>

---

<p align="center">
  IRRemoteCloner turns an Arduino and your computer into a universal IR remote. Point any remote at the receiver, press a button, and the app records the signal. Replay it later to control the same TV, air conditioner or fan. No account, no internet connection, and no Arduino IDE needed, not even to install the board firmware.
</p>

---

## Table of Contents

- [Installation Guide](#installation-guide)
- [What You Need](#what-you-need)
- [What It Does](#what-it-does)
- [How It Works](#how-it-works)
- [Supported Boards](#supported-boards)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Creator](#contributor)
- [License](#license)

---

## Installation Guide

IRRemoteCloner is a Python app. It runs straight from source, so there is nothing to compile.

**Prerequisites:**

| What you need | Where to get it |
|---------------|-----------------|
| Python 3.8 or newer | [python.org/downloads](https://www.python.org/downloads/) |
| Git | [git-scm.com](https://git-scm.com/downloads) |

**Steps:**

1. Clone the repository:
   ```
   git clone https://github.com/Huerte/RemoteCloner.git
   cd RemoteCloner
   ```

2. (Optional but recommended) create a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # Linux / macOS
   ```

3. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```
   This installs `PyQt5` (the interface) and `pyserial` (the USB serial link to the Arduino).

4. Run the app:
   ```
   python main.py
   ```

> **Note:** A copy of `avrdude.exe` is bundled for Windows, so **Set up board** works out of the box there. On Linux and macOS, install `avrdude` from your package manager and make sure it is on your `PATH`. The app uses it automatically when no bundled copy is found.

**Project structure:**

```
RemoteCloner/
├── main.py                  # The whole app: UI, storage, serial bridge, firmware installer
├── requirements.txt         # PyQt5 and pyserial
├── ir_receiver/
│   └── ir_receiver.ino      # Receiver sketch (captures signals, IR receiver on D11)
├── ir_sender/
│   └── ir_sender.ino        # Sender sketch (replays signals, IR LED on D3)
├── firmware/                # Prebuilt .hex files and build notes
│   ├── receiver_atmega328p.hex
│   ├── sender_atmega328p.hex
│   ├── receiver_atmega2560.hex
│   ├── sender_atmega2560.hex
│   └── BUILD.txt
├── tools/
│   └── avrdude/             # Bundled avrdude 8.0 for Windows (exe, config, notes)
└── remotes/                 # Your cloned remotes, one JSON file each (created on first run)
```

---

## What You Need

| Item | Notes |
|------|-------|
| A computer with a free USB port | Windows, Linux or macOS with Python 3.8+ |
| Arduino Uno, Nano or Mega 2560 | See [Supported Boards](#supported-boards) |
| IR receiver module (VS1838B or TSOP38238) | Captures signals. Output pin to **D11** |
| IR LED, NPN transistor (for example 2N2222) and a resistor of about 100 ohm | Replays signals. Wired to **D3** |
| USB cable that carries data | Some cables are power only and will not work |

Each board runs one sketch. The **Receiver** board captures and the **Sender** board transmits, so a full setup uses **two Arduinos**, each on its own USB port. If you only want to clone and store remotes, one Receiver board is enough. If you only want to replay stored remotes, one Sender board is enough.

An older combined sketch that does both jobs on one board is still recognised when connecting.

---

## What It Does

The app has six pages in the sidebar. Each one opens with `Ctrl+1` to `Ctrl+6`, and `Ctrl+N` creates a new remote.

| Page | What it does |
|------|--------------|
| Home | A dashboard with a card for each page and a count of your remotes and stored keys. |
| Clone remote | Type a key name, start listening, then press that button on the original remote. Supports auto-save, test send, and **batch mode** that records a whole list of keys in one go. Preset keys include POWER, MUTE, VOL_UP, VOL_DOWN, CH_UP, CH_DOWN, the arrow keys, OK, MENU, BACK, HOME, INPUT and the digits 0 to 9. Press `Esc` to cancel a capture. |
| Library | Create, rename, duplicate, delete, import and export remotes as JSON files. Add notes to a remote, and add, edit, rename, duplicate, delete, re-learn or test-send any key. The key editor exposes protocol, address, command, carrier frequency and raw timings. |
| Control panel | Fire keys as buttons. Choose **Raw replay** (exact pulse timings, most compatible) or **Decoded** (compact protocol command), set 0 to 10 repeats, and run macros: sequences of keys and delays such as `POWER, 500, VOL_UP`, where numbers are delays in milliseconds. Macros can be saved per remote. |
| Connection | Choose and connect the receiver and sender boards, ping them, and read the live serial log. Saved ports reconnect automatically on startup. A status light in the corner shows what is connected. |
| Set up board | Install the receiver or sender firmware on an Arduino with one click. Shows the wiring for the chosen role and a live installer log. |

---

## How It Works

IRRemoteCloner talks to the Arduino over USB serial at 115200 baud using `pyserial`.

- The **Receiver** firmware listens for one key press and reports both the decoded values (protocol, address, command) and the raw pulse timings.
- The **Sender** firmware replays a stored key, either from the raw timings or from the decoded values.
- A board is verified when you connect it: the app sends a ping and checks which firmware answers. If you pick the wrong role for a board, the app tells you which one it actually is.
- **Set up board** installs the firmware straight from the app. It runs the bundled `avrdude` against the matching `.hex` file in `firmware/`, with the right chip and bootloader settings for the board you chose.

**Serial protocol** (newline-terminated commands):

| Firmware | Command | Reply |
|----------|---------|-------|
| Both | `P` | `PONG RECEIVER` or `PONG SENDER` |
| Both | `V` | `VER receiver 1.0` or `VER sender 1.0` |
| Receiver | `L` (learn one key) | `OK learning`, then `DEC <protocol> <name> <address> <command>` and `RAW 38 <count> <us,us,...>` |
| Receiver | `C` (cancel) | `OK cancelled` |
| Sender | `S <khz> <count> <v1,v2,...>` (raw) | `OK sent` or `ERR size` |
| Sender | `D <protocol> <address> <command> <repeats>` (decoded) | `OK sent` |

**Remote storage.** Each remote is one JSON file in the `remotes/` folder next to `main.py`:

```json
{
  "notes": "Living room TV",
  "keys": {
    "POWER": { "proto": 7, "name": "SAMSUNG", "addr": 7, "cmd": 2, "khz": 38, "raw": [4500, 4500, 560, ...] }
  },
  "macros": {
    "Movie night": "POWER, 500, VOL_UP"
  }
}
```

- No internet access is needed or used.
- No account or sign-in is needed.
- No data leaves your computer. Everything stays in the `remotes/` folder, which is ignored by Git so your personal remotes are not committed by accident.
- The same JSON format is used by the [Android version](https://github.com/Huerte/RemoteCloner-Android), so remotes can be moved between the two.

---

## Supported Boards

| Board | Use the app | Install firmware from the app |
|-------|-------------|-------------------------------|
| Arduino Uno (ATmega328P, including CH340 clones) | Yes | Yes |
| Arduino Nano (ATmega328P, new bootloader) | Yes | Yes |
| Arduino Nano (ATmega328P, old bootloader) | Yes | Yes, at the slower 57600 baud |
| Arduino Mega 2560 | Yes | Yes |

The firmware is built with avr-gcc 7.3.0, Arduino AVR core 1.8.6 and IRremote 4.7.1 at 16 MHz.

Uno and Nano builds use a 200-entry raw buffer, which covers most TV and fan remotes. Long signals such as air conditioner remotes may not fit. The Mega 2560 builds use a 750-entry buffer and are the better choice for those.

Prefer to build the firmware yourself? Open `ir_receiver/ir_receiver.ino` or `ir_sender/ir_sender.ino` in the Arduino IDE with the **IRremote 4.x** library installed. Set `RAW_BUFFER_LENGTH` to 750 for Mega or ESP32 boards.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| No ports appear in the list | Check that the cable carries data and not just power, install the USB driver for your board (CH340 clones need one on some systems), then select **Refresh ports**. |
| "No reply from the board" when connecting | The board has no IRRemoteCloner firmware yet. Install it on the **Set up board** page and make sure the baud rate is 115200. |
| "This board runs the sender sketch" (or receiver) | You selected the board for the wrong role. Select it as the other port on the **Connection** page. |
| "The installer (avrdude) was not found" | On Linux or macOS, install `avrdude` and make sure it is on your `PATH`. On Windows, check that `tools/avrdude/avrdude.exe` is present. |
| "Firmware file ... is missing" | Restore the `.hex` files in the `firmware/` folder, for example with `git checkout -- firmware`. |
| The installer fails or times out | Try another data cable or USB port, pick the correct board type (Nano boards with an old bootloader need the old bootloader option), and close any other program using the serial port, such as the Arduino IDE serial monitor. |
| Nothing is captured | Point the original remote at the receiver from close range. Capture times out after 20 seconds. Check that the receiver output is on D11. |
| A replayed key does nothing | Check the IR LED polarity and that the transistor is wired to D3. Try **Raw replay** mode, or add a repeat. |
| An air conditioner key is cut off or fails to capture | The signal is too long for the 200-entry buffer on Uno and Nano. Use an Arduino Mega 2560 with the 750-entry firmware. |

---

## Contributing

Contributions are welcome. Here is how to go from zero to a submitted pull request.

### Getting Started

**Prerequisites:** Python 3.8+ and Git.

**Fork and clone:**

```
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/RemoteCloner.git
cd RemoteCloner

# 2. Keep your fork in sync with the original
git remote add upstream https://github.com/Huerte/RemoteCloner.git

# 3. Install dependencies and run the app
pip install -r requirements.txt
python main.py
```

### Making Changes

**Branch naming:**

```
feat/short-description    # New features
fix/short-description     # Bug fixes
docs/short-description    # Documentation only
chore/short-description   # Maintenance or refactoring
```

**Commit messages:** Use plain English. Describe what changed and why:

```
# Good
git commit -m "fix: keep unknown JSON fields when saving a remote"
git commit -m "feat: add a repeat count to macros"
git commit -m "docs: clarify the avrdude requirement on Linux"

# Avoid
git commit -m "fix stuff"
git commit -m "update"
```

**Code style:**

- Follow the existing patterns: PyQt5 with one `Page` class per sidebar page, and shared styling through the design tokens at the top of `main.py`.
- Keep serial and file code (`Bridge`, `Store`) separate from widget code so it stays easy to test.
- If you change the serial protocol, update **both** the sketches in `ir_receiver/` and `ir_sender/` and the protocol table in this README. Rebuild the `.hex` files in `firmware/` and update `firmware/BUILD.txt`.
- Keep functions short. If something is growing, split it.
- Never swallow exceptions silently with an empty `except` unless the operation is purely cosmetic.

### Submitting a Pull Request

1. Push your branch to your fork:
   ```
   git push origin feat/your-feature
   ```

2. Open a Pull Request against `Huerte/RemoteCloner:main` on GitHub.

3. In the PR description, briefly explain: what you changed, why, and how to test it.

4. If your change affects the app's screens or behavior, update this README accordingly.

---

## Contributor

<div align="center">
  <table>
    <tr>
      <td align="center"><a href="https://github.com/Huerte"><img src="https://github.com/Huerte.png" width="80px;" alt=""/></a><br /><a href="https://github.com/Huerte"><b>Huerte</b></a><br />Creator</td>
    </tr>
  </table>
</div>

---

## License

IRRemoteCloner is released under the [MIT License](LICENSE).

The MIT License covers this project's own code. The bundled `avrdude` (version 8.0 for Windows, unmodified) is a separate program and is free software licensed under the GNU GPL v2 or later. Its source code is at [github.com/avrdudes/avrdude](https://github.com/avrdudes/avrdude).

---

*Built to make IR remote cloning accessible to everyone.*
