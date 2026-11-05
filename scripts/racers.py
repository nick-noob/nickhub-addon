#!/usr/bin/env python3
"""
Manage race passwords for nickhub.com. Run on the Mac, where Wrangler is logged in to Cloudflare.

    python3 scripts/racers.py add "Character Name"      # new password + racers/<name>/config.json
    python3 scripts/racers.py package "Character Name"  # zip NickHub.exe + their config to send them
    python3 scripts/racers.py package                   # rebuild every racer's zip
    python3 scripts/racers.py list                      # who's registered
    python3 scripts/racers.py revoke "Character Name"   # the old password stops working

`package` (also run by `add`) builds zips for the release named by the addon's .toc Version line,
e.g. NickHub-shrim-pina-v3.3.0.zip. It checks release/NickHub.exe against that GitHub release
and downloads the right build if it's missing or different, so publish the release first.

Each password is stored in Cloudflare KV only as a SHA-256 hash, tied to the racer's main. Their
uploader sends the main and any alts, and a character belongs to whoever uploaded it first, so
nobody can update anyone else's characters. The password itself is only
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
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
RACERS = os.path.join(ROOT, "racers")
EXE = os.path.join(ROOT, "release", "NickHub.exe")
TOC = os.path.join(ROOT, "addon", "NickHubTracker", "NickHubTracker.toc")
PREFIX = "racer:"

START_HERE = """NickHub v{version}: racing as {name}

1. Unzip this whole folder somewhere you'll keep it, like Documents\\NickHub.
   Before launch, double-click "Test my setup.bat". It checks your password and
   finds WoW without uploading any stats, then tells you if anything needs fixing.
2. Double-click NickHub.exe before you log in to WoW Forever.
   Windows may say "Windows protected your PC". Click More info, then Run anyway.
   It finds WoW, installs the NickHub Tracker addon, and keeps it up to date.
3. Leave the NickHub window open while you play.
4. In game, type /nh sync whenever you want nickhub.com updated. Logging out works too.

Optional: enemy nameplates on (press V) help a little. Your kills count either way,
and targeting a mob teaches the addon its type and level. Nameplates also catch
mobs you kill without ever targeting, like extras in an AoE pull.

If it can't find WoW, it asks you to paste your World of Warcraft folder,
the one that contains _forever_. It remembers it after that.

To start it automatically: press Win+R, type shell:startup, press Enter,
and put a shortcut to NickHub.exe in the folder that opens.

config.json holds your personal password. Don't share it.
If it ever leaks, tell Nick and he'll send you a new one.
"""

# keeps its window open when NickHub.exe is missing or blocked, so the racer can read why
TEST_BAT = "\r\n".join([
    "@echo off",
    'cd /d "%~dp0"',
    "if not exist NickHub.exe (",
    "  echo NickHub.exe isn't in this folder.",
    "  echo Unzip the whole folder first: right-click the zip, then Extract All.",
    "  echo If you did, Windows Security may have removed it. Check Protection history.",
    "  pause",
    "  exit /b 1",
    ")",
    "NickHub.exe --test",
    "if errorlevel 1 pause",
    "",
])


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
    try:
        package(name)
    except SystemExit as e:
        print(f"Their zip isn't built yet: {e}\nThen run: python3 scripts/racers.py package \"{name}\"")
        return
    send_note()


def release_version():
    """The release being packaged: the addon's .toc Version line, which NickHub.exe also reports."""
    with open(TOC, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("## Version:"):
                return line.split(":", 1)[1].strip()
    sys.exit(f"No '## Version:' line in {os.path.relpath(TOC, ROOT)}")


def file_sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ensure_exe(version):
    """Make release/NickHub.exe the build attached to GitHub release v<version>."""
    tag = "v" + version
    res = subprocess.run(["gh", "release", "view", tag, "--json", "assets"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        sys.exit(f"GitHub has no release {tag} yet. Publish it first:\n"
                 f'  gh release create {tag} release/NickHubTracker.zip --title "NickHub Tracker {tag}" --notes-file release/release-notes.md')
    exe = next((a for a in json.loads(res.stdout)["assets"] if a["name"] == "NickHub.exe"), None)
    if not exe:
        sys.exit(f"Release {tag} doesn't have NickHub.exe yet. The build takes about 5 minutes, so try again then.")
    want = (exe.get("digest") or "").removeprefix("sha256:")
    if want and os.path.exists(EXE) and file_sha256(EXE) == want:
        return
    print(f"Downloading NickHub.exe from {tag}...")
    subprocess.run(["gh", "release", "download", tag, "--pattern", "NickHub.exe", "--dir", os.path.dirname(EXE), "--clobber"],
                   check=True, stdin=subprocess.DEVNULL)
    if want and file_sha256(EXE) != want:
        sys.exit(f"The downloaded NickHub.exe doesn't match release {tag}. Try again.")


def package(name, version=None):
    folder = os.path.join(RACERS, slug(name))
    cfg = os.path.join(folder, "config.json")
    if not os.path.exists(cfg):
        sys.exit(f"No config for {name} at {os.path.relpath(cfg, ROOT)}. Run `add` first.")
    if version is None:
        version = release_version()
        ensure_exe(version)
    for old in os.listdir(folder):  # an older version's zip would only cause mix-ups
        if old.startswith("NickHub-") and old.endswith(".zip"):
            os.remove(os.path.join(folder, old))
    out = os.path.join(folder, f"NickHub-{slug(name)}-v{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(EXE, "NickHub/NickHub.exe")
        z.write(cfg, "NickHub/config.json")
        z.writestr("NickHub/Start here.txt", START_HERE.format(name=name, version=version).replace("\n", "\r\n"))
        z.writestr("NickHub/Test my setup.bat", TEST_BAT)
    os.chmod(out, 0o600)
    print(f"Packaged {os.path.relpath(out, ROOT)}")


def package_all():
    version = release_version()
    ensure_exe(version)
    names = []
    for d in sorted(os.listdir(RACERS)) if os.path.isdir(RACERS) else []:
        cfg = os.path.join(RACERS, d, "config.json")
        if os.path.exists(cfg):
            with open(cfg, encoding="utf-8") as fh:
                names.append(json.load(fh).get("character") or d)
    if not names:
        sys.exit("No racers in racers/. Run `add` first.")
    for name in names:
        package(name, version)


def send_note():
    print("Send each zip privately (Discord DM or a Google Drive share; Gmail blocks .exe files).")
    print("Each contains that racer's password, so don't post it in a group chat or commit it.")


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
    ap.add_argument("command", choices=["add", "package", "list", "revoke"])
    ap.add_argument("character", nargs="?", help='the in-game character name, e.g. "Shrim Pina"')
    ap.add_argument("--local", action="store_true", help="use wrangler dev's local storage, for testing")
    args = ap.parse_args()
    where = "--local" if args.local else "--remote"
    name = (args.character or "").strip()
    if args.command not in ("list", "package") and not name:
        ap.error(f"{args.command} needs a character name")
    {"add": lambda: add(name, where), "package": lambda: (package(name) if name else package_all(), send_note()),
     "list": lambda: show(where),
     "revoke": lambda: revoke(name, where)}[args.command]()


if __name__ == "__main__":
    main()
