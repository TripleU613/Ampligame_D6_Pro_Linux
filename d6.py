#!/usr/bin/env python3
"""
d6 — minimal Fifine D6 daemon. Images / GIFs / colored labels / commands.
Nothing else.

Config (~/.config/d6.json):
{
  "brightness": 100,
  "buttons": {
    "1":  {"image":  "/path/to/icon.png", "command": "echo 1"},
    "2":  {"gif":    "/path/to/anim.gif", "fps": 15, "command": "echo 2"},
    "3":  {"label": "PLAY", "bg": [40,90,40], "fg": [255,255,255], "command": "playerctl play-pause"}
  }
}
"""
import os, sys, json, time, signal, threading, subprocess, io, logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import usb.core, usb.util
from PIL import Image, ImageDraw, ImageFont, ImageSequence

VID, PID    = 0x3142, 0x0060
OUT, IN     = 0x03, 0x82
PACKET      = 1024
LCD         = (105, 105)
N           = 15
CFG         = Path(os.environ.get("D6_CFG", Path.home() / ".config/d6.json"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("d6")

# ─── helpers ───
def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(p): return ImageFont.truetype(p, sz)
    return ImageFont.load_default()

def label_jpeg(text, bg=(30,30,30), fg=(255,255,255)):
    img = Image.new("RGB", LCD, bg)
    d = ImageDraw.Draw(img)
    sz = max(18, min(72, int(120/max(1,len(str(text))))))
    f = font(sz)
    bb = d.textbbox((0,0), str(text), font=f)
    w, h = bb[2]-bb[0], bb[3]-bb[1]
    d.text(((LCD[0]-w)/2-bb[0], (LCD[1]-h)/2-bb[1]), str(text), fill=fg, font=f)
    return jpeg(img)

def jpeg(img):
    out = img.convert("RGB").resize(LCD, Image.LANCZOS).rotate(180)
    b = io.BytesIO(); out.save(b, "JPEG", quality=88); return b.getvalue()

# ─── device ───
class D6:
    def __init__(self):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None: raise SystemExit(f"D6 not found ({VID:04x}:{PID:04x})")
        # Only detach kernel from iface 0 (vendor HID).
        # Iface 1 is a keyboard — re-attach if needed so button presses arrive as
        # scancodes via /dev/input, since the vendor IN endpoint is unreliable.
        try:
            if self.dev.is_kernel_driver_active(0): self.dev.detach_kernel_driver(0)
        except Exception: pass
        try:
            if not self.dev.is_kernel_driver_active(1): self.dev.attach_kernel_driver(1)
        except Exception as e:
            log.warning(f"could not attach kernel to iface 1: {e}")
        usb.util.claim_interface(self.dev, 0)
        try: self.dev.ctrl_transfer(0x21, 0x0A, 0x0000, 0, None, 1000)
        except Exception: pass
        self.lock = threading.Lock()

    def close(self):
        try: usb.util.release_interface(self.dev, 0)
        except Exception: pass
        try: usb.util.dispose_resources(self.dev)
        except Exception: pass

    def w(self, b):
        with self.lock:
            self.dev.write(OUT, b + b"\x00"*(PACKET-len(b)), timeout=2000)

    def wake(self):       self.w(b"CRT\x00\x00DIS")
    def bright(self, p):  self.w(b"CRT\x00\x00LIG" + bytes([max(0,min(100,p))]))
    def clear_all(self):  self.w(b"CRT\x00\x00CLE\x00\x00\x00\xff")
    def commit(self):     self.w(b"CRT\x00\x00STP")

    def img(self, key, jpg):
        h = b"CRT\x00\x00BAT\x00\x00" + bytes([(len(jpg)>>8)&0xff, len(jpg)&0xff, key+1])
        with self.lock:
            self.dev.write(OUT, h + b"\x00"*(PACKET-len(h)), timeout=2000)
            for i in range(0, len(jpg), PACKET):
                ch = jpg[i:i+PACKET]
                self.dev.write(OUT, ch + b"\x00"*(PACKET-len(ch)), timeout=2000)

    def read_event(self) -> Optional[Tuple[int,int]]:
        try:    data = self.dev.read(IN, 512, timeout=200)
        except usb.core.USBTimeoutError: return None
        b = bytes(data)
        if len(b) < 11 or b[:8] != b"ACK\x00\x00OK\x00": return None
        idx, st = b[9], b[10]
        if 1 <= idx <= N and st in (0,1): return (idx-1, st)
        return None

# ─── gif loop per key ───
class Gif(threading.Thread):
    def __init__(self, dev, key, frames, delays):
        super().__init__(daemon=True)
        self.dev, self.key, self.frames, self.delays = dev, key, frames, delays
        self._stop = threading.Event()
    def stop(self): self._stop.set()
    def run(self):
        i = 0
        while not self._stop.is_set():
            try:
                self.dev.img(self.key, self.frames[i])
                self.dev.commit()
            except Exception:
                return
            self._stop.wait(max(40, self.delays[i])/1000.0)
            i = (i+1) % len(self.frames)

# ─── main ───
def load_cfg():
    if not CFG.exists():
        CFG.parent.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps({"brightness":100, "buttons":{}}, indent=2))
    return json.loads(CFG.read_text())

def build(spec):
    if "image" in spec:
        try: return ("img", jpeg(Image.open(spec["image"])))
        except Exception as e: log.warning(f"image: {e}"); return None
    if "gif" in spec:
        try:
            im = Image.open(spec["gif"])
            frames, delays = [], []
            fps = spec.get("fps")
            for f in ImageSequence.Iterator(im):
                frames.append(jpeg(f.copy()))
                delays.append(int(1000/fps) if fps else f.info.get("duration", 80))
            return ("gif", frames, delays)
        except Exception as e: log.warning(f"gif: {e}"); return None
    if "label" in spec or "text" in spec:
        return ("img", label_jpeg(spec.get("label") or spec.get("text"),
                                  tuple(spec.get("bg", [30,30,30])),
                                  tuple(spec.get("fg", [255,255,255]))))
    return None

def render(dev, cfg, gifs):
    for g in gifs.values(): g.stop()
    gifs.clear()
    # NOTE: skipping clear_all — the CLE\xff command appears to silence the
    # firmware's input-scan engine on this firmware variant. Keys without
    # config will simply keep their previous image.
    for i in range(1, N+1):
        spec = cfg.get("buttons", {}).get(str(i))
        if not spec: continue
        b = build(spec)
        if not b: continue
        if b[0] == "img":
            try: dev.img(i-1, b[1])
            except Exception as e: log.warning(f"key {i}: {e}")
        elif b[0] == "gif":
            g = Gif(dev, i-1, b[1], b[2]); gifs[i] = g; g.start()
    dev.commit()

def run_cmd(cmd, label):
    if not cmd: return
    # Daemon runs as root (libusb), but GUI commands need the desktop user's env.
    # Drop privileges to SUDO_USER (or D6_USER override) and inject DISPLAY+XDG_RUNTIME_DIR+DBUS.
    target = os.environ.get("D6_USER") or os.environ.get("SUDO_USER")
    if target and target != "root":
        try:
            import pwd
            pw = pwd.getpwnam(target)
            uid = pw.pw_uid
            env = (
                f"DISPLAY={os.environ.get('DISPLAY', ':1')} "
                f"XAUTHORITY={pw.pw_dir}/.Xauthority "
                f"XDG_RUNTIME_DIR=/run/user/{uid} "
                f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus "
                f"HOME={pw.pw_dir} "
            )
            cmd = f"sudo -u {target} -E env {env} bash -c {shlex_quote(cmd)}"
        except Exception:
            pass
    try:
        subprocess.Popen(cmd, shell=True, executable="/bin/bash",
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        log.info(f"[{label}] $ {cmd}")
    except Exception as e:
        log.error(f"[{label}] {e}")

def shlex_quote(s):
    import shlex; return shlex.quote(s)

def main():
    dev  = D6()
    gifs: Dict[int, Gif] = {}
    cfg  = load_cfg()
    mtime = CFG.stat().st_mtime

    dev.wake()
    dev.bright(cfg.get("brightness", 100))
    dev.commit()
    time.sleep(0.05)
    render(dev, cfg, gifs)
    log.info("ready")

    stop = threading.Event()
    def sigh(*_): stop.set()
    signal.signal(signal.SIGINT,  sigh)
    signal.signal(signal.SIGTERM, sigh)

    last_check = 0
    try:
        while not stop.is_set():
            ev = dev.read_event()
            if ev is not None:
                key, state = ev
                if state == 1:
                    spec = cfg.get("buttons", {}).get(str(key+1), {})
                    run_cmd(spec.get("command"), f"key{key+1}")
            now = time.time()
            if now - last_check > 1.0:
                last_check = now
                m = CFG.stat().st_mtime
                if m != mtime:
                    mtime = m
                    cfg = load_cfg()
                    dev.bright(cfg.get("brightness", 100))
                    dev.commit()
                    render(dev, cfg, gifs)
                    log.info("config reloaded")
    finally:
        for g in gifs.values(): g.stop()
        try: dev.clear_all(); dev.commit()
        except Exception: pass
        dev.close()
        log.info("clean exit")

if __name__ == "__main__":
    main()
