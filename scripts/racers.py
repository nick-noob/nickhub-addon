#!/usr/bin/env python3
"""
Manage race passwords for nickhub.com. Run on the Mac, where Wrangler is logged in to Cloudflare.

    python3 scripts/racers.py add "Character Name"     # new password + racers/<name>/config.json
    python3 scripts/racers.py list                     # who's registered
    python3 scripts/racers.py revoke "Character Name"  # the old password stops working

Each password is stored in Cloudflare KV only as a SHA-256 hash, tied to one character, so a
racer's uploader can update that character and nothing else. The password itself is only
written to the racer's config.json, which lives in the gitignored racers/ folder. Send it
to the racer privately and never commit it.

Add --local to any command to use `wrangler dev`'s local storage instead of the live site.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
RACERS = os.path.join(ROOT, "racers")
PREFIX = "racer:"


def wrangler(args, where):
    cmd = ["npx", "wrangler", "kv", "key", *args, "--binding", "NICKHUB", where]
    res = subprocess.run(cmd, cwd=SITE, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        sys.exit(f"wrangler failed: {(res.stderr or res.stdout).strip()[-400:]}")
    return res.stdout


def registered(where):
    """[(kv key, record)] for every racer password."""
    out = wrangler(["list", "--prefix", PREFIX], where)
    keys = json.loads(out[out.index("["):])
    return [(k["name"], json.loads(wrangler(["get", k["name"], "--text"], where))) for k in keys]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "racer"


def add(name, where):
    if any(r.get("character", "").lower() == name.lower() for _, r in registered(where)):
        sys.exit(f"{name} already has a password. Revoke it first to issue a new one.")
    token = secrets.token_urlsafe(32)
    record = {"character": name, "added": datetime.date.today().isoformat()}
    wrangler(["put", PREFIX + hashlib.sha256(token.encode()).hexdigest(), json.dumps(record)], where)

    with open(os.path.join(ROOT, "uploader", "config.example.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["saved_variables_path"] = cfg["saved_variables_path"].replace("_anniversary_", "_forever_")
    cfg["token"], cfg["character"] = token, name
    folder = os.path.join(RACERS, slug(name))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "config.json")
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    print(f"Registered {name}. Their config is at {os.path.relpath(path, ROOT)}")
    print("Send it privately. It contains their password, so don't post it or commit it.")


def show(where):
    racers = registered(where)
    if not racers:
        print("No racers registered.")
    for _, r in sorted(racers, key=lambda x: x[1].get("character", "").lower()):
        print(f"{r.get('character')}  (added {r.get('added', '?')})")


def revoke(name, where):
    hits = [k for k, r in registered(where) if r.get("character", "").lower() == name.lower()]
    if not hits:
        sys.exit(f"No password registered for {name}.")
    for k in hits:
        wrangler(["delete", k], where)
    print(f"Revoked {name}'s password. Their uploads stop working; their stats stay on the site.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["add", "list", "revoke"])
    ap.add_argument("character", nargs="?", help='the in-game character name, e.g. "Shrim Pina"')
    ap.add_argument("--local", action="store_true", help="use wrangler dev's local storage, for testing")
    args = ap.parse_args()
    where = "--local" if args.local else "--remote"
    name = (args.character or "").strip()
    if args.command != "list" and not name:
        ap.error(f"{args.command} needs a character name")
    {"add": lambda: add(name, where), "list": lambda: show(where), "revoke": lambda: revoke(name, where)}[args.command]()


if __name__ == "__main__":
    main()
