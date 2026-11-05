-- NickHub Tracker
-- Logs leveling progress to SavedVariables so the uploader can push it to nickhub.com.
-- SavedVariables are only written to disk on /reload, logout, or exit. Use /nh sync.

local ADDON = ...
local VERSION = 1

local f = CreateFrame("Frame")
local db, char
local playerGUID, playerName

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------
local function now() return GetServerTime and GetServerTime() or time() end

local playedBase, playedAt -- seconds /played, GetTime() when received
local function played()
  if not playedBase then return nil end
  return math.floor(playedBase + (GetTime() - playedAt))
end

local function zone()
  local z = GetRealZoneText and GetRealZoneText() or nil
  if z == "" then z = nil end
  return z
end

local function msg(text)
  DEFAULT_CHAT_FRAME:AddMessage("|cff4fc3f7NickHub|r " .. text)
end

-- "Creature-0-1234-0-56-1234-0000ABCD" -> "1234"
local function npcKey(guid)
  if not guid then return nil end
  local unitType, _, _, _, _, id = strsplit("-", guid)
  if unitType == "Creature" or unitType == "Vehicle" then return id end
  return nil
end

local function isMine(flags)
  return flags and bit.band(flags, COMBATLOG_OBJECT_AFFILIATION_MINE or 0x1) > 0
end

-- Turn a localized format string ("%s dies, you gain %d experience.") into a Lua pattern
local function fmtToPattern(fmt)
  if not fmt then return nil end
  local p = fmt:gsub("([%%%(%)%.%+%-%*%?%[%]%^%$])", "%%%1")
  p = p:gsub("%%%%s", "(.-)"):gsub("%%%%d", "(%%d+)")
  return "^" .. p
end

---------------------------------------------------------------------------
-- Character record
---------------------------------------------------------------------------
local function initChar()
  NickHubTrackerDB = NickHubTrackerDB or {}
  db = NickHubTrackerDB
  db.version = VERSION
  db.chars = db.chars or {}
  db.settings = db.settings or { autoSync = false }

  playerName = UnitName("player")
  local realm = GetRealmName()
  local key = realm .. "-" .. playerName
  db.chars[key] = db.chars[key] or {}
  char = db.chars[key]

  local _, class = UnitClass("player")
  local _, race = UnitRace("player")
  char.name, char.realm, char.class, char.race = playerName, realm, class, race
  char.faction = UnitFactionGroup("player")
  char.startedAt = char.startedAt or now()
  char.levels = char.levels or {}
  char.kills = char.kills or {}
  char.npcs = char.npcs or {}
  char.quests = char.quests or {}
  char.accepted = char.accepted or {}
  char.deaths = char.deaths or {}
  char.zones = char.zones or {}
  char.sessions = char.sessions or {}
  char.xpGained = char.xpGained or { total = 0, mob = 0, quest = 0 }
  char.petDeaths = char.petDeaths or 0

  local lvl = UnitLevel("player")
  if not char.levels[lvl] and next(char.levels) == nil then
    -- first time we've seen this character: record its starting level
    char.levels[lvl] = { t = now(), z = zone(), m = GetMoney() }
  end
  char.firstLevel = char.firstLevel or lvl

  table.insert(char.sessions, { s = now() })
end

