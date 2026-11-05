#!/usr/bin/env python3
"""
NickHub app: the double-click version of the uploader, built into NickHub.exe for racers on Windows.

Put NickHub.exe and the config.json Nick sent you in the same folder, then double-click NickHub.exe.
It finds World of Warcraft, installs or updates the NickHub Tracker addon, then watches the addon's
saved file and uploads it to nickhub.com whenever you /nh sync or log out.

    NickHub.exe                         # normal use
    NickHub.exe --test                  # check the password, WoW and addon before launch; uploads nothing
    NickHub.exe --check                 # set up and show what it would upload, without uploading
    NickHub.exe --wow-dir "D:\\Games\\World of Warcraft"
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import string
import sys
import time
import urllib.error

import nickhub_uploader as up

FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
# PyInstaller unpacks bundled data to sys._MEIPASS; from source, use the repo's addon folder
ADDON_SRC = os.path.join(getattr(sys, "_MEIPASS", ""), "NickHubTracker") if FROZEN else os.path.join(HERE, "..", "addon", "NickHubTracker")
FLAVOR = "_forever_"


def say(text=""):
    print(text, flush=True)


def pause():
    # a double-clicked window closes on exit, so wait; skipped when there's no one to press Enter (e.g. CI)
    if FROZEN and sys.stdin and sys.stdin.isatty():
        input("\nPress Enter to close.")


def fail(text):
    raise SystemExit(text)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def load_config(path):
    if not os.path.exists(path):
        fail(f"Can't find config.json. Put the config.json Nick sent you in the same folder as this app:\n  {os.path.dirname(path)}")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    for key in ("endpoint", "token"):
        if not cfg.get(key) or "CHANGE_ME" in str(cfg[key]):
            fail(f"config.json is missing '{key}'. Ask Nick for a fresh config.json.")
    return cfg


def save_config(path, cfg):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")


# --------------------------------------------------------------------------
# Finding World of Warcraft
# --------------------------------------------------------------------------
def registry_paths():
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft")):
        for value in ("InstallPath", "GamePath"):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    p = os.path.normpath(winreg.QueryValueEx(key, value)[0])
            except OSError:
                continue
            if os.path.isfile(p):
                p = os.path.dirname(p)
            # the registry often points inside a game folder such as _retail_
            if os.path.basename(p).startswith("_"):
                p = os.path.dirname(p)
            out.append(p)
    return out


def wow_candidates(cfg):
    if cfg.get("wow_dir"):
        yield cfg["wow_dir"]
    yield from registry_paths()
    if os.name == "nt":
        for d in string.ascii_uppercase:
            drive = f"{d}:\\"
            if not os.path.exists(drive):
                continue
            for sub in ("Program Files (x86)", "Program Files", "", "Games", "Program Files (x86)\\Battle.net", "Battle.net"):
                yield os.path.join(drive, sub, "World of Warcraft")


def game_folder(wow_dir, flavor):
    """The Forever game folder inside a WoW install, e.g. ...\\World of Warcraft\\_forever_."""
    if not wow_dir or not os.path.isdir(wow_dir):
        return None
    if os.path.basename(os.path.normpath(wow_dir)).startswith("_"):  # they gave the game folder itself
        return os.path.normpath(wow_dir)
    exact = os.path.join(wow_dir, flavor)
    if os.path.isdir(exact):
        return exact
    loose = sorted(glob.glob(os.path.join(glob.escape(wow_dir), "_*forever*_")))
    return loose[0] if loose else None


def find_game(cfg, cfg_path, interactive):
    flavor = cfg.get("flavor") or FLAVOR
    seen, installs = set(), []
    for cand in wow_candidates(cfg):
        key = os.path.normcase(os.path.normpath(cand))
        if key in seen:
            continue
        seen.add(key)
        game = game_folder(cand, flavor)
        if game:
            return game
        if os.path.isdir(cand):
            installs.append(cand)
    for wow in installs:
        say(f"Found World of Warcraft at {wow}, but no WoW Forever folder inside it.")
        say("If Forever isn't installed yet, install it in Battle.net and run this app again.")
    if not interactive:
        fail("Couldn't find WoW Forever. Pass --wow-dir with your World of Warcraft folder.")
    while True:
        say()
        say("Paste the path to your World of Warcraft folder and press Enter.")
        say(r"It's the folder that contains _forever_, for example D:\Games\World of Warcraft")
        typed = input("> ").strip().strip('"')
        game = game_folder(typed, flavor)
        if game:
            cfg["wow_dir"] = typed
            save_config(cfg_path, cfg)  # remember it for next time
            return game
        say(f"No WoW Forever folder found in {typed or 'that path'}. Try again.")


# --------------------------------------------------------------------------
# Installing the addon
# --------------------------------------------------------------------------
def file_hashes(root):
    out = {}
    for dirpath, _, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def install_addon(game):
    dest = os.path.join(game, "Interface", "AddOns", "NickHubTracker")
    if os.path.islink(dest) or (hasattr(os.path, "isjunction") and os.path.isjunction(dest)):
        return "linked to a development copy, left alone"
    want = file_hashes(ADDON_SRC)
    if not want:
        fail("This app is missing its copy of the addon. Download NickHub.exe again.")
    have = file_hashes(dest) if os.path.isdir(dest) else {}
    if all(have.get(k) == v for k, v in want.items()):
        return "up to date"
    shutil.copytree(ADDON_SRC, dest, dirs_exist_ok=True)
    return "updated (type /reload in game if you're logged in)" if have else "installed"


# --------------------------------------------------------------------------
# Watching and uploading
# --------------------------------------------------------------------------
def saved_files(game, cfg):
    files = glob.glob(os.path.join(glob.escape(game), "WTF", "Account", "*", "SavedVariables", "NickHubTracker.lua"))
    manual = cfg.get("saved_variables_path")
    if manual and "CHANGE_ME" not in manual and os.path.exists(manual):
        files.append(manual)
    return sorted(set(files))


def fingerprint(files):
    h = hashlib.sha256()
    for p in files:
        h.update(p.encode())
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def build_payload(files, main):
    """One upload covering every WoW account on this PC; the newest copy of a character wins."""
    chars, version = {}, None
    for p in files:
        part = up.build_payload(p, main)
        version = part.get("version") or version
        for key, c in part["chars"].items():
            if key not in chars or (c.get("updatedAt") or 0) >= (chars[key].get("updatedAt") or 0):
                chars[key] = c
    payload = {"version": version, "uploadedAt": int(time.time()), "chars": chars}
    if main:
        payload["main"] = main  # the rest show up on the site as this racer's alts
    return payload


def report(status, text, payload):
    stamp = time.strftime("%H:%M:%S")
    if not 200 <= status < 300:
        say(f"[{stamp}] server said {status}: {text[:200]}")
        return False
    try:
        skipped = json.loads(text).get("skipped") or []
    except ValueError:
        skipped = []
    saved = {k: c for k, c in payload["chars"].items() if k not in skipped}
    say(f"[{stamp}] uploaded: {up.summarize(dict(payload, chars=saved))}")
    if skipped:
        say(f"           not uploaded (another racer's character, or older than what's saved): {', '.join(skipped)}")
    return True


def test(args):
    """A pre-launch check of everything except the game itself. Its only upload is empty, so nothing reaches the leaderboard."""
    cfg_path = args.config or os.path.join(HERE, "config.json")
    problems = []
    say("NickHub setup test")
    say()
    cfg = load_config(cfg_path)
    if args.wow_dir:
        cfg["wow_dir"] = args.wow_dir
    say(f"[ok]  config.json found. Racing as: {cfg.get('character') or 'every character on this PC'}")

    try:
        status, _ = up.upload(cfg, {"version": 0, "chars": {}})
        if 200 <= status < 300:
            say("[ok]  nickhub.com accepted your password")
        else:
            problems.append(f"nickhub.com answered {status}")
    except urllib.error.HTTPError as e:
        problems.append("nickhub.com rejected your password. Ask Nick for a fresh config.json." if e.code == 401 else f"nickhub.com answered {e.code}")
    except (urllib.error.URLError, OSError) as e:
        problems.append(f"Couldn't reach nickhub.com ({e}). Check your internet connection or firewall.")

    try:
        game = find_game(cfg, cfg_path, interactive=False)
    except SystemExit:
        game = None
        problems.append("WoW Forever isn't installed yet, or isn't in a usual place. Once it's installed, run this test again. "
                        "If it still isn't found, double-click NickHub.exe and it will ask for your World of Warcraft folder.")
    if game:
        say(f"[ok]  WoW Forever found: {game}")
        say(f"[ok]  Addon: {install_addon(game)}")
        files = saved_files(game, cfg)
        if files:
            say(f"[ok]  Saved data found. Your next upload: {up.summarize(build_payload(files, cfg.get('character') or None))}")
        else:
            say("[--]  No saved data yet. That's expected before your first login. It appears after your first /nh sync.")

    for p in problems:
        say(f"[!!]  {p}")
    say()
    say("All set. Double-click NickHub.exe before you log in to WoW Forever." if not problems else
        f"{len(problems)} thing{'s' if len(problems) > 1 else ''} to fix. Send Nick a screenshot of this window if you're stuck.")


def run(args):
    if args.test:
        test(args)
        pause()
        return
    cfg_path = args.config or os.path.join(HERE, "config.json")
    cfg = load_config(cfg_path)
    if args.wow_dir:
        cfg["wow_dir"] = args.wow_dir
    character = cfg.get("character") or None

    say("NickHub uploader")
    say(f"Racing as: {character or 'every character on this PC'}")
    game = find_game(cfg, cfg_path, interactive=not args.check)
    say(f"WoW Forever: {game}")
    say(f"Addon: {install_addon(game)}")

    if args.check:
        files = saved_files(game, cfg)
        say(f"Saved files: {len(files)}")
        for p in files:
            say(f"  {p}")
        if files:
            say(f"Would upload: {up.summarize(build_payload(files, character))}")
        return

    say()
    say("Leave this window open while you play. Type /nh sync in game (or log out) to update nickhub.com.")
    interval = float(cfg.get("poll_seconds", 5))
    last, waiting_said = None, False
    while True:
        try:
            files = saved_files(game, cfg)
            if not files:
                if not waiting_said:
                    say("Waiting for your first /nh sync. The addon's saved file appears after you sync or log out.")
                    waiting_said = True
            else:
                fp = fingerprint(files)
                if fp != last:
                    time.sleep(1)  # let WoW finish writing
                    payload = build_payload(files, character)
                    status, text = up.upload(cfg, payload)
                    if report(status, text, payload):
                        last = fingerprint(files)
        except urllib.error.HTTPError as e:
            say(f"Upload failed: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")
            if e.code == 401:
                say("Your password was rejected. Ask Nick for a fresh config.json.")
        except (urllib.error.URLError, OSError) as e:
            say(f"Upload failed: {e}. Will retry.")
        except ValueError as e:
            say(f"Couldn't read the saved file ({e}). Will retry.")
        if args.once:
            return
        time.sleep(interval)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", action="store_true", help="check the password, WoW and addon before launch, without uploading any stats")
    ap.add_argument("--check", action="store_true", help="set up and show what would be uploaded, then exit")
    ap.add_argument("--once", action="store_true", help="upload once and exit")
    ap.add_argument("--wow-dir", help="your World of Warcraft folder, if it isn't found automatically")
    ap.add_argument("--config", help="path to config.json (defaults to the app's folder)")
    args = ap.parse_args()
    if os.name == "nt":
        os.system("title NickHub")
    try:
        run(args)
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        if e.code not in (None, 0):
            say(str(e.code))
            if not args.check:
                pause()
            sys.exit(1)
    except Exception as e:  # keep the window open so the racer can read what went wrong
        say(f"Something went wrong: {e!r}")
        if not args.check:
            pause()
        sys.exit(1)


if __name__ == "__main__":
    main()
