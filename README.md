# NickHub Leveling Tracker

Tracks a WoW Forever 1–60 run and shows it on nickhub.com.

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

Copy the `id` it prints into `wrangler.toml` (replace `PASTE_KV_NAMESPACE_ID_HERE`). Then make an upload password and store it as a secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
npx wrangler secret put INGEST_TOKEN      # paste the value from above
npx wrangler deploy
```

nickhub.com now shows the dashboard with demo data until your first upload. Redeploy with `npx wrangler deploy` whenever you change anything in `site/`.

> Want to try it before the domain is ready? Comment out the `routes` block in `wrangler.toml` and deploy — you'll get a free `nickhub.<you>.workers.dev` URL. Use that in the uploader's `endpoint` for now.

## 3. Install the addon (Windows)

Get the repo onto your Windows PC with `git clone https://github.com/<you>/nickhub-addon.git` (or GitHub Desktop, or **Code → Download ZIP** on the repo page). Then, in PowerShell from the repo folder:

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

Optional `"character": "Nickhunt"` in config.json uploads only that character (skips your TBC test alt).

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
