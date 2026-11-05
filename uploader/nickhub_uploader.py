#!/usr/bin/env python3
"""
NickHub uploader: watches the NickHubTracker SavedVariables file and pushes it to nickhub.com.

Usage:
    python nickhub_uploader.py            # watch and upload whenever the file changes
    python nickhub_uploader.py --once     # upload once and exit
    python nickhub_uploader.py --dump     # print the parsed JSON (no upload) for debugging

Settings live in config.json next to this script (see config.example.json).
Only uses the Python standard library.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# Minimal Lua table parser for WoW SavedVariables files
# --------------------------------------------------------------------------
class LuaParser:
    def __init__(self, text):
        self.s = text
        self.i = 0
        self.n = len(text)

    def error(self, msg):
        line = self.s.count("\n", 0, self.i) + 1
        raise ValueError(f"{msg} at line {line}")

    def skip(self):
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n,;":
                self.i += 1
            elif s.startswith("--", self.i):
                if s.startswith("--[[", self.i):
                    end = s.find("]]", self.i)
                    self.i = n if end < 0 else end + 2
                else:
                    end = s.find("\n", self.i)
                    self.i = n if end < 0 else end + 1
            else:
                break

    def parse_file(self):
        out = {}
        while True:
            self.skip()
            if self.i >= self.n:
                return out
            name = self.ident()
            self.skip()
            self.expect("=")
            out[name] = self.value()

    def expect(self, ch):
        if self.s[self.i:self.i + len(ch)] != ch:
            self.error(f"expected {ch!r}")
        self.i += len(ch)

    def ident(self):
        start = self.i
        while self.i < self.n and (self.s[self.i].isalnum() or self.s[self.i] == "_"):
            self.i += 1
        if start == self.i:
            self.error("expected identifier")
        return self.s[start:self.i]

    def value(self):
        self.skip()
        c = self.s[self.i]
        if c == "{":
            return self.table()
        if c == '"' or c == "'":
            return self.string()
        if c == "-" or c.isdigit() or c == ".":
            return self.number()
        word = self.ident()
        if word == "true":
            return True
        if word == "false":
            return False
        if word == "nil":
            return None
        self.error(f"unexpected {word!r}")

    def number(self):
        start = self.i
        if self.s[self.i] == "-":
            self.i += 1
        while self.i < self.n and (self.s[self.i].isalnum() or self.s[self.i] in ".+-"):
            if self.s[self.i] in "+-" and self.s[self.i - 1] not in "eE":
                break
            self.i += 1
        txt = self.s[start:self.i]
        try:
            if txt.lower().startswith(("0x", "-0x")):
                return int(txt, 16)
            v = float(txt)
            return int(v) if v.is_integer() and "." not in txt and "e" not in txt.lower() else v
        except ValueError:
            if txt in ("inf", "-inf", "nan"):
                return None
            self.error(f"bad number {txt!r}")

    ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "\n": "\n", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}

    def string(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        raw = bytearray()
        while True:
            if self.i >= self.n:
                self.error("unterminated string")
            c = self.s[self.i]
            if c == q:
                self.i += 1
                break
            if c == "\\":
                nxt = self.s[self.i + 1]
                if nxt.isdigit():  # \ddd decimal byte escape
                    j = self.i + 1
                    while j < self.i + 4 and j < self.n and self.s[j].isdigit():
                        j += 1
                    out.append(chr(int(self.s[self.i + 1:j])))
                    self.i = j
                    continue
                out.append(self.ESC.get(nxt, nxt))
                self.i += 2
                continue
            out.append(c)
            self.i += 1
        txt = "".join(out)
        # byte escapes produce latin-1 chars; re-decode as UTF-8 when possible
        try:
            return txt.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return txt

    def table(self):
        self.expect("{")
        arr, obj = [], {}
        while True:
            self.skip()
            if self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[":
                self.i += 1
                key = self.value()
                self.skip()
                self.expect("]")
                self.skip()
                self.expect("=")
                obj[key] = self.value()
            else:
                # bare identifier key (name = value) or array value
                save = self.i
                if self.s[self.i].isalpha() or self.s[self.i] == "_":
                    word = self.ident()
                    self.skip()
                    if self.i < self.n and self.s[self.i] == "=" and self.s[self.i + 1] != "=":
                        self.i += 1
                        obj[word] = self.value()
                        continue
                    self.i = save
                arr.append(self.value())
        if obj and not arr:
            # integer-keyed tables (e.g. levels[1..60]) become string keys in JSON
            return {str(k) if not isinstance(k, str) else k: v for k, v in obj.items()}
        if arr and not obj:
            return arr
        if not arr and not obj:
            return {}
        merged = {str(i + 1): v for i, v in enumerate(arr)}
        merged.update({str(k): v for k, v in obj.items()})
        return merged


def parse_saved_variables(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return LuaParser(fh.read()).parse_file()


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------
def load_config():
    path = os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        sys.exit(f"Missing {path}. Copy config.example.json to config.json and fill it in.")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    for key in ("saved_variables_path", "endpoint", "token"):
        if not cfg.get(key) or "CHANGE_ME" in str(cfg[key]):
            sys.exit(f"config.json: set '{key}'")
    cfg["saved_variables_path"] = os.path.expandvars(os.path.expanduser(cfg["saved_variables_path"]))
    return cfg


def build_payload(path, main=None):
    """Every character in the file. `main` (config.json's "character") tells the site which one is
    racing; the rest show up as its alts."""
    data = parse_saved_variables(path).get("NickHubTrackerDB") or {}
    chars = data.get("chars") or {}
    # an alt without a guid hasn't logged in since v3.1.0, so it may be an old first-name entry
    # ("<realm>-Shrim") that mixes characters; it uploads once it logs in again
    chars = {k: c for k, c in chars.items() if c.get("guid") or (main and k.lower().endswith("-" + main.lower()))}
    for c in chars.values():
        # a contiguous 1..N levels table serializes as a Lua array; key it by level again
        if isinstance(c.get("levels"), list):
            first = int(c.get("firstLevel") or 1)
            c["levels"] = {str(first + i): v for i, v in enumerate(c["levels"])}
        for k in ("kills", "quests", "deaths", "zones", "sessions"):
            if isinstance(c.get(k), dict):  # sparse arrays come through as dicts
                c[k] = [c[k][i] for i in sorted(c[k], key=lambda x: int(x))]
            c.setdefault(k, [])
    payload = {"version": data.get("version"), "uploadedAt": int(time.time()), "chars": chars}
    if main:
        payload["main"] = main
    return payload


def upload(cfg, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(
        cfg["endpoint"], data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["token"], "User-Agent": "nickhub-uploader/1"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode(errors="replace")


def summarize(payload):
    parts = []
    for key, c in payload["chars"].items():
        parts.append(f"{key}: lvl {c.get('level')} | {len(c.get('kills') or [])} kills | {len(c.get('quests') or [])} quests")
    return "; ".join(parts) or "no characters"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="upload once and exit")
    ap.add_argument("--dump", metavar="FILE", nargs="?", const="-", help="print parsed JSON instead of uploading (optionally from FILE)")
    args = ap.parse_args()

    if args.dump:
        path = args.dump if args.dump != "-" else load_config()["saved_variables_path"]
        print(json.dumps(build_payload(path), indent=2))
        return

    cfg = load_config()
    path = cfg["saved_variables_path"]
    interval = float(cfg.get("poll_seconds", 5))
    last_hash = None
    print(f"Watching {path}")
    print("In game: type /nh sync (or log out) to write new data. Ctrl+C to stop.")

    while True:
        try:
            if os.path.exists(path):
                raw = open(path, "rb").read()
                h = hashlib.sha256(raw).hexdigest()
                if h != last_hash:
                    time.sleep(1)  # let WoW finish writing
                    payload = build_payload(path, cfg.get("character"))
                    status, text = upload(cfg, payload)
                    stamp = time.strftime("%H:%M:%S")
                    if 200 <= status < 300:
                        print(f"[{stamp}] uploaded — {summarize(payload)}")
                        last_hash = hashlib.sha256(open(path, "rb").read()).hexdigest()
                    else:
                        print(f"[{stamp}] server said {status}: {text[:200]}")
            elif last_hash is None:
                print("SavedVariables file not found yet — it appears after your first /reload or logout with the addon enabled.")
                last_hash = ""
        except urllib.error.HTTPError as e:
            print(f"Upload failed: HTTP {e.code} {e.read().decode(errors='replace')[:200]}")
        except (urllib.error.URLError, OSError) as e:
            print(f"Upload failed: {e}")
        except ValueError as e:
            print(f"Couldn't parse SavedVariables ({e}); will retry.")
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
