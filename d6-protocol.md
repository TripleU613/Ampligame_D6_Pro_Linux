# Fifine Ampligame D6 — Linux Protocol (verified working)

End-to-end USB protocol for the Fifine Ampligame D6 / HOTSPOTEKUSB on Linux.
Reverse-engineered from `SDLibrary1.dll` (Qt5 + libusb-1.0, shipped in
Fifine Control Deck 3.10.194.0805) and verified by direct USB experiment on
firmware `V3.D6.1.009`. Compatible with the Mirabox / Ajazz / Hotspot
Stream Dock family that uses the `CRT…` opcode set; the `mirajazz` Rust
crate documents the same wire format for the production PID.

## Identification

| Field | Value |
|---|---|
| USB VID | `0x3142` |
| USB PID | `0x0060` (this unit's "HID DEMO" firmware) — also seen `0x0007` on production |
| Manufacturer | `HOTSPOTEKUSB` |
| Product | `HOTSPOTEKUSB HID DEMO` (this unit) |
| Firmware ASCII | `V3.D6.1.009` (returned by `VER`) |
| Form factor | 3 rows × 5 cols = 15 keys, each with a 105 × 105 LCD |
| HID usage page / id | `0xFFA0 / 0x01` (vendor-defined) |

## USB topology

```
Configuration 1
├── Interface 0 — vendor HID (the protocol surface)
│   ├── EP 0x82 IN  — interrupt, 512 B  — input reports (button events, ACKs)
│   └── EP 0x03 OUT — interrupt, 1024 B — commands & image data
└── Interface 1 — generic keyboard, IN EP 0x81 @ 8 B (unused)
```

## Linux setup (critical — without this, device is silent)

This unit's firmware does **not** transmit input reports while the kernel
`usbhid` driver owns the vendor interface. Required steps before doing
anything else:

1. Detach kernel driver from interface 0 (and 1, harmless):
   `dev.detach_kernel_driver(0)`
2. Claim interface 0 via libusb:
   `usb.util.claim_interface(dev, 0)`
3. Send HID `SET_IDLE 0,0` control transfer
   (`bmRequestType=0x21, bRequest=0x0A, wValue=0x0000, wIndex=0x0000`).
   Optional but matches what the Windows app does.

The device is **fully reactive** — there is no "wake-up" sequence required
to receive button events. As soon as you start polling EP `0x82`, button
events arrive. Sending `DIS` is required to wake the **screens** but not
input.

> Note: hidapi's `hid_write` strips the first byte of a buffer if it is
> `0x00` (treats it as a no-id HID report ID prefix). When sending raw via
> libusb interrupt OUT, **do not include a leading `0x00`** — write the
> command bytes directly. mirajazz includes the `0x00` because it goes
> through `hid_write`; this doc gives the on-wire bytes.

## Wire format — host → device (EP 0x03 OUT)

Every output is a **1024-byte interrupt OUT transfer**, zero-padded.
Commands begin with the literal ASCII `CRT\x00\x00`, then a 3-letter
opcode, then opcode-specific payload.

```
offset  bytes              meaning
0..2    "CRT"              command magic
3..4    \x00 \x00
5..7    "OPC"              opcode (3 ASCII chars)
8..9    \x00 \x00
10..    payload (varies)
...     \x00 padding to 1024
```

### Opcodes (verified working unless noted)

| Opcode | Payload | Effect | Status |
|---|---|---|---|
| `DIS` | none | Wake / display on (screens powered + backlit) | ✅ |
| `LIG` | 1 byte (0–100) | Set brightness; `0x64` = 100% | ✅ |
| `CLE` | 4 bytes `\x00 \x00 \x00 [key+1]` (or `\xff` for all) | Clear screen for key (`mirajazz`) | ✅ all-clear |
| `STP` | none | Commit pending writes / end batch | ✅ |
| `VER` | none | Get firmware version (response on EP 0x82) | ✅ |
| `BAT` | image header (see below) | Begin image upload | ✅ |
| `MOD` | `0x30 + mode` | Set device mode (per `mirajazz`) | not tested |
| `HAN` | none | Handshake reply (host→device, used after device sends `ANLDER`) | from RE |

### Image upload (`BAT`)

To set the image on a single key:

1. **Header packet** (1024 bytes, on-wire):
   ```
   "CRT" \x00\x00 "BAT" \x00\x00 [len_hi] [len_lo] [key+1]   (then \x00 pad)
   ```
   - `len_hi`, `len_lo` = total JPEG length, big-endian
   - `key+1` = button index, **1-based** (button 1 = `0x01`, … button 15 = `0x0F`)

2. **Image data**: write the JPEG bytes in **1024-byte chunks** as raw
   interrupt OUT transfers (no per-chunk header; pad the final chunk
   with `\x00` to 1024).

3. **Commit** with `CRT\x00\x00STP`.

### Image format

- **Codec:** baseline JPEG, RGB
- **Resolution:** 105 × 105 px
- **Orientation:** rotate the source image **180°** before encoding
  (the device displays it flipped otherwise)
- **Quality:** 90 works fine; size ≈ 1500–6000 B per key

## Wire format — device → host (EP 0x82 IN)

Every input/ack is a **512-byte interrupt IN transfer**.

```
offset  bytes              meaning
0..7    41 43 4B 00 00     "ACK\x00\x00"
        4F 4B 00           "OK\x00"
8       \x00               padding
9       nn                 context byte (button id, ACK code, …)
10      ss                 state byte (01 = press / OK-pos, 00 = release / OK-neg)
11..    \x00               padding
```

### Button events

| Byte 9 | Position |
|---|---|
| `0x01` | row 0, col 0 (top-left)  |
| `0x02` | row 0, col 1             |
| `0x03` | row 0, col 2             |
| `0x04` | row 0, col 3             |
| `0x05` | row 0, col 4 (top-right) |
| `0x06` | row 1, col 0             |
| `0x07` | row 1, col 1             |
| `0x08` | row 1, col 2             |
| `0x09` | row 1, col 3             |
| `0x0A` | row 1, col 4             |
| `0x0B` | row 2, col 0 (bot-left)  |
| `0x0C` | row 2, col 1             |
| `0x0D` | row 2, col 2             |
| `0x0E` | row 2, col 3             |
| `0x0F` | row 2, col 4 (bot-right) |

| Byte 10 | Meaning |
|---|---|
| `0x01` | press   |
| `0x00` | release |

Each physical click produces both a press (`01`) and a release (`00`) packet.

### Command ACKs

After every host→device command the device sends a 512-byte ACK on
EP `0x82`. Byte 9 echoes a small context value, byte 10 is the
result (`01` typically = OK). ACKs may queue if you don't drain them.

## Reference scripts (in this repo / `/tmp`)

| Script | Purpose | Verified |
|---|---|---|
| `/tmp/d6-light.py`   | Wake screens + brightness 100% + clear + commit | ✅ |
| `/tmp/d6-buttons.py` | Wake + read all 15 button press/release events  | ✅ |
| `/tmp/d6-image.py`   | Upload a 105×105 JPEG to a single key            | ✅ (button 1 shows "1") |

## External references

- `SDLibrary1.dll` — Fifine Control Deck protocol library (Qt5 + libusb)
- `mirajazz` Rust crate: <https://github.com/4ndv/mirajazz>
- `Uriziel01/Ajazz-AKP153-reverse-engineering`:
  <https://github.com/Uriziel01/Ajazz-AKP153-reverse-engineering>
- Companion module discussion (Lyagva):
  <https://github.com/bitfocus/companion-module-requests/issues/2006>
- OpenDeck D6 plugin:
  <https://github.com/shugotekitten/opendeck-ampgd6>
