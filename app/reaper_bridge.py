"""Pont Sonothèque -> REAPER.

Lancer reaper.exe avec des fichiers en argument ouvre un nouveau projet.
On installe donc un petit ReaScript (Lua) qui démarre avec REAPER
(Scripts/__startup.lua) et surveille un fichier « boîte aux lettres ».
La Sonothèque y écrit les chemins à insérer ; le script les place au
curseur d'édition, sur la piste sélectionnée, dans le projet ouvert.
"""
import os
import subprocess
import sys
import time

MARK = "-- Sonotheque bridge"

LUA = r'''-- Sonothèque -> REAPER
-- Insère les sons envoyés par la Sonothèque au curseur d'édition,
-- sur la piste sélectionnée du projet en cours. Installé automatiquement.
local dir   = reaper.GetResourcePath() .. "/Scripts/Sonotheque/"
local INBOX = dir .. "inbox.txt"
local WORK  = dir .. "inbox.work"
local ALIVE = dir .. "alive.txt"
local SEC   = "Sonotheque"

-- une seule instance
local now = reaper.time_precise()
local beat = tonumber(reaper.GetExtState(SEC, "beat")) or -100
if now - beat < 2.5 then return end
reaper.SetExtState(SEC, "beat", tostring(now), false)

local function read_lines(p)
  local f = io.open(p, "rb")
  if not f then return {} end
  local s = f:read("a") or ""
  f:close()
  local t = {}
  for line in s:gmatch("[^\r\n]+") do t[#t + 1] = line end
  return t
end

local function items_of(track)
  local s = {}
  for i = 0, reaper.CountTrackMediaItems(track) - 1 do
    s[reaper.GetTrackMediaItem(track, i)] = true
  end
  return s
end

local function insert(paths)
  if #paths == 0 then return end
  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  local track = reaper.GetSelectedTrack(0, 0) or reaper.GetLastTouchedTrack()
  if not track then
    reaper.InsertTrackAtIndex(reaper.CountTracks(0), true)
    track = reaper.GetTrack(0, reaper.CountTracks(0) - 1)
  end
  reaper.SetOnlyTrackSelected(track)
  reaper.Main_OnCommand(40914, 0) -- piste sélectionnée = dernière touchée
  local idx = math.floor(reaper.GetMediaTrackInfo_Value(track, "IP_TRACKNUMBER")) - 1
  local pos = reaper.GetCursorPosition()
  reaper.Main_OnCommand(40289, 0) -- désélectionner les items
  local new = {}
  for _, p in ipairs(paths) do
    local before = items_of(track)
    reaper.SetEditCurPos(pos, false, false)
    reaper.InsertMedia(p, 512 | (idx << 16)) -- 512 : piste donnée par le mot haut
    for i = 0, reaper.CountTrackMediaItems(track) - 1 do
      local it = reaper.GetTrackMediaItem(track, i)
      if not before[it] then
        new[#new + 1] = it
        local e = reaper.GetMediaItemInfo_Value(it, "D_POSITION") + reaper.GetMediaItemInfo_Value(it, "D_LENGTH")
        if e > pos then pos = e end
      end
    end
  end
  for _, it in ipairs(new) do reaper.SetMediaItemSelected(it, true) end
  reaper.SetEditCurPos(pos, true, false) -- curseur après le dernier son (enchaîner)
  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock("Sonothèque : insérer " .. #new .. " son(s)", -1)
end

local last_poll, last_beat = 0, 0
local function loop()
  local t = reaper.time_precise()
  if t - last_poll > 0.12 then
    last_poll = t
    if os.rename(INBOX, WORK) then
      local paths = read_lines(WORK)
      os.remove(WORK)
      insert(paths)
    end
  end
  if t - last_beat > 1 then
    last_beat = t
    reaper.SetExtState(SEC, "beat", tostring(t), false)
    local f = io.open(ALIVE, "wb")
    if f then f:write(tostring(os.time())); f:close() end
  end
  reaper.defer(loop)
end
loop()
'''

STARTUP_LINE = ('dofile(reaper.GetResourcePath() .. "/Scripts/Sonotheque/sonotheque_bridge.lua") '
                + MARK + "\n")


def default_resource(exe):
    """Dossier de ressources REAPER (installation portable ou %APPDATA%\\REAPER)."""
    if exe:
        d = os.path.dirname(exe)
        if os.path.isfile(os.path.join(d, "reaper.ini")):
            return d
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "REAPER")


def bridge_dir(res):
    return os.path.join(res, "Scripts", "Sonotheque")


def is_installed(res):
    st = os.path.join(res, "Scripts", "__startup.lua")
    if not os.path.isfile(os.path.join(bridge_dir(res), "sonotheque_bridge.lua")) or not os.path.isfile(st):
        return False
    with open(st, encoding="utf-8", errors="ignore") as f:
        return MARK in f.read()


def install(res):
    d = bridge_dir(res)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "sonotheque_bridge.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write(LUA)
    st = os.path.join(res, "Scripts", "__startup.lua")
    old = ""
    if os.path.isfile(st):
        with open(st, encoding="utf-8", errors="ignore") as f:
            old = f.read()
    if MARK not in old:  # on ajoute sans toucher à un __startup.lua existant
        with open(st, "a", encoding="utf-8", newline="\n") as f:
            if old and not old.endswith("\n"):
                f.write("\n")
            f.write(STARTUP_LINE)


def alive(res):
    try:
        with open(os.path.join(bridge_dir(res), "alive.txt")) as f:
            return abs(time.time() - float(f.read().strip())) < 4
    except (OSError, ValueError):
        return False


def send(res, paths):
    d = bridge_dir(res)
    inbox = os.path.join(d, "inbox.txt")
    lines = []
    if os.path.exists(inbox):  # pas encore consommé : on cumule
        try:
            with open(inbox, encoding="utf-8") as f:
                lines = [l for l in f.read().splitlines() if l]
        except OSError:
            pass
    tmp = inbox + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines + list(paths)) + "\n")
    os.replace(tmp, inbox)


def clear_inbox(res):
    try:
        os.remove(os.path.join(bridge_dir(res), "inbox.txt"))
    except OSError:
        pass


def reaper_running():
    if not sys.platform.startswith("win"):
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq reaper.exe", "/NH"], capture_output=True,
                             text=True, creationflags=0x08000000, timeout=5).stdout
        return "reaper.exe" in out.lower()
    except Exception:
        return False
