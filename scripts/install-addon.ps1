# Installs the NickHubTracker addon into a WoW folder on Windows.
#
# By default it creates a directory junction (no admin needed), so after a
# `git pull` the updated addon is live on your next /reload — nothing to copy.
#
#   .\scripts\install-addon.ps1                       # TBC Anniversary (_anniversary_)
#   .\scripts\install-addon.ps1 -Flavor _forever_     # WoW Forever (check the folder name)
#   .\scripts\install-addon.ps1 -Copy                 # copy instead of linking
#   .\scripts\install-addon.ps1 -WowDir "D:\Games\World of Warcraft"

param(
  [string]$Flavor = "_anniversary_",
  [string]$WowDir = "C:\Program Files (x86)\World of Warcraft",
  [switch]$Copy
)
$ErrorActionPreference = "Stop"

$src = (Resolve-Path (Join-Path $PSScriptRoot "..\addon\NickHubTracker")).Path
$game = Join-Path $WowDir $Flavor
if (-not (Test-Path $game)) {
  Write-Host "Can't find $game" -ForegroundColor Red
  if (Test-Path $WowDir) {
    Write-Host "Game folders in ${WowDir}:"
    Get-ChildItem $WowDir -Directory | Where-Object Name -like "_*_" | ForEach-Object { "  " + $_.Name }
  } else {
    Write-Host "WoW isn't at $WowDir. Pass -WowDir with the right location."
  }
  exit 1
}

$addons = Join-Path $game "Interface\AddOns"
New-Item -ItemType Directory -Force -Path $addons | Out-Null
$dest = Join-Path $addons "NickHubTracker"

if (Test-Path $dest) {
  $item = Get-Item $dest -Force
  if ($item.LinkType) { $item.Delete() } else { Remove-Item $dest -Recurse -Force }
  Write-Host "Replaced existing NickHubTracker"
}

if ($Copy) {
  Copy-Item $src $dest -Recurse
  Write-Host "Copied addon to $dest (run this again after each git pull)" -ForegroundColor Green
} else {
  New-Item -ItemType Junction -Path $dest -Target $src | Out-Null
  Write-Host "Linked $dest -> $src" -ForegroundColor Green
  Write-Host "After a git pull, /reload in game to pick up changes."
}
