# NickHub Leveling Tracker

A custom World of Warcraft addon that logs a WoW Forever 1–60 run, kill by kill, and publishes it to a live website.

- **See it live:** [nickhub.com](https://nickhub.com)
- **Read how it works:** [nickhub.com/how-it-works](https://nickhub.com/how-it-works)

WoW addons can't go online, so the addon saves to a file, a small uploader on the PC sends that file to a Cloudflare Worker, and the dashboard reads it from there.

```
WoW addon ──(/nh sync writes SavedVariables)──> uploader on your PC ──HTTPS──> Cloudflare Worker (nickhub.com) ──> dashboard
```

| Folder | What it is |
|---|---|
| `addon/NickHubTracker` | The in-game addon |
| `uploader/` | Python script that watches the addon's saved file and uploads it |
| `site/` | Cloudflare Worker + dashboard (shows demo data until your first upload; add `?demo` to the URL to see it anytime) |
| `scripts/` | `install-addon.ps1` — puts the addon into your WoW folder on Windows |
| `tools/` | Test harness that runs the addon against a fake WoW API |

**What gets logged:** each level-up (time, /played, zone, gold), every mob kill (mob, creature type, mob level, XP, zone — pet kills included), every quest turn-in (title, XP, money, how long you had it), deaths (who killed you, where), pet deaths, zone changes, and XP split by mobs vs quests.

---

# Setup

These are the steps for running this tracker, written for nickhub.com. On your own copy, use your own domain in place of `nickhub.com`, including in `site/wrangler.toml`, and your own KV namespace `id`. The `id` in this repo belongs to the live site and won't work on another Cloudflare account.

## 1. Put nickhub.com on Cloudflare (one time, ~10 min)

1. Make a free account at dash.cloudflare.com → **Add a domain** → `nickhub.com` → Free plan.
2. Cloudflare gives you two nameservers. At your registrar, replace nickhub.com's nameservers with those. It usually takes minutes, sometimes a few hours.

## 2. Deploy the site (one time)

Needs Node.js 18+ (`brew install node` if you don't have it).

```bash
cd site
npm install
npx wrangler login
npx wrangler kv namespace create NICKHUB
```

Copy the `id` it prints into `wrangler.toml`, replacing the existing `id` under `[[kv_namespaces]]`. Then make an upload password and store it as a secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
npx wrangler secret put INGEST_TOKEN      # paste the value from above
npx wrangler deploy
```

nickhub.com now shows the dashboard with demo data until your first upload. Redeploy with `npx wrangler deploy` whenever you change anything in `site/`.

> Want to try it before the domain is ready? Comment out the `routes` block in `wrangler.toml` and deploy — you'll get a free `nickhub.<you>.workers.dev` URL. Use that in the uploader's `endpoint` for now.

## 3. Install the addon (Windows)

Get the repo onto your Windows PC with `git clone https://github.com/nick-noob/nickhub-addon.git` (or GitHub Desktop, or **Code → Download ZIP** on the repo page). Then, in PowerShell from the repo folder:

```powershell
.\scripts\install-addon.ps1                     # TBC Anniversary, for testing
.\scripts\install-addon.ps1 -Flavor _forever_   # WoW Forever (check the folder name Battle.net creates)
```

This links `addon\NickHubTracker` into `World of Warcraft\<flavor>\Interface\AddOns\`, so a later `git pull` updates the addon with no copying. Add `-Copy` to copy it instead, or `-WowDir "D:\..."` if WoW isn't in Program Files. If PowerShell refuses to run the script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

No PowerShell? Copy the `addon\NickHubTracker` folder into `Interface\AddOns\` by hand.

If the character screen lists it as **out of date**, tick *Load out of date AddOns*, or run `/dump select(4, GetBuildInfo())` in game and put that number on the `## Interface:` line of `NickHubTracker.toc`.

In game:

| Command | Does |
|---|---|
| `/nh` | Status: level, /played, kills, quests, deaths |
| `/nh sync` | Saves now (reloads your UI — ~3 seconds) |
| `/nh auto on` | Pops a "Sync now?" button after every level-up |
| `/nh reset confirm` | Wipes this character's log (use after testing on TBC) |

WoW only writes addon data to disk on a reload or logout — that's why sync reloads the UI. Nothing is lost between syncs; it just isn't on the website yet.

## 4. Run the uploader

Needs Python 3 (no extra packages).

1. Copy `uploader/config.example.json` to `uploader/config.json`.
2. Set `saved_variables_path` — replace `CHANGE_ME` with your account folder name (look in `World of Warcraft\_anniversary_\WTF\Account\`). Use the `_anniversary_` path to test, the Forever path for the real run.
3. Set `token` to the INGEST_TOKEN from step 2, and `endpoint` to `https://nickhub.com/api/ingest`.
4. Double-click `start_uploader.bat` (or run `python uploader\nickhub_uploader.py`) and leave the window open while you play. Python comes from python.org or the Microsoft Store; tick "Add to PATH" when installing.

`config.json` holds your upload password, so it's in `.gitignore` and never goes to GitHub.

Each `/nh sync` or logout → the uploader notices within a few seconds → nickhub.com updates. `python uploader\nickhub_uploader.py --dump` prints what it would upload, handy for debugging.

Optional `"character": "Shrim Pina"` in config.json uploads only that character (skips your TBC test alt).

## Adding racers (friends)

Each friend gets their own upload password, tied to their character. Their uploader can update that character and nothing else, so nobody can overwrite another run. Run this on the Mac, where Wrangler is logged in:

```bash
gh release download --pattern NickHub.exe --dir release --clobber   # latest app build
python3 scripts/racers.py add "Character Name"      # registers them and builds their zip
python3 scripts/racers.py package "Character Name"  # rebuild their zip, e.g. after a new app build
python3 scripts/racers.py list                      # who's registered
python3 scripts/racers.py revoke "Character Name"   # their password stops working; their stats stay
```

`add` writes `racers/<name>/config.json` and, when `release/NickHub.exe` is there, `racers/<name>/NickHub-<name>.zip`. That zip holds the app, their config and a "Start here" note. Send it to the friend privately (a Discord DM or Google Drive share works; Gmail blocks `.exe` files). It contains their password, and the `racers/` and `release/` folders are gitignored so neither can be committed. To replace a lost password, revoke it and add the friend again. Your own `INGEST_TOKEN` stays the admin password and can update any character.

### The racer app (NickHub.exe)

`uploader/nickhub_app.py` is the uploader for friends, built into a single `NickHub.exe` by GitHub Actions (`.github/workflows/build-app.yml`). The build also smoke-tests the exe on Windows against a fake WoW install. Each push that touches `uploader/` or `addon/` produces a build artifact, and publishing a GitHub release attaches `NickHub.exe` to it.

When a friend double-clicks it, it:
1. Finds WoW Forever, checking the registry and the usual install folders on every drive, and asks for the folder if it can't find one.
2. Installs or updates the bundled addon in `Interface\AddOns`.
3. Watches every WoW account's saved file and uploads changes, like the uploader you run.

To check it on a PC without uploading anything, run `NickHub.exe --check`.

Friends who only want the addon can download it from the [latest release](https://github.com/nick-noob/nickhub-addon/releases/latest). Either way, it needs to be installed before their first login.

## Testing on TBC Anniversary before launch

1. Install the addon there, log in. You should see `NickHub tracking <name>` in chat.
2. Target and kill a few mobs, turn in a quest, then `/nh` — kills and quests should count up.
3. `/nh sync` with the uploader running → check nickhub.com.
4. When done, `/nh reset confirm` on the test character (or set `"character"` in config.json).

## Workflow: build on the Mac, play on Windows

**Mac (VS Code):** edit the code → commit → push from the Source Control panel. The Lua extension VS Code recommends is set up to know WoW's functions, so you won't get a wall of warnings. Run `python3 tools/run_sim.py` to sanity-check addon changes against the fake WoW API before pushing (needs `pip3 install lupa`).

**Windows (playing):** `git pull` in the repo folder → `/reload` in game. With the junction from step 3, the new addon is live right away.

**Site changes:** pushing doesn't deploy the site. Run `npx wrangler deploy` from `site/` on whichever computer you're on.

## Notes and limits

- A "kill" is any mob you or your pet damaged that died. Mobs you hit but another player tagged can occasionally count; grey mobs count but give no XP.
- Creature type and mob level come from targeting, mouseover or nameplates, so turn nameplates on (V) for the best coverage.
- Forever runs a Classic-era client; the addon uses only APIs those clients share and skips any event a client doesn't have. Give it a quick check on launch night with `/nh`.
- `tools/` has the test harness that runs the addon against a fake WoW API (`python tools/run_sim.py` — needs `pip install lupa`). It's how `site/public/demo.json` was made.

## Rights

This repo has no open source license, so all rights are reserved. You're welcome to read the code, but no permission is granted to reuse or redistribute it. Chart.js (`site/public/chart.umd.min.js`) is third-party code under its own MIT License.

This is an unofficial fan project and isn't affiliated with or endorsed by Blizzard Entertainment. World of Warcraft and the orc portrait used as the site icon (`site/public/favicon.png` and `site/public/apple-touch-icon.png`) belong to Blizzard Entertainment.
