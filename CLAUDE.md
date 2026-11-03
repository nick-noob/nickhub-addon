# CLAUDE.md

Context for Claude Code sessions on this repo. Nick works with Claude on two machines, and this file keeps both sessions in sync. This repo is public, so never write secrets or personal details here.

## What this is

NickHub tracks Nick's WoW Forever 1–60 run (character **Shrim Pina**, Orc Hunter, realm Forever) and shows it at https://nickhub.com.

```
addon (Lua, in game) → SavedVariables file → uploader (Python, on the PC) → Cloudflare Worker + KV → dashboard (browser)
```

WoW Forever launches **2026-11-04 at 3:00 PM PT** (23:00 UTC). The site shows a countdown banner until then.

| Path | What it is |
|---|---|
| `addon/NickHubTracker/` | The addon. It logs level-ups, kills, quests, deaths and zones to `NickHubTrackerDB` |
| `uploader/` | Python uploader (standard library only) that watches the SavedVariables file and POSTs it |
| `site/src/worker.js` | Cloudflare Worker: `POST /api/ingest` (Bearer token), `GET /api/data`, and static assets for everything else |
| `site/public/` | `index.html` (dashboard), `how-it-works.html`, `how-the-race-works.html`, `demo.json`, favicons |
| `tools/` | Simulator: runs the real addon against a fake WoW API (`python tools/run_sim.py`, needs `pip install lupa`). It generated `site/public/demo.json` |
| `scripts/install-addon.ps1` | Windows script that links the addon into `World of Warcraft\<flavor>\Interface\AddOns` with a junction |

## Which machine does what

**Windows PC: playing.** It has WoW, the addon (linked from this repo by junction, so the repo folder must not move) and the uploader. Node and Wrangler aren't installed here.
- After pulling an addon change, `/reload` in game to load it.
- `uploader/config.json` holds the upload password. It's gitignored and must never be committed or printed.

**Mac: development and deploys.** It has Node, Wrangler (logged into Cloudflare) and the `gh` CLI.
- **The site is only deployed from the Mac**, with `npx wrangler deploy` in `site/`. Pushing to GitHub doesn't deploy it.
- **Cloudflare data changes** (KV reads and deletes, secrets) also happen on the Mac.

From Windows, commit and push site changes, then ask Nick to deploy them from the Mac.

## Rules

- **Never commit secrets.** That covers the upload password (`INGEST_TOKEN`), `uploader/config.json`, `site/.dev.vars` and any per-friend config. GitHub secret scanning and push protection are on as a backstop.
- **Commit identity:** commits use the GitHub noreply address, never a personal email. Before committing on a new machine, set it for this repo:
  `git config user.name "Nick"` and `git config user.email "106461792+nick-noob@users.noreply.github.com"`
- **No license:** all rights are reserved, and the README says so. The orc favicon is Blizzard's art and stays noted as such.
- **Ask first:** commit or push only when Nick asks, and confirm before anything public-facing or hard to undo.
- **Match the code:** follow the existing style and comment density. The site is plain HTML, CSS and JS with Chart.js, and has no build step.
- **Light and dark themes:** the dashboard's colours are CSS tokens on `:root`, redefined for dark mode. Keep both themes working, and keep pages usable at phone width.

## Status as of 2026-11-03

- **Done:**
  - The site is live, still showing the demo data (Shrim Pina, Horde route, simulated level 60) with a "demo data" banner.
  - `INGEST_TOKEN` is set in Cloudflare, and the upload endpoint answers 401 without it.
- **Not yet verified:** a real upload. Nick is setting up Windows, following the steps below, and plans a test sync on TBC Anniversary before launch.
- **After the test sync:** the test character is stored on the live site, and `/nh reset` doesn't remove it from there. The Mac session must delete it from KV before launch so the demo shows again.

### Windows setup steps (summary)
1. **Install the tools:** GitHub Desktop, and Python from python.org with "Add python.exe to PATH" ticked.
2. **Clone** this repo, by default into `Documents\GitHub\nickhub-addon`.
3. **Install the addon:** run `powershell -ExecutionPolicy Bypass -File .\scripts\install-addon.ps1`.
   - The default is the `_anniversary_` flavor. Add `-Flavor _forever_` for Forever, and `-WowDir` if WoW isn't in the default location.
4. **Configure the uploader:** copy `uploader/config.example.json` to `uploader/config.json`, then fill it in.
   - **`token`:** the upload password.
   - **Path:** replace `CHANGE_ME` with the account folder name, and keep every backslash doubled.
   - **`character`:** blank for the test, `"Shrim Pina"` for Forever.
5. **Create the saved file:** log in, kill a few mobs and type `/nh sync`. The first sync creates the file the uploader reads.
6. **Start the uploader:** double-click `uploader/start_uploader.bat`.
   - **Working** looks like `uploaded — ...`.
   - **`unauthorized`** means the password doesn't match the one in Cloudflare.
   - **A parse or path error** usually means a single backslash or the wrong account folder.
7. **On launch day:**
   - Rerun the install with `-Flavor _forever_` and point `config.json` at the Forever folder.
   - Log in as Shrim Pina with the addon already installed, so it captures everything from level 1.

If the addon shows as **out of date**, tick "Load out of date AddOns". The `.toc` Interface line may need the Forever client's version, which `/dump select(4, GetBuildInfo())` prints.

## Planned: friends leveling race (not built)

A preview page with made-up racers is live at `/how-the-race-works`. Don't build the real thing until Nick says to.

- **Racers:** Nick plus 3 friends, all on Windows.
- **Winner:** the first to reach 60 on the calendar. Rank by level, then XP. The winner comes from the level-60 timestamp, which uses the game server's clock.

Planned work:
- **Passwords:** one per racer, tied to their character, so nobody's uploader can overwrite another run.
- **Storage:** one KV record per character. Today the Worker merges everyone into a single `data` key, so two near-simultaneous uploads can lose one.
- **Loading:** a light summary endpoint, with each character's detail fetched on demand. A level 60 run is about 500 KB.
- **Pages:** a leaderboard home page with a race chart, plus individual pages such as `/shrim-pina`.
- **Friends' app:** a PyInstaller `.exe` built on Windows that finds the WoW folder itself. Each friend gets a zip with their own `config.json`, shared privately and never committed.

When the real leaderboard ships, remove the "Preview" label from `how-the-race-works.html`.
