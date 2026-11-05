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
| `site/src/worker.js` | Cloudflare Worker: `POST /api/ingest` (Bearer password), `GET /api/summary`, `GET /api/char/<key>`, `GET /api/data`, and static assets for everything else |
| `scripts/racers.py` | Mac-only tool that adds, lists and revokes per-racer upload passwords (hashed in KV), writes each racer's `config.json` into the gitignored `racers/` folder, and packages it with `release/NickHub.exe` into a zip to send |
| `uploader/nickhub_app.py` | The racers' app, built into `NickHub.exe`. It finds WoW Forever, installs or updates the bundled addon, and watches and uploads every account's saved file. `--test` (run by `Test my setup.bat` in racer zips) checks the password with an empty upload, plus WoW and the addon. `--check` is a dry run |
| `.github/workflows/build-app.yml` | Builds `NickHub.exe` on Windows with PyInstaller, smoke-tests it against a fake WoW install, and attaches it to published releases |
| `site/public/` | `index.html` (leaderboard home page with the launch countdown), `racer.html` (one racer's profile, served at `/<racer-name>`; `/racer?demo` shows `demo.json`), `how-it-works.html`, `how-the-race-works.html`, favicons |
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

- **Never commit secrets.** That covers the upload password (`INGEST_TOKEN`), `uploader/config.json`, `site/.dev.vars` and anything in `racers/`. GitHub secret scanning and push protection are on as a backstop.
- **Commit identity:** commits use the GitHub noreply address, never a personal email. Before committing on a new machine, set it for this repo:
  `git config user.name "Nick"` and `git config user.email "106461792+nick-noob@users.noreply.github.com"`
- **No license:** all rights are reserved, and the README says so. The orc favicon is Blizzard's art and stays noted as such.
- **Ask first:** commit or push only when Nick asks, and confirm before anything public-facing or hard to undo.
- **Match the code:** follow the existing style and comment density. The site is plain HTML, CSS and JS with Chart.js, and has no build step.
- **Light and dark themes:** the dashboard's colours are CSS tokens on `:root`, redefined for dark mode. Keep both themes working, and keep pages usable at phone width.

## Status as of 2026-11-03

- **Done:**
  - The site is live. The home page is the race leaderboard, empty until the first sync. The simulated demo run (Shrim Pina, Horde route, level 60) lives at `/racer?demo`.
  - `INGEST_TOKEN` is set in Cloudflare, and the upload endpoint answers 401 without it.
- **Windows pipeline verified:** a TBC Anniversary test upload worked on 2026-11-03, and its test character was deleted from KV afterwards. Nick's `config.json` now points at `_forever_` with `"character": "Shrim Pina"`.
- **Race backend live (2026-11-03):**
  - **Storage:** each character is its own KV key, `char:<realm-name>`, with a small summary in the key's metadata. The old single `data` key is gone.
  - **Passwords:** racers live under `racer:<sha256 of password>` → `{ character }`. A racer password may only update keys ending in `-<character>`, while `INGEST_TOKEN` (Nick's) is the admin password and may update any key.
  - **No friends registered yet.**
- **To remove a stray character** (such as a test upload), delete its `char:<key>` from KV. `/nh reset` only clears the PC.
- **Release:** `release/NickHubTracker.zip` and `release/release-notes.md` (both gitignored) are ready for GitHub release `v1.0.0`, which Nick publishes himself. Publishing it makes the workflow attach `NickHub.exe`.
- **Racers' setup:** each racer gets a personal zip from `racers.py` containing the app, their config and a "Start here" note. The app installs the addon, so racers don't need the addon zip.

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

If the addon shows as **out of date**, tick "Load out of date AddOns". **Incompatible** means the client's interface number is missing from the `.toc` Interface line, and the checkbox can't override it. The number comes from the version at the bottom-left of the login screen (1.60.1 → 16001) or `/dump select(4, GetBuildInfo())`. Forever shipped as 1.60.1 (build 70755) on 2026-11-02, and the `.toc` lists 16000–16005 to cover launch-day patches. A `.toc` change also needs a new release and re-sent racer zips, because `NickHub.exe` bundles the addon.

## WoW Forever client quirks (found on launch day, 2026-11-04)

- **Interface number:** the client is 1.60.x, so the `.toc` lists 16000–16005. A version outside that list shows the addon as **Incompatible**.
- **Names:** `UnitName` returns only the first name ("Shrim"), so keys look like `<realm>-Shrim`. The uploader and the Worker match a racer's registered full name or its first word, and the site shows the full name.
- **No combat log:** registering `COMBAT_LOG_EVENT_UNFILTERED` is a forbidden action there. It caused a "blocked from an action" popup (`UNKNOWN()`) on every load, so the addon skips it on interface 16000–19999. Kills come from the "X dies, you gain N experience" messages instead, so killed-by on deaths and pet deaths stay blank.
- **/played:** the timed `RequestTimePlayed` after login and level-up works. Don't replace `ChatFrame_DisplayTimePlayed`; the addon mutes the chat windows instead.
- **Blocked calls:** if WoW blocks one, the addon prints "WoW blocked a call to …" in chat.
- **Testing:** `NO_CLEU=1 python tools/run_sim.py` simulates the Forever client.

## Friends leveling race

`/how-the-race-works` explains the race to friends, with a sample leaderboard of made-up racers.

- **Racers:** Nick plus 3 friends, all on Windows.
- **Winner:** the first to reach 60 on the calendar. Rank by level, then XP. The winner comes from the level-60 timestamp, which uses the game server's clock.

Built (2026-11-03): per-racer passwords (`scripts/racers.py`), per-character storage, `/api/summary` (cached about 30 seconds, because KV list operations are limited on the free plan) and `/api/char/<key>`.
- **Leaderboard:** `index.html` ranks finished racers by who hit 60 first, then everyone else by level, then XP. It shows a race chart from each racer's `line:` timeline and group records, and refreshes every minute.
- **Profiles:** each racer's page is `racer.html`, served at `/<name-slug>`. The Worker sends any single path segment that isn't a file to that page.
- **Colours:** each racer's colour comes from their key's alphabetical position (`--r1`…`--r4`, a validated palette), so it doesn't change as the standings do.

