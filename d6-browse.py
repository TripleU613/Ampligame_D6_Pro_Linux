#!/usr/bin/env python3
"""
d6-browse — search and pick assets from the d6-deck catalog.

  d6-browse list                  # all icons
  d6-browse list --gif            # only GIFs
  d6-browse search play           # icons whose name contains "play"
  d6-browse plugin obs            # plugins whose name contains "obs"
  d6-browse pick play             # print a JSON snippet you can paste into a button
"""
import json, sys, argparse
from pathlib import Path

CATALOG = Path.home() / ".local/share/d6-deck/assets/catalog.json"

def load():
    if not CATALOG.exists():
        sys.exit("catalog not found — run d6-harvest.py first")
    return json.loads(CATALOG.read_text())

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--gif", action="store_true")

    p_s = sub.add_parser("search")
    p_s.add_argument("term")

    p_p = sub.add_parser("plugin")
    p_p.add_argument("term")

    p_pk = sub.add_parser("pick")
    p_pk.add_argument("term")
    p_pk.add_argument("--cmd", default="echo pressed",
                      help="command for the button (default: echo pressed)")

    args = ap.parse_args()
    cat = load()

    if args.cmd == "list":
        items = cat["anims"] if args.gif else cat["icons"]
        for it in items:
            extras = ""
            if args.gif: extras = f"  ({it['frames']}f, {it['duration_ms']}ms/f)"
            print(f"{it['name']:32s}  {it.get('file', it['path'])}{extras}")
    elif args.cmd == "search":
        q = args.term.lower()
        for it in cat["icons"]:
            if q in it["name"].lower() or q in it.get("origin", "").lower():
                print(f"{it['name']:32s}  {it['kind']:4s}  {it['origin']}/{it['file']}")
    elif args.cmd == "plugin":
        q = args.term.lower()
        for p in cat["plugins"]:
            if q in p["name"].lower() or q in (p.get("description") or "").lower():
                print(f"\n● {p['name']} ({p['id']})")
                print(f"  {p.get('description','')}")
                for a in p.get("actions", []):
                    print(f"    – {a['name']} ({a['uuid']})")
    elif args.cmd == "pick":
        q = args.term.lower()
        anim = next((a for a in cat["anims"] if q in a["name"].lower()), None)
        if anim:
            snippet = {"gif": anim["path"], "command": args.cmd}
        else:
            ico = next((i for i in cat["icons"] if q in i["name"].lower()), None)
            if not ico: sys.exit(f"no asset matching '{args.term}'")
            snippet = {"image": ico["path"], "command": args.cmd}
        print(json.dumps(snippet, indent=2))

if __name__ == "__main__":
    main()
