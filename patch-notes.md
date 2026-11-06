# Patch notes

Everything we've run into while building NickHub and racing on WoW Forever: what went wrong, why, and what fixed it. Newest first. Release versions refer to the [GitHub releases](https://github.com/nick-noob/nickhub-addon/releases). Site changes go live when the Worker is deployed and don't need a new release.

**Found something?** Post it in the group with a screenshot and the time it happened. Anything the addon prints in chat (`/nh` shows your status) helps too. Since v3.2.0, an error inside the addon is sent along with your next sync, so it can be looked up on the site's side.

## Known issues and limits

These are open, or are limits of the WoW Forever client rather than bugs we can fix.

| Issue | Status |
|---|---|
| Kills inside dungeons usually have no mob type, so they're left out of "Kills by creature type" | **Client limit.** Forever hides enemy details from addons in instance combat. Kill counts and "Most-killed mobs" still work |
| Deaths don't say what killed you, and pet deaths aren't counted | **Client limit.** Both came from the combat log, which Forever doesn't give addons |
| Kills that give no XP, such as grey mobs, aren't counted | **By design.** Kills come from the "X dies, you gain N experience" messages |
| Windows Defender sometimes flags `NickHub.exe` as a threat | **Open.** A false positive on new, unsigned exes built with PyInstaller. Allow it in Windows Security → Protection history. A folder-style build that trips Defender less is an option |
| Windows 11 Smart App Control blocks `NickHub.exe` with no way to run it | **Open.** It blocks every unsigned app. Turning it off can't be undone without resetting Windows, so that's each racer's call |
| Kills from before v2.4.0 on Forever were never recorded | **Can't be recovered.** Kill counts start from when each racer updated |
| Racers who made a second character with the same first name before v3.1.0 have a few of that character's kills mixed into their main | **Can't be separated.** Levels, XP and quests are correct again after the next sync |
| A Forever patch past 1.60.5 would show the addon as **Incompatible** | **Watch for it.** The `.toc` lists interface numbers 16000–16005. A new number takes a one-line fix and a new release |

---

## v3.4.0 (Nov 6): levels no longer drop at logout, and every release shows its version

**Issue:** after logging off for the night, everyone dropped exactly 5 levels on the leaderboard (22 to 17, 21 to 16, 20 to 15), and the race chart lines fell at their last point.

**Cause:** the addon takes a last snapshot at logout, and while logging out the Forever client reports a level 5 too low and an empty XP bar. The level-up history was right all along.

**Fix:**
- **Addon:** the saved level never goes down. It's kept current as you gain XP, and an XP reading with no XP bar is ignored.
- **Worker:** it never saves a character below its highest logged level-up, so the board corrects itself on each racer's next sync, even on older versions.

**Asked for:** an easy way to tell which version each racer has.

**Change:**
- **One number:** the addon's `.toc` holds the version.
- **Where it shows:** the addon prints it at login and in `/nh`. NickHub.exe and its setup test print it too.
- **Zips:** each racer's zip is named with it, such as `NickHub-snort-wasabi-v3.4.0.zip`, and the "Start here" note says it.
- **On the site:** each sync sends the version, so the site's data shows who runs what.
- **Packaging:** `racers.py package` downloads the matching NickHub.exe itself. With no name, it rebuilds every racer's zip.

---

## v3.3.0 (Nov 5): every character on the leaderboard

**Asked for:** a new character (Eat Pizza) didn't appear on the site after `/nh sync`.

**Cause:** by design until now. Each uploader sent only one character per racer, and a racer's password could only update that one.

**Change:**
- **Uploads:** every character on the PC uploads, and each races on the same board. The first character to 60 wins.
- **Ownership:** a racer's first upload of a character makes it theirs, and nobody else's password can update it after that.
- **Colours:** the board has 8 colours, up from 4. They go out in the order characters started, so a new character never changes anyone else's.
- **Update needed:** racers need v3.3.0 for their other characters to show up. Older versions keep uploading the character they registered with.

---

## v3.2.0 (Nov 5): no more error floods in dungeons

**Issue:** during big pulls in Ragefire Chasm, the addon flooded the screen with errors. WoW then warned that it was "experiencing a high number of errors" and offered to disable it.

**Cause:** in instance combat, the modern client hides enemy names, IDs and levels from addons as "secret values", and using one is an error. The addon tried to read each new nameplate's details, so a big pull meant dozens of errors at once.

**Fix:**
- The addon checks whether a mob's details are hidden before using them, and skips that mob if so.
- If anything else ever errors, the addon keeps tracking, says so once in chat, and sends the error with the next sync.

## Site: syncs show up in about 25 seconds (Nov 5)

**Issue:** a `/nh sync` could take up to about 2½ minutes to show on the leaderboard.

**Cause:** the site stored characters in Cloudflare KV, which can take up to a minute to show a new write everywhere. On top of that, the leaderboard was cached for 30 seconds in Cloudflare and again in the browser, and the page refreshed once a minute.

**Fix:** characters now live in Cloudflare D1, a SQL database that shows a write on the very next request. Each full log is gzipped, so a level-60 log takes about 80 KB. The leaderboard isn't cached any more and refreshes every 20 seconds. Racer passwords stay in KV.

## Site: the free Cloudflare plan ran low (Nov 5)

