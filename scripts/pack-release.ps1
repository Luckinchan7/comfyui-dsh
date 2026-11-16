# Build the release zip from the committed tree and emit a checksum file.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\pack-release.ps1 -Version 1.1.0
#
# Using `git archive` instead of Compress-Archive is deliberate: it packs exactly
# the files git tracks in HEAD, so the release can never drift from the repo and
# stray build artifacts (node_modules, models, output) cannot leak in.

param(
  [Parameter(Mandatory = $true)][string]$Version,
  [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $OutDir) { $OutDir = Join-Path $Root 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Push-Location $Root
try {
  $dirty = git status --porcelain
  if ($dirty) {
    Write-Host '  [warn] working tree is not clean - the zip is built from HEAD,' -ForegroundColor Yellow
    Write-Host '         so uncommitted edits will NOT be included.' -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "         $_" -ForegroundColor DarkGray }
    Write-Host ''
  }

  $zip = Join-Path $OutDir 'comfyui-dsh.zip'
  if (Test-Path $zip) { Remove-Item $zip -Force }
  git archive --format=zip -o "$zip" HEAD
  if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }

  $sums = Join-Path $OutDir "SHA256SUMS-v$Version"
  $hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
  "$hash  comfyui-dsh.zip" | Out-File -FilePath $sums -Encoding ascii -NoNewline:$false

  $kb = [math]::Round((Get-Item $zip).Length / 1KB, 1)
  Write-Host "  zip    $zip  ($kb KB)" -ForegroundColor Green
  Write-Host "  sums   $sums" -ForegroundColor Green
  Write-Host "  sha256 $hash"
  Write-Host ''
  Write-Host '  Next:' -ForegroundColor Cyan
  Write-Host "    git tag -a v$Version -m 'v$Version'"
  Write-Host "    git -c credential.helper=wincred push origin v$Version"
  Write-Host "    gh release create v$Version '$zip' '$sums' -t 'v$Version' -F notes.md"
}
finally {
  Pop-Location
}
