-- Test harness: runs NickHubTracker.lua against a mocked WoW API and simulates a 1-60 run.
-- Usage (via lupa in tools/run_sim.py). Writes a WoW-style SavedVariables file.

math.randomseed(SEED or 42)

-- ---------- clock ----------
local clock = 0            -- GetTime()
local server0 = 1793836800 -- 2026-11-04 23:00 UTC (3pm PT launch)
local playedTotal = 0
function GetTime() return clock end
function GetServerTime() return server0 + math.floor(clock) end
time = function() return GetServerTime() end
local timers = {}
C_Timer = { After = function(d, fn) table.insert(timers, { at = clock + d, fn = fn }) end }
local function advance(dt)
  local target = clock + dt
  while true do
    local best, bi
    for i, t in ipairs(timers) do if t.at <= target and (not best or t.at < best.at) then best, bi = t, i end end
    if not best then break end
    table.remove(timers, bi)
    if best.at > clock then playedTotal = playedTotal + (best.at - clock); clock = best.at end
    best.fn()
  end
  playedTotal = playedTotal + (target - clock)
  clock = target
end

-- ---------- lua 5.1 compat ----------
bit = { band = function(a, b) return a & b end }
function strsplit(sep, s)
  local out = {}
  for part in (s .. sep):gmatch("(.-)" .. sep:gsub("%p", "%%%0")) do out[#out + 1] = part end
  return table.unpack(out)
end
unpack = table.unpack

-- ---------- player state ----------
local P = { level = 1, xp = 0, money = 0, zone = "Durotar", combat = false }
local XPMAX = {}
for l = 1, 60 do XPMAX[l] = math.floor(400 + (l - 1) * 180 + (l ^ 2.35) * 9) end
local PLAYER_GUID = "Player-4395-0A1B2C3D"
local PET_GUID = "Pet-0-4395-0-1-1234-0100ABCD"

function UnitName(u) if u == "player" then return "Shrim Pina" end return units[u] and units[u].name end
function GetRealmName() return "Forever" end
function UnitClass() return "Hunter", "HUNTER" end
function UnitRace() return "Orc", "Orc" end
function UnitFactionGroup() return "Horde" end
function UnitLevel(u) if u == "player" then return P.level end return units[u] and units[u].level end
function UnitXP() return P.xp end
function UnitXPMax() return XPMAX[P.level] or 0 end
function GetXPExhaustion() return 0 end
function GetMoney() return P.money end
function GetRealZoneText() return P.zone end
function InCombatLockdown() return P.combat end
function UnitAffectingCombat() return P.combat end
units = {}
function UnitExists(u) return units[u] ~= nil end
function UnitIsPlayer() return false end
function UnitGUID(u)
  if u == "player" then return PLAYER_GUID elseif u == "pet" then return PET_GUID end
  return units[u] and units[u].guid
end
function UnitCreatureType(u) return units[u] and units[u].ctype end
function UnitClassification(u) return units[u] and units[u].class or "normal" end
function SecondsToTime(s) return string.format("%dh %dm", s // 3600, (s % 3600) // 60) end

COMBATLOG_OBJECT_AFFILIATION_MINE = 0x1
COMBATLOG_XPGAIN_FIRSTPERSON = "%s dies, you gain %d experience."
COMBATLOG_XPGAIN_FIRSTPERSON_UNNAMED = "You gain %d experience."
DEFAULT_CHAT_FRAME = { AddMessage = function(_, t) if VERBOSE then print("[chat] " .. t) end end }
local playedPrinted = 0
function ChatFrame_DisplayTimePlayed() playedPrinted = playedPrinted + 1 end
StaticPopupDialogs = {}
local popups = 0
function StaticPopup_Show() popups = popups + 1 end
function ReloadUI() end
SlashCmdList = {}
local questTitle
function GetTitleText() return questTitle end
function GetQuestID() return nil end
function GetQuestLogTitle(i) return questTitle end

-- ---------- events ----------
local forbidden = 0
function GetBuildInfo() return "1.60.1", "70755", "Nov 2 2026", NO_CLEU and 16001 or 11508 end
local frame
local cleu
function CombatLogGetCurrentEventInfo() return table.unpack(cleu, 1, 15) end
function CreateFrame()
  frame = { events = {} }
  function frame:SetScript(_, fn) self.fn = fn end
  function frame:RegisterEvent(e)
    if NO_CLEU and e == "COMBAT_LOG_EVENT_UNFILTERED" then forbidden = forbidden + 1; return end -- like WoW Forever
    self.events[e] = true
  end
  return frame
end
local function fire(e, ...) if frame.events[e] then frame.fn(frame, e, ...) end end
-- like WoW Forever, /played can only be asked for right after a keypress
local keypress = false
function RequestTimePlayed()
  if not keypress then forbidden = forbidden + 1; fire("ADDON_ACTION_FORBIDDEN", "NickHubTracker", "UNKNOWN()"); return end
  C_Timer.After(0.2, function() fire("TIME_PLAYED_MSG", math.floor(playedTotal), 0); ChatFrame_DisplayTimePlayed() end)
end
local function typeSlash(cmd) keypress = true; SlashCmdList.NICKHUB(cmd); keypress = false end

-- ---------- load addon ----------
local chunk = assert(loadfile(ADDON_PATH))
local function login()
  chunk("NickHubTracker", {})
  fire("PLAYER_LOGIN")
  advance(5)
end
login()
typeSlash("") -- the player checks /nh once, which learns /played

-- ---------- world data ----------
local ZONES = {
  { 1, "Durotar", { { "Mottled Boar", "Beast" }, { "Vile Familiar", "Demon" }, { "Scorpid Worker", "Beast" }, { "Razormane Quilboar", "Humanoid" } } },
  { 10, "The Barrens", { { "Zhevra Runner", "Beast" }, { "Sunscale Lashtail", "Beast" }, { "Razormane Thornweaver", "Humanoid" }, { "Kolkar Bloodcharger", "Humanoid" } } },
  { 18, "Stonetalon Mountains", { { "Venture Co. Logger", "Humanoid" }, { "Deepmoss Creeper", "Beast" }, { "Bloodfury Roguefeather", "Humanoid" }, { "Venture Co. Operator", "Mechanical" } } },
  { 21, "Ashenvale", { { "Ghostpaw Runner", "Beast" }, { "Thistlefur Avenger", "Humanoid" }, { "Foulweald Warrior", "Humanoid" }, { "Befouled Water Elemental", "Elemental" } } },
  { 28, "Thousand Needles", { { "Galak Scout", "Humanoid" }, { "Highperch Wyvern", "Beast" }, { "Grimtotem Geomancer", "Humanoid" }, { "Sparkleshell Tortoise", "Beast" } } },
  { 32, "Stranglethorn Vale", { { "Young Stranglethorn Tiger", "Beast" }, { "Kurzen Jungle Fighter", "Humanoid" }, { "Bloodscalp Warrior", "Humanoid" }, { "Jungle Stalker", "Beast" } } },
  { 38, "Arathi Highlands", { { "Witherbark Troll", "Humanoid" }, { "Highland Thrasher", "Beast" }, { "Boulderfist Ogre", "Giant" }, { "Feral Mountain Lion", "Beast" } } },
  { 42, "Tanaris", { { "Wastewander Bandit", "Humanoid" }, { "Sandfury Hideskinner", "Humanoid" }, { "Scorpid Reaver", "Beast" }, { "Dunemaul Ogre", "Giant" } } },
  { 48, "Feralas", { { "Gordunni Ogre", "Giant" }, { "Frayfeather Skystormer", "Beast" }, { "Grimtotem Raider", "Humanoid" }, { "Ironfur Bear", "Beast" } } },
  { 51, "Un'Goro Crater", { { "Stegodon", "Beast" }, { "Gorilla", "Beast" }, { "Glutinous Ooze", "Elemental" }, { "Ravasaur Runner", "Beast" } } },
  { 54, "Felwood", { { "Deadwood Warrior", "Humanoid" }, { "Toxic Horror", "Elemental" }, { "Entropic Beast", "Elemental" }, { "Irontree Stomper", "Elemental" } } },
  { 56, "Winterspring", { { "Winterfall Shaman", "Humanoid" }, { "Frostsaber", "Beast" }, { "Ice Thistle Yeti", "Beast" }, { "Cobalt Wyrmkin", "Dragonkin" } } },
  { 58, "Eastern Plaguelands", { { "Plaguehound", "Undead" }, { "Cursed Mage", "Undead" }, { "Scourge Champion", "Undead" }, { "Plague Monstrosity", "Undead" } } },
}
local function zoneFor(level)
  local z = ZONES[1]
  for _, zz in ipairs(ZONES) do if level >= zz[1] then z = zz end end
  return z
end

local nextSpawn = 0x10000
local npcIdOf = {}
local function npcId(name)
  if not npcIdOf[name] then npcIdOf[name] = tostring(1000 + (#name * 37 + name:byte(1) * 11 + name:byte(-1)) % 9000) end
  return npcIdOf[name]
end

local function gainXP(amount)
  P.xp = P.xp + amount
  while P.level < 60 and P.xp >= XPMAX[P.level] do
    P.xp = P.xp - XPMAX[P.level]
    P.level = P.level + 1
    fire("PLAYER_XP_UPDATE", "player")
    fire("PLAYER_LEVEL_UP", P.level)
  end
  if P.level >= 60 then P.xp = 0 end
  fire("PLAYER_XP_UPDATE", "player")
end

local function killMob()
  local z = zoneFor(P.level)
  local mob = z[3][math.random(#z[3])]
  nextSpawn = nextSpawn + 1
  local guid = ("Creature-0-4395-0-12-%s-%08X"):format(npcId(mob[1]), nextSpawn)
  local mlvl = math.max(1, P.level + math.random(-2, 1))
  units.target = { name = mob[1], guid = guid, level = mlvl, ctype = mob[2], class = (math.random() < 0.03) and "elite" or "normal" }
  fire("PLAYER_TARGET_CHANGED")
  P.combat = true
  local petBlow = math.random() < 0.45
  cleu = { 0, "RANGE_DAMAGE", false, PLAYER_GUID, "Shrim Pina", 0x511, 0, guid, mob[1], 0xa48, 0 }
  fire("COMBAT_LOG_EVENT_UNFILTERED")
  if petBlow then
    cleu = { 0, "SWING_DAMAGE", false, PET_GUID, "Bruno", 0x1111, 0, guid, mob[1], 0xa48, 0 }
    fire("COMBAT_LOG_EVENT_UNFILTERED")
  end
  cleu = { 0, "SWING_DAMAGE", false, guid, mob[1], 0xa48, 0, PLAYER_GUID, "Shrim Pina", 0x511, 0 }
  fire("COMBAT_LOG_EVENT_UNFILTERED")
  advance(math.random(8, 20))
  local xp = math.floor((P.level * 5 + 45) * (1 + (mlvl - P.level) * 0.05))
  local xpFirst = math.random() < 0.5
  if xpFirst then fire("CHAT_MSG_COMBAT_XP_GAIN", ("%s dies, you gain %d experience."):format(mob[1], xp)) end
  cleu = { 0, "UNIT_DIED", false, "", nil, 0x80000000, 0, guid, mob[1], 0xa48, 0 }
  fire("COMBAT_LOG_EVENT_UNFILTERED")
  if not xpFirst then fire("CHAT_MSG_COMBAT_XP_GAIN", ("%s dies, you gain %d experience."):format(mob[1], xp)) end
  gainXP(xp)
  P.money = P.money + math.random(0, P.level * 8)
  P.combat = false
  fire("PLAYER_REGEN_ENABLED")
  units.target = nil
  advance(math.random(10, 35))
end

local QWORDS = { "The Missing", "Bounty on", "Supplies for", "Report to", "Wanted:", "A Hunter's", "Cleansing the", "Trouble in", "Return to", "Ancient" }
local QNOUNS = { "Scouts", "Pelts", "Ogres", "Thane", "Watch", "Crate", "Relic", "Totem", "Expedition", "Grove", "Ridge", "Camp" }
local questId = 300
local function doQuest()
  questId = questId + 1
  questTitle = QWORDS[math.random(#QWORDS)] .. " " .. QNOUNS[math.random(#QNOUNS)]
  fire("QUEST_ACCEPTED", 1, questId)
  advance(math.random(60, 240))
  fire("QUEST_COMPLETE")
  local xp = math.floor((P.level * 26 + 90) * (0.8 + math.random() * 0.5))
  local money = P.level * math.random(20, 120)
  P.money = P.money + money
  fire("QUEST_TURNED_IN", questId, xp, money)
  gainXP(xp)
  advance(math.random(15, 60))
end

local function die()
  local z = zoneFor(P.level)
  local mob = z[3][math.random(#z[3])]
  cleu = { 0, "SWING_DAMAGE", false, "Creature-0-1-0-1-99-1", mob[1], 0xa48, 0, PLAYER_GUID, "Shrim Pina", 0x511, 0 }
  fire("COMBAT_LOG_EVENT_UNFILTERED")
  fire("PLAYER_DEAD")
  advance(math.random(60, 150))
end

-- ---------- simulate ----------
local targetLevel = TARGET_LEVEL or 60
local lastZone, reloaded
while P.level < targetLevel do
  if P.level >= 10 and not reloaded then -- /nh sync reloads the UI; /played should carry over
    typeSlash("sync"); advance(4); login(); reloaded = true
  end
  local z = zoneFor(P.level)
  if z[2] ~= lastZone then P.zone = z[2]; fire("ZONE_CHANGED_NEW_AREA"); lastZone = z[2]; advance(120) end
  local r = math.random()
  if r < 0.70 then killMob()
  elseif r < 0.985 then doQuest()
  else die() end
  if math.random() < 0.002 then
    cleu = { 0, "UNIT_DIED", false, "", nil, 0, 0, PET_GUID, "Bruno", 0x1111, 0 }
    fire("COMBAT_LOG_EVENT_UNFILTERED")
  end
end
advance(10)
fire("PLAYER_LOGOUT")
RESULT = { db = NickHubTrackerDB, playedPrinted = playedPrinted, popups = popups, played = math.floor(playedTotal), forbidden = forbidden }

-- ---------- WoW-style serializer ----------
local function key(k)
  if type(k) == "number" then return "[" .. k .. "]" end
  return ('["%s"]'):format(k)
end
local function val(v)
  if type(v) == "string" then return ('"%s"'):format(v:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub("\n", "\\n")) end
  return tostring(v)
end
local function ser(t, ind, out)
  local n = #t
  for i = 1, n do
    local v = t[i]
    if type(v) == "table" then
      out[#out + 1] = ind .. "{\n"; ser(v, ind .. "\t", out); out[#out + 1] = ind .. "}, -- [" .. i .. "]\n"
    else out[#out + 1] = ind .. val(v) .. ", -- [" .. i .. "]\n" end
  end
  local keys = {}
  for k in pairs(t) do if not (type(k) == "number" and k >= 1 and k <= n and k % 1 == 0) then keys[#keys + 1] = k end end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do
    local v = t[k]
    if type(v) == "table" then
      out[#out + 1] = ind .. key(k) .. " = {\n"; ser(v, ind .. "\t", out); out[#out + 1] = ind .. "},\n"
    else out[#out + 1] = ind .. key(k) .. " = " .. val(v) .. ",\n" end
  end
end
local out = { "\nNickHubTrackerDB = {\n" }
ser(NickHubTrackerDB, "\t", out)
out[#out + 1] = "}\n"
local fh = assert(io.open(OUT_PATH, "w"))
fh:write(table.concat(out))
fh:close()