**Issue:** Cloudflare warned that the free plan's daily KV limit was half used.

**Cause:** the free plan allows 1,000 writes and 1,000 key listings a day. Every upload writes, and every leaderboard rebuild lists every character. Five racers on launch night used that up fast.

**Fix:** the account moved to the Workers Paid plan ($5/month), which allows about a million of each a month. The move to D1 also stopped the leaderboard listing KV keys.

## v3.1.0 (Nov 5): a new character no longer takes over your main

**Issue:** two racers showed up at level 1 with hundreds of kills and about 10 hours played.

**Cause:** Forever only gives addons a character's first name, and an account's characters can share it. The addon stored characters as realm plus first name, so a new character with the same first name took over the main's entry. It kept the old history but replaced the level.

**Fix:** characters are now stored under their full name, which `GetUnitName("player", true)` provides ("Shrim Pina"). An old first-name entry moves to whichever character reached its highest level, so a new alt can't claim it. The old entries were deleted from the site, and each racer reappeared with their next sync.

## Setup test window closes instantly (Nov 4)

**Issue:** racers said `Test my setup.bat` wouldn't open at all.

**Cause:** when `NickHub.exe` was missing, the black window flashed and closed before anyone could read why. The exe goes missing when the zip isn't extracted first, or when Windows Defender has removed it.

**Fix:** the test now stays open and explains what's wrong. The batch file is built into each racer's zip, so a re-sent zip has the fix without a new release.

## v3.0.0 (Nov 4): /played is automatic again

**Fix:** v2.5.0 asked for /played only when you typed `/nh`, because we wrongly blamed the "blocked" popup on the automatic /played request. That request works on Forever, so it's back after login and each level-up. Nobody has to remember to type `/nh` after logging in.

## v2.5.0 (Nov 4): the "blocked from an action" popup is gone

**Issue:** every login and `/reload`, Blizzard's own included, showed "NickHubTracker has been blocked from an action only available to the Blizzard UI", naming `UNKNOWN()`.

**Cause:** the addon registered for the combat log as it loaded. On Forever that counts as a forbidden action.

**Fix:** the addon doesn't register for the combat log on Forever. Getting here took three tries. The first two moved the addon's /played handling, and wrongly blamed it. The combat log turned out to be the cause once Blizzard's plain `/reload` showed the popup too.

## v2.4.0 (Nov 4): kills are counted on Forever

**Issue:** kills stayed at 0 even after finishing a kill quest, and "Kills by creature type" and "Most-killed mobs" were empty.

**Cause:** the addon counted kills from the combat log, which Forever doesn't give addons.

**Fix:** each "X dies, you gain N experience" message becomes a kill. The mob's type and level come from the last time you targeted it.

## Site: your own uploads crashed the Worker (Nov 4)

**Issue:** the uploader showed `HTTP 500 error code: 1101`.

**Cause:** a bug in the v2.3.0 name-matching change. The admin password isn't tied to a character, and the new check read the character name before checking for admin.

**Fix:** the check tests for admin first. Racers' uploads weren't affected.

## v2.3.0 (Nov 4): uploads matched by first name

**Issue:** the uploader said `uploaded — no characters` after a `/nh sync`.

**Cause:** Forever's first-name-only names (see v3.1.0) meant the saved character was `…-Shrim`, so a filter set to "Shrim Pina" skipped it.

**Fix:** a stopgap that matched first names too. v3.1.0 replaced it with full names.

## v2.2.0 (Nov 4): the addon loads on Forever

**Issue:** the AddOn list showed **Incompatible**, even with "Load out of date AddOns" ticked.

**Cause:** the `.toc` only listed the Classic Era and TBC interface numbers. Forever is 1.60.1, which is interface 16001 (1×10000 + 60×100 + 1). "Load out of date" can't override a number the client doesn't recognise at all.

**Fix:** the `.toc` lists 16000–16005, covering launch-day patches.

## v2.1.0 (Nov 3): a setup test before launch

**Added:** `Test my setup.bat` in each racer's zip, and `uploader\test_setup.bat` for the Python uploader. The test checks the password with an empty upload, finds WoW Forever and installs the addon, then lists anything to fix.

## v2.0.0 (Nov 3): the racer app

**Added:**
- **`NickHub.exe`,** a double-click app that finds WoW, installs and updates the addon, and uploads.
- **Personal zips:** `racers.py` packages each racer's app with their config.
- **Race backend:** a password for each racer that can only update their own character.
- **Leaderboard:** the home page, with a profile page for each racer.

## v1.0.0 (Nov 3): the addon

**Added:** the first release of the addon on its own.

## Before launch (Nov 1–3)

The addon, the uploader and nickhub.com were built and tested on TBC Anniversary. That covers the dashboard, the launch countdown, the How it works pages, the favicon and logo, and light and dark themes. The simulator in `tools/` runs the real addon against a fake WoW API. It now covers each Forever difference above: `NO_CLEU=1` for no combat log and first-name-only names, and `SECRETS=1` for hidden enemy details.

---

## Adding an entry

Add new entries at the top, below the known issues, in this shape:

```markdown
## vX.Y.Z (date): what changed, in a few words

**Issue:** what people saw.

**Cause:** why it happened.

**Fix:** what changed, and anything racers need to do.
```

Move a known issue into an entry once it's fixed.
