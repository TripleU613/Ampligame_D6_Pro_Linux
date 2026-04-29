#!/usr/bin/env python3
"""
d6-set — quickly bind a button: copies the image into the managed icon folder
so the source can't be clobbered, updates ~/.config/d6.json (or $D6_CFG).

Usage:
  d6-set.py <button> <image_path> [<command>]
  d6-set.py 1 ~/Pictures/gmail.png 'firefox https://mail.google.com'
  d6-set.py clear 4               # remove a binding

Env:
  D6_CFG       — config path  (default ~/.config/d6.json)
  D6_ICONS_DIR — managed icons (default ~/.local/share/d6-deck/icons)
"""
import os, sys, json, shutil, hashlib
from pathlib import Path

CFG_PATH  = Path(os.environ.get("D6_CFG", Path.home() / ".config/d6.json"))
ICONS_DIR = Path(os.environ.get("D6_ICONS_DIR", Path.home() / ".local/share/d6-deck/icons"))

def usage():
    print(__doc__); sys.exit(1)

def copy_managed(src: Path) -> Path:
    """Copy src into ICONS_DIR with a content-hash prefix; return new path.
    Stable: same content → same managed path."""
    src = Path(src).expanduser().resolve()
    if not src.exists():
        sys.exit(f"image not found: {src}")
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(src.read_bytes()).hexdigest()[:10]
    safe = "".join(c for c in src.stem if c.isalnum() or c in "._-")[:60] or "icon"
    dst = ICONS_DIR / f"{h}_{safe}{src.suffix.lower()}"
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst

def load_cfg():
    if not CFG_PATH.exists():
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CFG_PATH.write_text(json.dumps({"brightness":100, "buttons":{}}, indent=2))
    return json.loads(CFG_PATH.read_text())

def save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, indent=2))

def main():
    args = sys.argv[1:]
    if len(args) < 2:
        usage()

    cfg = load_cfg()
    buttons = cfg.setdefault("buttons", {})

    if args[0] == "clear":
        n = args[1]
        buttons.pop(str(int(n)), None)
        save_cfg(cfg)
        print(f"cleared button {n}")
        return

    n = str(int(args[0]))
    src = Path(args[1]).expanduser()
    cmd = args[2] if len(args) > 2 else buttons.get(n, {}).get("command", "")

    managed = copy_managed(src)
    spec = {"image": str(managed)}
    if cmd: spec["command"] = cmd
    buttons[n] = spec
    save_cfg(cfg)
    print(f"button {n}: image → {managed}")
    if cmd: print(f"           cmd   → {cmd}")

if __name__ == "__main__":
    main()
