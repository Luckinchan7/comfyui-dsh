# Install the dsh-comfy-models plugin into the active DSH profile.
#
#   powershell -ExecutionPolicy Bypass -File .\dsh\install-plugin.ps1
#   powershell -ExecutionPolicy Bypass -File .\dsh\install-plugin.ps1 -DryRun
#
# What it does, and why each step is needed:
#   1. copy plugin\  ->  <profile>\.local-packages\dsh-comfy-models\
#      (the "source of truth" copy that package.json points at)
#   2. copy the same files ->  <profile>\node_modules\dsh-comfy-models\
#      (what the runtime actually loads - file: deps are not always linked)
#   3. add the dependency to the profile's package.json
#   4. append a `- insert:` registration block to cordis.patch.yml
#      (a bare `- id: ...` line makes plugin-manager report unknown-plugin)
#
# Every step is idempotent and backs the file up before touching it.

param(
  [string]$ProfileDir = '',
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Pkg  = 'dsh-comfy-models'

function Info($m) { Write-Host "    ..   $m" -ForegroundColor DarkGray }
function Ok($m)   { Write-Host "    OK   $m" -ForegroundColor Green }
function Skip($m) { Write-Host "    --   $m" -ForegroundColor DarkGray }
function Warn($m) { Write-Host "    !!   $m" -ForegroundColor Yellow }

# Set-Content -Encoding utf8 in PowerShell 5.1 prepends a BOM, and Node refuses
# to parse a package.json that starts with one. Write UTF-8 without BOM instead.
function Write-TextNoBom($Path, $Text) {
  $enc = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

# ------------------------------------------------------------- locate profile
if (-not $ProfileDir) {
  $base = Join-Path $env:USERPROFILE '.dsh\profiles'
  if (-not (Test-Path $base)) { throw "no DSH profiles directory at $base - is DSH installed?" }
  # Prefer a profile that already has an image-gen entry; else the only one.
  $candidates = Get-ChildItem $base -Directory
  $withImageGen = $candidates | Where-Object {
    $y = Join-Path $_.FullName 'cordis.patch.yml'
    (Test-Path $y) -and (Select-String -Path $y -Pattern 'comfyuiWorkflows|dsh-image-gen' -Quiet)
  }
  if ($withImageGen) { $pick = $withImageGen | Select-Object -First 1 }
  elseif ($candidates.Count -eq 1) { $pick = $candidates[0] }
  else {
    Warn "several profiles and none has image-gen; pass -ProfileDir explicitly:"
    $candidates | ForEach-Object { Write-Host "         $($_.FullName)" }
    exit 1
  }
  $ProfileDir = $pick.FullName
}
if (-not (Test-Path $ProfileDir)) { throw "profile directory not found: $ProfileDir" }

Write-Host ''
Write-Host "  dsh-comfy-models installer" -ForegroundColor White
Write-Host "  source : $Root\plugin"
Write-Host "  target : $ProfileDir"
if ($DryRun) { Write-Host '  mode   : DRY RUN' -ForegroundColor Yellow }
Write-Host ''

# ------------------------------------------------------------------- 1+2 copy
$files = @('package.json', 'README.md', 'lib\catalog.js', 'lib\index.js', 'lib\yaml-store.js')
foreach ($f in $files) {
  if (-not (Test-Path (Join-Path $Root "plugin\$f"))) { throw "plugin\$f missing from the repo" }
}

foreach ($dest in @(
    (Join-Path $ProfileDir ".local-packages\$Pkg"),
    (Join-Path $ProfileDir "node_modules\$Pkg")
  )) {
  if ($DryRun) { Info "would copy -> $dest" ; continue }
  New-Item -ItemType Directory -Force -Path (Join-Path $dest 'lib') | Out-Null
  foreach ($f in $files) {
    Copy-Item (Join-Path $Root "plugin\$f") (Join-Path $dest $f) -Force
  }
  Ok "copied -> $dest"
}

# --------------------------------------------------------------- 3 package.json
$pkgJson = Join-Path $ProfileDir 'package.json'
if (-not (Test-Path $pkgJson)) { throw "profile has no package.json: $pkgJson" }
$raw = Get-Content $pkgJson -Raw
if ($raw -match '"dsh-comfy-models"') {
  Skip 'package.json already declares the dependency'
} else {
  $stamp = Get-Date -Format 'yyyyMMddHHmmss'
  if (-not $DryRun) { Copy-Item $pkgJson "$pkgJson.bak-$Pkg-$stamp" }
  # Splice a dependencies entry without reformatting the rest of the file.
  $dep = '  "dependencies": {'
  if ($raw -match [regex]::Escape($dep)) {
    $newRaw = $raw -replace [regex]::Escape($dep), ($dep + "`n    `"$Pkg`": `"file:./.local-packages/$Pkg`",")
  } else {
    # no dependencies block yet: insert one right after the opening brace
    $i = $raw.IndexOf('{')
    if ($i -lt 0) { throw 'package.json is not an object' }
    $newRaw = $raw.Substring(0, $i + 1) + "`n  `"dependencies`": {`n    `"$Pkg`": `"file:./.local-packages/$Pkg`"`n  }," + $raw.Substring($i + 1)
  }
  # The splice above leaves a trailing comma when `dependencies` was empty
  # (`{ }`), which is invalid JSON. Validate and fall back to a structured
  # rewrite - Node refuses to load the profile on a malformed package.json.
  try {
    $null = $newRaw | ConvertFrom-Json
  } catch {
    $obj = $raw | ConvertFrom-Json
    if (-not $obj.PSObject.Properties['dependencies']) {
      $obj | Add-Member -NotePropertyName dependencies -NotePropertyValue ([pscustomobject]@{})
    }
    $obj.dependencies | Add-Member -NotePropertyName $Pkg -NotePropertyValue "file:./.local-packages/$Pkg" -Force
    $newRaw = ($obj | ConvertTo-Json -Depth 20).TrimEnd() + "`n"
    Info 'dependencies block was empty - rewrote the file structurally'
  }
  if (-not $DryRun) { Write-TextNoBom $pkgJson $newRaw }
  Ok "package.json dependency added"
}

# ------------------------------------------------------------- 4 cordis.patch.yml
$yml = Join-Path $ProfileDir 'cordis.patch.yml'
if (-not (Test-Path $yml)) { throw "profile has no cordis.patch.yml: $yml" }
$ymlText = Get-Content $yml -Raw
if ($ymlText -match "(?m)^\s*-\s+id:\s*$Pkg\s*$") {
  Skip 'cordis.patch.yml already registers the plugin'
} else {
  $stamp = Get-Date -Format 'yyyyMMddHHmmss'
  if (-not $DryRun) { Copy-Item $yml "$yml.bak-$Pkg-$stamp" }
  $block = @"

# ---- dsh-comfy-models: switch the ComfyUI checkpoint from DSH ----
- insert:
    - id: $Pkg
      name: $Pkg
      config:
        comfyuiBaseURL: http://127.0.0.1:8188
        autoSyncOnStart: true
        includeEdit: true
        includeHires: false
        overwriteExisting: false
"@
  if (-not $DryRun) {
    $ymlText = [System.IO.File]::ReadAllText($yml)
    Write-TextNoBom $yml ($ymlText.TrimEnd() + "`n" + $block.TrimEnd() + "`n")
  }
  Ok 'cordis.patch.yml registration appended'
}

Write-Host ''
Write-Host '  Done.' -ForegroundColor Green
Write-Host ''
if ($DryRun) {
  Write-Host '  Dry run only - nothing was written. Re-run without -DryRun.' -ForegroundColor Yellow
} else {
  Write-Host '  Next:'
  Write-Host '    1. start ComfyUI (the "start ComfyUI" .bat) so the plugin can read /object_info'
  Write-Host '    2. restart DSH so the plugin loads'
  Write-Host '    3. ask the agent: "comfy_models_list" then "comfy_models_sync"'
  Write-Host ''
  Write-Host '  Adding a checkpoint later: drop it in models/checkpoints, then comfy_models_sync.'
}
Write-Host ''
