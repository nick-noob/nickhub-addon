"""Run the addon against a mocked WoW API, then parse the output with the uploader's parser."""
import json, os, sys
from lupa import LuaRuntime

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(root, "uploader"))
import nickhub_uploader as up

target = int(sys.argv[1]) if len(sys.argv) > 1 else 60
out_sv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "tools", "NickHubTracker.lua")

lua = LuaRuntime(unpack_returned_tuples=True)
g = lua.globals()
g.ADDON_PATH = os.path.join(root, "addon", "NickHubTracker", "NickHubTracker.lua")
g.OUT_PATH = out_sv
g.TARGET_LEVEL = target
g.SEED = 7
g.NO_CLEU = os.environ.get("NO_CLEU") == "1"  # simulate a client that hides the combat log
lua.execute(open(os.path.join(root, "tools", "sim.lua")).read())
res = g.RESULT
print("sim played:", res.played, "| /played chat lines:", res.playedPrinted, "| blocked calls:", res.forbidden, "| sync popups:", res.popups)

payload = up.build_payload(out_sv)
c = next(iter(payload["chars"].values()))
kills = c["kills"]
print("without played: kills", sum(1 for k in kills if k.get("p") is None), "| levels", sum(1 for v in c["levels"].values() if v.get("p") is None))
print("level", c["level"], "| played", c.get("played"), "| kills", len(kills), "| with xp", sum(1 for k in kills if "x" in k))
print("quests", len(c["quests"]), "titled", sum(1 for q in c["quests"] if q.get("title")), "| deaths", len(c["deaths"]), "| pet deaths", c["petDeaths"])
print("levels logged", len(c["levels"]), "keys sample", list(c["levels"])[:3], "| npcs", len(c["npcs"]))
print("npc sample", next(iter(c["npcs"].items())))
print("xpGained", c["xpGained"], "| zones", [z["z"] for z in c["zones"]][:4])
print("death sample", c["deaths"][0] if c["deaths"] else None)
json.dump(payload, open(os.path.join(root, "tools", "sample.json"), "w"), separators=(",", ":"))
print("json KB", os.path.getsize(os.path.join(root, "tools", "sample.json")) // 1024, "| SV KB", os.path.getsize(out_sv) // 1024)
