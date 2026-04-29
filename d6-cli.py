#!/usr/bin/env python3
"""
d6-cli — interactive setup + button binding for the Fifine Ampligame D6.

Walks you through:
  1. Verifying the device is detected
  2. Writing/loading ~/.config/d6.json
  3. Adding/replacing one or more button bindings (image / gif / label + command)
  4. Optionally launching the d6.py daemon

Run with sudo so libusb can access the device:
  sudo D6_USER=$USER python3 d6-cli.py
"""
import os, sys, json, subprocess, shlex
from pathlib import Path

HERE        = Path(__file__).resolve().parent
DAEMON      = HERE / "d6.py"
CFG_PATH    = Path(os.environ.get("D6_CFG", Path.home() / ".config/d6.json"))
USER        = os.environ.get("D6_USER") or os.environ.get("SUDO_USER") or os.environ.get("USER")
VID, PID    = 0x3142, 0x0060
KEYS        = 15

# ─── ANSI helpers ───
GREEN, RED, CYAN, BOLD, DIM, RESET = "\033[32m", "\033[31m", "\033[36m", "\033[1m", "\033[2m", "\033[0m"
def ok(msg):   print(f"{GREEN}✓{RESET} {msg}")
def err(msg):  print(f"{RED}✗{RESET} {msg}")
def info(msg): print(f"{CYAN}→{RESET} {msg}")
def head(msg): print(f"\n{BOLD}{msg}{RESET}")

# ─── checks ───
def check_deps():
    head("checking dependencies")
    missing = []
    for mod in ("usb.core", "PIL.Image"):
        try: __import__(mod)
        except ImportError: missing.append(mod)
    if missing:
        err(f"missing python modules: {missing}")
        info("install with: sudo apt install python3-usb python3-pil")
        sys.exit(1)
    ok("python deps present")

def check_device():
    head("looking for device")
    import usb.core
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        err(f"D6 not found (looking for {VID:04x}:{PID:04x})")
        info("plug it in and try again. lsusb should list 'HOTSPOTEKUSB'")
        sys.exit(1)
    ok(f"D6 detected at bus {dev.bus} dev {dev.address}")

def check_root():
    if os.geteuid() != 0:
        err("must run as root (libusb needs to claim the interface)")
        info(f"  sudo D6_USER={USER or 'YOURUSER'} python3 {sys.argv[0]}")
        sys.exit(1)

def load_cfg():
    if not CFG_PATH.exists():
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        default = {
            "brightness": 100,
            "buttons": {str(i): {"label": str(i)} for i in range(1, KEYS + 1)}
        }
        CFG_PATH.write_text(json.dumps(default, indent=2))
        ok(f"wrote default config → {CFG_PATH}")
    return json.loads(CFG_PATH.read_text())

def save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, indent=2))
    ok(f"saved → {CFG_PATH}")

# ─── interactive ───
def show_layout(cfg):
    head("current layout (top → bottom, right → left within each row)")
    print(f"  {DIM}physical positions:{RESET}")
    print(f"    top:   [ 5][ 4][ 3][ 2][ 1]")
    print(f"    mid:   [10][ 9][ 8][ 7][ 6]")
    print(f"    bot:   [15][14][13][12][11]")
    print(f"  {DIM}bound:{RESET}")
    for i in range(1, KEYS + 1):
        spec = cfg.get("buttons", {}).get(str(i), {})
        kind = ("image"    if "image" in spec else
                "gif"      if "gif"   in spec else
                spec.get("label") or spec.get("text") or "—")
        cmd  = spec.get("command", "")
        cmd_short = (cmd[:50] + "…") if len(cmd) > 50 else cmd
        print(f"    {i:2d} → {kind:20s}  {DIM}{cmd_short}{RESET}")

def prompt(label, default=None):
    suffix = f" [{default}]" if default else ""
    s = input(f"{CYAN}{label}{RESET}{suffix}: ").strip()
    return s or default

def add_binding(cfg):
    head("add / replace a button binding")
    while True:
        n = prompt(f"button number (1-{KEYS}, blank to stop)")
        if not n: return
        if not n.isdigit() or not (1 <= int(n) <= KEYS):
            err(f"out of range")
            continue
        n = str(int(n))

        print(f"  {DIM}content options: 1) image  2) gif  3) label  (blank = keep current){RESET}")
        kind = prompt("  pick 1/2/3", "3")
        spec = {}
        if kind == "1":
            p = prompt("  image path")
            if not p or not os.path.exists(p):
                err("file not found"); continue
            spec["image"] = os.path.abspath(p)
        elif kind == "2":
            p = prompt("  gif path")
            if not p or not os.path.exists(p):
                err("file not found"); continue
            spec["gif"] = os.path.abspath(p)
            fps = prompt("  fps override (blank = use gif's own timing)")
            if fps and fps.isdigit():
                spec["fps"] = int(fps)
        else:
            text = prompt("  label text", n)
            spec["label"] = text
            bg = prompt("  bg color  R,G,B", "30,30,30")
            fg = prompt("  fg color  R,G,B", "255,255,255")
            try:
                spec["bg"] = [int(x) for x in bg.split(",")]
                spec["fg"] = [int(x) for x in fg.split(",")]
            except ValueError: pass

        cmd = prompt("  command on press (e.g. xdg-open https://...)")
        if cmd:
            spec["command"] = cmd

        cfg.setdefault("buttons", {})[n] = spec
        save_cfg(cfg)
        ok(f"button {n} updated")
        if prompt("add another? y/N", "n").lower() != "y":
            return

def maybe_launch():
    head("launch daemon now?")
    if prompt("y/N", "n").lower() != "y":
        info(f"start it later with:  sudo D6_USER={USER or '$USER'} python3 {DAEMON}")
        return
    if not DAEMON.exists():
        err(f"daemon not found at {DAEMON}")
        return
    info("launching… (Ctrl-C to stop)")
    env = {**os.environ, "D6_USER": USER or "", "D6_CFG": str(CFG_PATH)}
    os.execvpe(sys.executable, [sys.executable, str(DAEMON)], env)

# ─── entry ───
def main():
    print(f"{BOLD}d6-cli{RESET} — Fifine Ampligame D6 setup\n")
    check_root()
    check_deps()
    check_device()
    cfg = load_cfg()
    show_layout(cfg)
    add_binding(cfg)
    maybe_launch()

if __name__ == "__main__":
    main()