local function snapshot()
  if not char then return end
  char.level = UnitLevel("player")
  char.xp = UnitXP("player")
  char.xpMax = UnitXPMax("player")
  char.rested = GetXPExhaustion() or 0
  char.money = GetMoney()
  char.zone = zone()
  char.updatedAt = now()
  if playedBase then char.played, char.playedAt = played(), now() end
  local s = char.sessions[#char.sessions]
  if s then s.e = now() end
end

---------------------------------------------------------------------------
-- /played
---------------------------------------------------------------------------
-- WoW Forever blocks an addon asking for /played outside a keypress, so the addon asks only
-- from /nh and otherwise listens for the player's own /played (TIME_PLAYED_MSG)

-- a /reload (such as /nh sync) saved /played moments ago, so carry it over instead of asking
local function restorePlayed()
  local gap = char.playedAt and (now() - char.playedAt)
  if char.played and gap and gap >= 0 and gap < 60 then
    playedBase, playedAt = char.played + gap, GetTime()
  end
end

---------------------------------------------------------------------------
-- Kill tracking
---------------------------------------------------------------------------
local tagged = {}     -- guid -> { name, t } mobs damaged by me or my pet
local guidLevel = {}  -- guid -> mob level (seen via target/mouseover/nameplate)
local levelByName = {} -- mob name -> last level seen, for kills known only by name
local pendingXP = {}  -- xp messages that arrived before the death event
local lastAttacker
local XP_PATTERN = fmtToPattern(COMBATLOG_XPGAIN_FIRSTPERSON)
local XP_PATTERN_UNNAMED = fmtToPattern(COMBATLOG_XPGAIN_FIRSTPERSON_UNNAMED)

local function learnUnit(unit)
  if not UnitExists(unit) or UnitIsPlayer(unit) then return end
  local guid = UnitGUID(unit)
  local k = npcKey(guid)
  if not k then return end
  local lvl = UnitLevel(unit)
  guidLevel[guid] = lvl
  levelByName[UnitName(unit) or ""] = lvl
  local n = char.npcs[k] or { n = UnitName(unit), c = 0 }
  n.n = UnitName(unit) or n.n
  n.type = UnitCreatureType(unit) or n.type
  n.cl = UnitClassification(unit) or n.cl
  if lvl and lvl > 0 then
    n.minL = math.min(n.minL or lvl, lvl)
    n.maxL = math.max(n.maxL or lvl, lvl)
  end
  char.npcs[k] = n
end

-- a mob seen by targeting, so a kill known only by name still gets its type and level
local function npcKeyByName(name)
  local any
  for k, n in pairs(char.npcs) do
    if n.n == name then
      if n.type then return k end
      any = any or k
    end
  end
  return any or ("name:" .. (name or "?"))
end

local function recordKill(guid, name)
  local k = npcKey(guid) or npcKeyByName(name)
  local n = char.npcs[k] or { n = name, c = 0 }
  n.n = n.n or name
  n.c = (n.c or 0) + 1
  char.npcs[k] = n

  local kill = { t = now(), p = played(), k = k, l = (guid and guidLevel[guid]) or levelByName[name], lv = UnitLevel("player"), z = zone() }
  -- XP message may have arrived just before the death event
  for i = #pendingXP, 1, -1 do
    local px = pendingXP[i]
    if px.name == name and GetTime() - px.at < 3 then
      kill.x = px.xp
      table.remove(pendingXP, i)
      break
    end
  end
  table.insert(char.kills, kill)
  if guid then tagged[guid] = nil; guidLevel[guid] = nil end
  return kill
end

local DAMAGE = {
  SWING_DAMAGE = true, RANGE_DAMAGE = true, SPELL_DAMAGE = true,
  SPELL_PERIODIC_DAMAGE = true, DAMAGE_SHIELD = true, ENVIRONMENTAL_DAMAGE = true,
}

local function onCombatLog()
  local _, sub, _, srcGUID, srcName, srcFlags, _, dstGUID, dstName = CombatLogGetCurrentEventInfo()

  if sub == "UNIT_DIED" then
    if tagged[dstGUID] then
      recordKill(dstGUID, tagged[dstGUID].name or dstName)
    elseif UnitGUID("pet") and dstGUID == UnitGUID("pet") then
      char.petDeaths = (char.petDeaths or 0) + 1
    end
    return
  end

  if dstGUID == playerGUID and DAMAGE[sub] then
    if sub == "ENVIRONMENTAL_DAMAGE" then
      local envType = select(12, CombatLogGetCurrentEventInfo())
      lastAttacker = envType and ("Environment: " .. envType) or "Environment"
    else
      lastAttacker = srcName
    end
    return
  end

  -- anything I (or my pet) do to an NPC marks it as "mine"
  if isMine(srcFlags) and npcKey(dstGUID) and (DAMAGE[sub] or sub:find("^SPELL_AURA_APPLIED")) then
    if not tagged[dstGUID] then tagged[dstGUID] = { name = dstName, t = GetTime() } end
  end
end

local function onXPMessage(text)
  local name, xp = nil, nil
  if XP_PATTERN then name, xp = text:match(XP_PATTERN) end
  if not xp then return end -- unnamed/exploration gains are counted via PLAYER_XP_UPDATE
  xp = tonumber(xp)
  char.xpGained.mob = char.xpGained.mob + xp
  -- attach to the matching kill if it's already recorded
  for i = #char.kills, math.max(1, #char.kills - 5), -1 do
    local kill = char.kills[i]
    local n = char.npcs[kill.k]
    if not kill.x and n and n.n == name and now() - kill.t <= 3 then
      kill.x = xp
      return
    end
  end
  local px = { name = name, xp = xp, at = GetTime() }
  table.insert(pendingXP, px)
  -- the combat log normally claims this within a moment. WoW Forever doesn't give addons the
  -- combat log, so if nothing claims it, the XP message itself is the kill
  C_Timer.After(1, function()
    for i = #pendingXP, 1, -1 do
      if pendingXP[i] == px then
        table.remove(pendingXP, i)
        recordKill(nil, name).x = xp
        return
      end
    end
  end)
end

-- clean up stale tags every minute so the table doesn't grow forever
local function sweep()
  local cutoff = GetTime() - 300
  for g, v in pairs(tagged) do if v.t < cutoff then tagged[g] = nil; guidLevel[g] = nil end end
  for i = #pendingXP, 1, -1 do if GetTime() - pendingXP[i].at > 10 then table.remove(pendingXP, i) end end
  C_Timer.After(60, sweep)
end

---------------------------------------------------------------------------
-- XP accounting
---------------------------------------------------------------------------
local lastXP, lastMax, lastLvl
local function onXPUpdate()
  local xp, max, lvl = UnitXP("player"), UnitXPMax("player"), UnitLevel("player")
  if lastXP then
    local delta
    if lvl == lastLvl then delta = xp - lastXP
    elseif lvl > lastLvl then delta = (lastMax - lastXP) + xp end
    if delta and delta > 0 then char.xpGained.total = char.xpGained.total + delta end
  end
  lastXP, lastMax, lastLvl = xp, max, lvl
end

---------------------------------------------------------------------------
-- Quests
---------------------------------------------------------------------------
local pendingTitle
local function questTitle(id)
  if pendingTitle and pendingTitle.id == id then return pendingTitle.title end
  if C_QuestLog and C_QuestLog.GetQuestInfo then
    local ok, t = pcall(C_QuestLog.GetQuestInfo, id)
    if ok and type(t) == "string" then return t end
    if ok and type(t) == "table" then return t.title end
  end
  if C_QuestLog and C_QuestLog.GetTitleForQuestID then
    local ok, t = pcall(C_QuestLog.GetTitleForQuestID, id)
    if ok and t then return t end
  end
  if pendingTitle then return pendingTitle.title end
  return nil
end

local function onQuestTurnedIn(id, xp, money)
  local title = questTitle(id)
  local acc = char.accepted[id]
  table.insert(char.quests, {
    t = now(), p = played(), id = id, title = title or (acc and acc.title),
    x = xp or 0, m = money or 0, lv = UnitLevel("player"), z = zone(),
    a = acc and acc.t or nil,
  })
  char.accepted[id] = nil
  char.xpGained.quest = char.xpGained.quest + (xp or 0)
  pendingTitle = nil
end

local function onQuestAccepted(a1, a2)
  -- Classic clients pass (questLogIndex, questID); modern passes (questID)
  local id = a2 or a1
  local title
  if a2 and GetQuestLogTitle then title = GetQuestLogTitle(a1) end
  title = title or questTitle(id)
  char.accepted[id] = { t = now(), title = title, lv = UnitLevel("player") }
end

---------------------------------------------------------------------------
-- Level ups, deaths, zones
---------------------------------------------------------------------------
local wantSync = false
local trySync -- defined below

local function onLevelUp(level)
  char.levels[level] = { t = now(), p = played(), z = zone(), m = GetMoney() }
  msg(("Level %d logged%s. Type |cffffff00/nh sync|r to push it to nickhub.com."):format(
    level, played() and (" at " .. SecondsToTime(played())) or ""))
  if db.settings.autoSync then C_Timer.After(3, function() trySync(false) end) end
end

StaticPopupDialogs["NICKHUB_SYNC"] = {
  text = "NickHub: level %s logged.\nReload now to sync it to nickhub.com?",
  button1 = "Sync", button2 = "Later",
  OnAccept = function() snapshot(); ReloadUI() end,
  timeout = 30, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}

function trySync(fromSlash)
  if InCombatLockdown() or UnitAffectingCombat("player") then
    wantSync = true
    if fromSlash then msg("in combat — will ask again when combat ends.") end
    return
  end
  wantSync = false
  if fromSlash then
    snapshot()
    ReloadUI()
  else
    StaticPopup_Show("NICKHUB_SYNC", UnitLevel("player"))
  end
end

local function onDeath()
  table.insert(char.deaths, { t = now(), p = played(), z = zone(), lv = UnitLevel("player"), by = lastAttacker })
end

local function onZoneChange()
  local z = zone()
  local last = char.zones[#char.zones]
  if z and (not last or last.z ~= z) then
    table.insert(char.zones, { t = now(), p = played(), z = z, lv = UnitLevel("player") })
  end
end

---------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------
local handlers = {}

function handlers.PLAYER_LOGIN()
  playerGUID = UnitGUID("player")
  initChar()
  lastXP, lastMax, lastLvl = UnitXP("player"), UnitXPMax("player"), UnitLevel("player")
  onZoneChange()
  restorePlayed()
  snapshot()
  C_Timer.After(60, sweep)
  msg(("tracking %s (level %d). |cffffff00/nh|r for status."):format(playerName, UnitLevel("player")))
  if not playedBase then msg("type |cffffff00/nh|r or /played once so your levels get a time played.") end
end

function handlers.PLAYER_LOGOUT() snapshot() end

function handlers.TIME_PLAYED_MSG(total)
  playedBase, playedAt = total, GetTime()
  char.played = total
  -- backfill any level entry recorded before /played was known
  local lvl = char.levels[UnitLevel("player")]
  if lvl and not lvl.p and now() - lvl.t < 120 then lvl.p = math.max(0, total - (now() - lvl.t)) end
  local z = char.zones[#char.zones]
  if z and not z.p then z.p = math.max(0, total - (now() - z.t)) end
end

function handlers.PLAYER_LEVEL_UP(level) onLevelUp(level) end
function handlers.PLAYER_XP_UPDATE() onXPUpdate() end
function handlers.COMBAT_LOG_EVENT_UNFILTERED() pcall(onCombatLog) end -- a client that hides the log shouldn't spam errors
function handlers.CHAT_MSG_COMBAT_XP_GAIN(text) onXPMessage(text) end
function handlers.QUEST_COMPLETE()
  pendingTitle = { title = GetTitleText and GetTitleText() or nil, id = GetQuestID and GetQuestID() or nil }
end
function handlers.QUEST_TURNED_IN(id, xp, money) onQuestTurnedIn(id, xp, money) end
function handlers.QUEST_ACCEPTED(a1, a2) onQuestAccepted(a1, a2) end
function handlers.PLAYER_DEAD() onDeath() end
function handlers.ZONE_CHANGED_NEW_AREA() onZoneChange() end
function handlers.PLAYER_TARGET_CHANGED() learnUnit("target") end
function handlers.UPDATE_MOUSEOVER_UNIT() learnUnit("mouseover") end
function handlers.NAME_PLATE_UNIT_ADDED(unit) learnUnit(unit) end
function handlers.PLAYER_REGEN_ENABLED() if wantSync then C_Timer.After(1, function() trySync(false) end) end end
function handlers.PLAYER_MONEY() if char then char.money = GetMoney() end end
-- WoW names the function it blocked, so say which one instead of only showing its popup
local function onBlocked(addon, fn)
  if addon ~= ADDON then return end
  msg(("WoW blocked a call to %s. Tell Nick."):format(tostring(fn)))
  if NickHubTrackerDB then NickHubTrackerDB.blocked = { fn = tostring(fn), t = now() } end
end
handlers.ADDON_ACTION_FORBIDDEN = onBlocked
handlers.ADDON_ACTION_BLOCKED = onBlocked

f:SetScript("OnEvent", function(_, event, ...)
  local h = handlers[event]
  if event ~= "PLAYER_LOGIN" and not char and h ~= onBlocked then return end
  if h then h(...) end
end)
-- WoW Forever (interface 16000+) treats registering for the combat log as a forbidden action and
-- shows a "blocked from an action" popup on every load, so skip it there; kills come from XP messages
local interface = select(4, GetBuildInfo()) or 0
local noCombatLog = interface >= 16000 and interface < 20000
for event in pairs(handlers) do
  if not (noCombatLog and event == "COMBAT_LOG_EVENT_UNFILTERED") then
    pcall(f.RegisterEvent, f, event) -- ignore events a client doesn't have
  end
end

---------------------------------------------------------------------------
-- Slash commands
---------------------------------------------------------------------------
SLASH_NICKHUB1 = "/nh"
SLASH_NICKHUB2 = "/nickhub"
SlashCmdList.NICKHUB = function(input)
  local cmd, arg = (input or ""):lower():match("^(%S*)%s*(.-)$")
  if cmd == "sync" then
    msg("saving… (reloading UI)")
    trySync(true)
  elseif cmd == "auto" then
    db.settings.autoSync = (arg == "on")
    msg("sync prompt on level up: " .. (db.settings.autoSync and "|cff00ff00on|r" or "|cffff5555off|r"))
  elseif cmd == "reset" then
    if arg == "confirm" then
      local key = char.realm .. "-" .. char.name
      db.chars[key] = nil
      initChar()
      msg("data for this character wiped.")
    else
      msg("this wipes everything logged for this character. Type |cffffff00/nh reset confirm|r to do it.")
    end
  else
    if not playedBase then RequestTimePlayed() end
    snapshot()
    local kills = #char.kills
    local quests = #char.quests
    msg(("Lvl %d | %s played | %d kills | %d quests | %d deaths | auto-sync %s"):format(
      char.level, char.played and SecondsToTime(char.played) or "?", kills, quests, #char.deaths,
      db.settings.autoSync and "on" or "off"))
    msg("/nh sync — save now   /nh auto on|off — offer a sync after each level   /nh reset")
  end
end
