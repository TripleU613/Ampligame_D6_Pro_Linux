#!/usr/bin/env python3
"""
d6-harvest — extract every reusable asset from the Fifine Control Deck install.

Outputs:
  ~/.local/share/d6-deck/assets/
    icons/         — all PNG/JPG/SVG/GIF (deduped by content hash, named by source)
    plugins/       — every .sdPlugin (manifest + icons + actions) preserved
    profiles/      — default profile JSONs
    catalog.json   — searchable manifest:
                       { "icons":   [{name,path,plugin,sha,size,kind}],
                         "plugins": [{id,name,actions,icon,description}],
                         "anims":   [{name,path,frames,duration_ms}] }

Usage:
  d6-harvest.py [--src /path/to/fifine-install] [--out ~/.local/share/d6-deck/assets]
"""
import os, sys, json, hashlib, shutil, argparse, re
from pathlib import Path
from PIL import Image, ImageSequence

DEFAULT_SRC = Path.home() / ".wine/drive_c/Program Files (x86)/fifine Control Deck"
DEFAULT_OUT = Path.home() / ".local/share/d6-deck/assets"

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico")

def sha256_short(p: Path, n=12) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:n]

def safe_name(s: str) -> str:
    return re.sub(r"[^\w.-]", "_", s)[:80]

def gif_meta(p: Path):
    try:
        im = Image.open(p)
        if not getattr(im, "is_animated", False): return None
        frames = sum(1 for _ in ImageSequence.Iterator(im))
        # average frame duration
        durs = []
        for f in ImageSequence.Iterator(im):
            durs.append(f.info.get("duration", 80))
        return {"frames": frames, "duration_ms": int(sum(durs) / max(1, len(durs)))}
    except Exception:
        return None

def parse_plugin(plugin_dir: Path):
    mf = plugin_dir / "manifest.json"
    if not mf.exists(): return None
    try:
        m = json.loads(mf.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    actions = []
    for a in (m.get("Actions") or []):
        actions.append({
            "name":  a.get("Name"),
            "uuid":  a.get("UUID"),
            "icon":  a.get("Icon"),
            "tooltip": a.get("Tooltip") or a.get("Description"),
        })
    return {
        "id":          m.get("UUID") or plugin_dir.name,
        "name":        m.get("Name") or plugin_dir.name,
        "version":     m.get("Version"),
        "description": m.get("Description"),
        "category":    m.get("Category"),
        "icon":        m.get("Icon"),
        "actions":     actions,
        "_dir":        plugin_dir.name,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--symlink", action="store_true",
                    help="symlink instead of copy (saves disk)")
    args = ap.parse_args()

    if not args.src.exists():
        sys.exit(f"source not found: {args.src}")

    icons_dir   = args.out / "icons"
    plugins_dir = args.out / "plugins"
    profiles_dir = args.out / "profiles"
    for d in (icons_dir, plugins_dir, profiles_dir):
        d.mkdir(parents=True, exist_ok=True)

    catalog = {"icons": [], "plugins": [], "anims": [], "src": str(args.src)}
    seen_hashes = {}

    # ── plugins ──────────────────────────────────────────────
    src_plugins = args.src / "plugins"
    if src_plugins.exists():
        for pdir in sorted(src_plugins.iterdir()):
            if not pdir.is_dir(): continue
            meta = parse_plugin(pdir)
            if not meta: continue
            dst = plugins_dir / pdir.name
            if dst.exists(): shutil.rmtree(dst)
            if args.symlink:
                dst.symlink_to(pdir.resolve())
            else:
                shutil.copytree(pdir, dst, ignore=shutil.ignore_patterns(
                    "*.exe", "*.dll", "*.so", "*.dylib", "node_modules", "__pycache__"
                ))
            meta["_path"] = str(dst)
            catalog["plugins"].append(meta)

    # ── images & gifs ───────────────────────────────────────
    for root, dirs, files in os.walk(args.src):
        rp = Path(root)
        # skip massive non-asset dirs
        rel = rp.relative_to(args.src).parts
        if rel and rel[0] in {"CefView", "node", "translations", "imageformats",
                              "platforms", "mediaservice", "iconengines",
                              "playlistformats", "audio", "bearer", "styles"}:
            dirs[:] = []
            continue
        for fn in files:
            p = rp / fn
            if p.suffix.lower() not in IMG_EXTS: continue
            try:
                size = p.stat().st_size
                if size < 100 or size > 8 * 1024 * 1024: continue
                h = sha256_short(p)
            except Exception:
                continue
            if h in seen_hashes:
                continue
            seen_hashes[h] = True
            origin = "/".join(rel) if rel else "."
            outname = f"{h}_{safe_name(p.stem)}{p.suffix.lower()}"
            outp = icons_dir / outname
            if not outp.exists():
                try:
                    if args.symlink: outp.symlink_to(p.resolve())
                    else: shutil.copy2(p, outp)
                except Exception:
                    continue

            entry = {
                "name":    p.stem,
                "file":    outname,
                "path":    str(outp),
                "origin":  origin,
                "size":    size,
                "kind":    p.suffix.lower().lstrip("."),
            }
            catalog["icons"].append(entry)

            if p.suffix.lower() == ".gif":
                gm = gif_meta(p)
                if gm:
                    catalog["anims"].append({
                        "name": p.stem, "path": str(outp), **gm,
                    })

    # ── default profiles (look for json files describing button layouts) ──
    dd = args.src / "defaultData"
    if dd.exists():
        for jp in dd.rglob("*.json"):
            try:
                data = json.loads(jp.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            # heuristic: profile-like JSON has "Actions" or "Pages" or "Profile"
            keys = {k.lower() for k in data.keys()} if isinstance(data, dict) else set()
            if keys & {"actions", "pages", "profile", "deviceconfig", "states"}:
                outp = profiles_dir / safe_name(jp.relative_to(dd).as_posix().replace("/", "__"))
                outp.write_text(jp.read_text(encoding="utf-8", errors="replace"))

    catalog["icons"].sort(key=lambda e: e["name"].lower())
    (args.out / "catalog.json").write_text(json.dumps(catalog, indent=2))

    # summary
    print(f"out:           {args.out}")
    print(f"plugins:       {len(catalog['plugins'])}")
    print(f"unique icons:  {len(catalog['icons'])}")
    print(f"animated GIFs: {len(catalog['anims'])}")
    profs = list(profiles_dir.iterdir())
    print(f"profiles:      {len(profs)}")
    print(f"\ncatalog → {args.out / 'catalog.json'}")

if __name__ == "__main__":
    main()
