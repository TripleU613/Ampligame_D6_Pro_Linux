# Ampligame D6 — Linux Driver & CLI

Userspace Linux driver and CLI for the **Fifine Ampligame D6** (15-key Stream
Deck-style hardware, USB VID `0x3142` PID `0x0060`, manufacturer string
`HOTSPOTEKUSB`).

Linux has no official support for this device. This project reverse-engineers
the protocol from `SDLibrary1.dll` (Qt5 + libusb, shipped with Fifine Control
Deck for Windows) and implements:

- **Device wake**, brightness, screen clear, batched commits
- **Per-key 105×105 JPEG image upload**
- **Animated GIF playback** per key (independent frame loops)
- **Button input** via the device's vendor HID interface
- **Sudo-friendly command execution** as the desktop user

See `d6-protocol.md` for the full wire-level spec.

## Quickstart

```bash
# 1. install OS deps
sudo apt install python3-usb python3-pil

# 2. clone & enter
git clone https://github.com/TripleU613/Ampligame_D6-_Linux.git
cd Ampligame_D6-_Linux

# 3. interactive setup + button bind in one shot
sudo D6_USER=$USER python3 d6-cli.py

# the CLI writes ~/.config/d6.json, then offers to launch the daemon
```

## Files

| File | Purpose |
|---|---|
| `d6.py`          | Headless daemon: opens device, renders config, runs commands |
| `d6-cli.py`      | Interactive setup + per-button binding |
| `d6-harvest.py`  | Extracts every icon/GIF/plugin from a Fifine Control Deck install (run once after installing the Windows app under Wine) |
| `d6-browse.py`   | Search the harvested asset catalog (`d6-browse search play`) |
| `d6-protocol.md` | Full reverse-engineered protocol spec |

## Config format

`~/.config/d6.json` — daemon hot-reloads on file changes.

```jsonc
{
  "brightness": 100,
  "buttons": {
    "1":  {"image": "/path/to/gmail.png",
           "command": "xdg-open https://mail.google.com/"},
    "2":  {"gif": "/path/to/spinner.gif", "fps": 24,
           "command": "obs-cmd start-streaming"},
    "3":  {"label": "PLAY", "bg": [40, 90, 40], "fg": [255, 255, 255],
           "command": "playerctl play-pause"}
  }
}
```

### Button options

- `image`  — path to PNG/JPG (any size; resized + rotated 180° internally)
- `gif`    — path to animated GIF, plays in a loop. Optional `fps` overrides frame timing.
- `label` / `text` — text rendered on a colored background
- `bg`, `fg` — `[R,G,B]` colors (only used with `label`)
- `command` — shell command run on press (executes as `$D6_USER`, with desktop env injected)

## Button layout

Config keys use natural top→bottom, left→right ordering:

```
top:     1  2  3  4  5
mid:     6  7  8  9 10
bot:    11 12 13 14 15
```

Hardware quirk: the device numbers its bytes top-to-bottom in its own
internal frame, but the device is normally mounted with that frame
flipped 180° relative to the user (which is why all images get rotated
180° before upload). The daemon does the row-flip automatically — you
write the config in user-natural order; it talks to the hardware in its
own order.

## Running

The daemon needs libusb access; either run with `sudo`, or install the udev
rule (see `udev/40-ampgd6.rules` — optional).

```bash
# foreground
sudo D6_USER=$USER python3 d6.py

# background (systemd, optional)
sudo cp systemd/d6-deck.service /etc/systemd/system/
sudo systemctl enable --now d6-deck
```

## License

MIT — do whatever. No warranty.

This project is unaffiliated with Fifine. The "HID DEMO" firmware variant
shipped on some D6 units appears to be pre-release; production firmware
(PID `0x0007`) is supported by upstream `mirajazz`/`opendeck-ampgd6`.
