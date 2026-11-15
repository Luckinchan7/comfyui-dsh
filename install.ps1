# ComfyUI local installer for Windows (RTX 40/50 series friendly)
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# Safe to re-run: every step checks its target first and skips when present,
# so an interrupted install resumes instead of starting over.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyBase    = Join-Path $Root 'python-base'
$Venv      = Join-Path $Root 'venv'
$ComfyDir  = Join-Path $Root 'ComfyUI-0.45.0'
$ModelDir  = Join-Path $ComfyDir 'models\checkpoints'
$ModelFile = Join-Path $ModelDir 'Illustrious-XL-v1.1.safetensors'

# mirrors chosen for reachability from CN; each has a fallback where it matters
$PyUrl    = 'https://registry.npmmirror.com/-/binary/python-build-standalone/20261110/cpython-3.12.16%2B20261110-x86_64-pc-windows-msvc-install_only.tar.gz'
$ComfyUrl = 'https://gh-proxy.com/https://github.com/comfyanonymous/ComfyUI/archive/refs/tags/v0.45.0.tar.gz'
$ComfyAlt = 'https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/refs/tags/v0.45.0'
$ModelUrl = 'https://hf-mirror.com/OnomaAIResearch/Illustrious-XL-v1.1/resolve/main/Illustrious-XL-v1.1.safetensors'
# Index mirrors in preference order. aliyun's PyPI mirror intermittently
# returns ChunkedEncodingError on small files, so it is not first.
$PipIndexes = @(
  'https://pypi.tuna.tsinghua.edu.cn/simple/',
  'https://mirrors.cloud.tencent.com/pypi/simple/',
  'https://mirrors.aliyun.com/pypi/simple/',
  'https://pypi.org/simple/'
)
$PipIndex = $PipIndexes[0]
# The aliyun directory page is plain HTML, not a PEP 503 index, so --find-links
# silently falls back to the CPU build on the PyPI mirror. Point at the wheels.
$TorchIdx = 'https://mirrors.aliyun.com/pytorch-wheels/cu130'
$TorchWhl = 'https://mirrors.aliyun.com/pytorch-wheels/cu130/torch-2.9.0%2Bcu130-cp312-cp312-win_amd64.whl'
$TvWhl    = 'https://mirrors.aliyun.com/pytorch-wheels/cu130/torchvision-0.24.0%2Bcu130-cp312-cp312-win_amd64.whl'

function Step($n, $msg) { Write-Host ''; Write-Host "[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "    OK   $msg" -ForegroundColor Green }
function Skip($msg)     { Write-Host "    --   $msg" -ForegroundColor DarkGray }
function Info($msg)     { Write-Host "         $msg" -ForegroundColor DarkGray }
function Fail($msg)     { Write-Host "    !!   $msg" -ForegroundColor Red; exit 1 }

function Format-Size($bytes) {
  if ($bytes -ge 1GB) { return ([math]::Round($bytes/1GB, 2)).ToString() + ' GB' }
  if ($bytes -ge 1MB) { return ([math]::Round($bytes/1MB, 1)).ToString() + ' MB' }
  return ([math]::Round($bytes/1KB, 0)).ToString() + ' KB'
}

# Run an external program without letting its stderr output abort the script.
# PowerShell turns native stderr into error records, and with
# $ErrorActionPreference = 'Stop' that escalates to a terminating error even
# when the program itself succeeded - which is exactly what curl's progress
# meter would otherwise cause here. Passing -Show keeps the output on screen
# (useful for the multi-GB model download) while stderr stays non-terminating.
function Invoke-Native($Exe, [string[]]$Argv, [switch]$Show) {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    if ($Show) {
      # pass straight through so curl's progress bar renders in place
      & $Exe @Argv
    } else {
      & $Exe @Argv 2>&1 | Out-Null
    }
    return $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $prev
  }
}

# torch and torchvision are installed with --no-deps (so pip cannot swap in a
# CPU build), which leaves their own imports unsatisfied. Pull just the runtime
# dependencies from the PyPI mirror.
function Repair-TorchDeps($Py, $Indexes) {
  $pkgs = @('typing_extensions', 'filelock', 'sympy', 'networkx', 'jinja2', 'fsspec',
            'numpy', 'pillow', 'setuptools')
  foreach ($idx in $Indexes) {
    $code = Invoke-Native $Py (@('-m', 'pip', 'install', '--quiet', '--no-warn-script-location',
      '--retries', '5', '--timeout', '60', '--index-url', $idx) + $pkgs)
    if ($code -ne 0) { continue }
    $probe = Invoke-Native $Py @('-c', 'import typing_extensions, filelock, sympy, networkx, jinja2, fsspec, numpy, PIL, setuptools')
    if ($probe -eq 0) { return 0 }
  }
  return 1
}

# pip's own downloader gives up on this route (15s read timeouts on a 1.9 GB
# wheel), so fetch the wheel with curl and install from the local file.
function Get-Wheel($Url, $MinBytes, $Label) {
  $name = [System.IO.Path]::GetFileName([Uri]::UnescapeDataString($Url))
  $dest = Join-Path $env:TEMP $name
  if (-not (Get-File $Url $dest $MinBytes $Label)) { return $null }
  return $dest
}

# Download with resume. Returns $true when the file reaches $MinBytes.
function Get-File($Url, $Out, $MinBytes, $Label) {
  if (Test-Path $Out) {
    $have = (Get-Item $Out).Length
    if ($have -ge $MinBytes) { Skip "$Label (already downloaded, $(Format-Size $have))"; return $true }
  }
  Info "GET $Url"
  $code = Invoke-Native 'curl.exe' @('-sSL', '--fail', '--retry', '3', '--retry-delay', '2', '-C', '-', '-o', "$Out", "$Url")
  if ($code -ne 0 -or -not (Test-Path $Out)) { return $false }
  $have = (Get-Item $Out).Length
  if ($have -lt $MinBytes) {
    Write-Host "         short read ($(Format-Size $have) of at least $(Format-Size $MinBytes))"
    return $false
  }
  Ok "$Label ($(Format-Size $have))"
  return $true
}

function Test-TorchCu {
  param([string]$Py)
  try {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $r = & $Py -c "import torch;print(torch.__version__);print(torch.cuda.is_available());print(torch.version.cuda)" 2>$null
    } finally {
      $ErrorActionPreference = $prev
    }
    if (-not $r -or $r.Count -lt 3) { return $null }
    if ($r[0] -notlike '*+cu*') { return $null }
    return @{ Version = $r[0]; Cuda = ($r[1] -eq 'True'); Runtime = $r[2] }
  } catch { return $null }
}

Write-Host ''
Write-Host '  ComfyUI + Denoise slider' -ForegroundColor White
Write-Host "  target: $Root"
Write-Host ''

# ---------------------------------------------------------------- 1) python
Step 1 'Python 3.12 runtime (standalone copy, system Python untouched)'
$PyExe = Join-Path $PyBase 'python.exe'
if (Test-Path $PyExe) {
  $pv = & $PyExe -c "import sys;print('%d.%d.%d'%sys.version_info[:3])"
  Skip "python-base ($pv)"
} else {
  $tgz = Join-Path $env:TEMP 'cpython-portable-win.tar.gz'
  if (-not (Get-File $PyUrl $tgz 30000000 'python runtime')) { Fail 'python download failed - check your network and re-run' }
  Info 'extracting...'
  New-Item -ItemType Directory -Force -Path $PyBase | Out-Null
  $code = Invoke-Native 'tar.exe' @('-xzf', "$tgz", '-C', "$PyBase", '--strip-components=1')
  if ($code -ne 0) { Fail 'tar extract failed' }
  Remove-Item $tgz -Force -ErrorAction SilentlyContinue
  if (-not (Test-Path $PyExe)) { Fail 'python.exe missing after extract' }
  Ok 'python-base ready'
}

# A standalone build needs its own pip; make sure it is there.
$null = Invoke-Native $PyExe @('-m', 'ensurepip', '--default-pip')
$PyVer = & $PyExe -c "import sys;print('%d.%d.%d'%sys.version_info[:3])"
Ok "python $PyVer"

# ---------------------------------------------------------------- 2) venv
Step 2 'virtual environment'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
if (Test-Path $VenvPy) {
  Skip 'venv'
} else {
  $code = Invoke-Native $PyExe @('-m', 'venv', "$Venv")
  if ($code -ne 0) { Fail 'venv creation failed' }
  Ok 'venv created'
}
# A venv stores absolute paths in pyvenv.cfg, so moving the whole folder breaks
# it. Rewrite those two lines to the current location, which makes the install
# relocatable simply by re-running this script after a move.
$Cfg = Join-Path $Venv 'pyvenv.cfg'
if (Test-Path $Cfg) {
  $cfgText = Get-Content $Cfg -Raw
  $fixed = $cfgText
  $fixed = $fixed -replace '(?m)^home = .*', ("home = " + $PyBase)
  $fixed = $fixed -replace '(?m)^executable = .*', ("executable = " + $PyExe)
  if ($fixed -ne $cfgText) {
    Set-Content -Path $Cfg -Value $fixed -NoNewline -Encoding ASCII
    Info 'pyvenv.cfg repointed at the current folder'
  }
}
foreach ($idx in $PipIndexes) {
  if ((Invoke-Native $VenvPy @('-m', 'pip', 'install', '--upgrade', 'pip', '--quiet', '--retries', '5', '--timeout', '60', '--index-url', $idx)) -eq 0) { break }
}
Ok 'pip ready'

# ---------------------------------------------------------------- 3) torch
Step 3 'PyTorch with CUDA 13 (RTX 50 series / Blackwell sm_120 needs cu130)'
$t = Test-TorchCu -Py $VenvPy
if ($t -and $t.Cuda) {
  Skip "torch $($t.Version) cuda=True runtime=$($t.Runtime)"
} else {
  Info 'about 1.9 GB, a few minutes'
  $tw = Get-Wheel $TorchWhl 1800000000 'torch 2.9.0+cu130 wheel'
  $vw = Get-Wheel $TvWhl 8000000 'torchvision 0.24.0+cu130 wheel'
  if (-not $tw -or -not $vw) { Fail 'could not download the cu130 wheels' }
  $code = Invoke-Native $VenvPy @('-m', 'pip', 'install', '--no-cache-dir', '--force-reinstall', '--no-deps', $tw, $vw)
  if ($code -ne 0) { Fail 'pip could not install torch' }
  $null = Repair-TorchDeps $VenvPy $PipIndexes
  $t = Test-TorchCu -Py $VenvPy
  if (-not $t) { Fail 'torch install failed' }
  if (-not $t.Cuda) { Fail 'torch installed but CUDA is unavailable - update your NVIDIA driver' }
  Ok "torch $($t.Version) cuda=True runtime=$($t.Runtime)"
}

# ---------------------------------------------------------------- 4) comfy source
Step 4 'ComfyUI source v0.45.0'
if (Test-Path (Join-Path $ComfyDir 'main.py')) {
  Skip 'ComfyUI-0.45.0'
} else {
  $tgz = Join-Path $env:TEMP 'comfyui-0.45.0.tar.gz'
  $got = Get-File $ComfyUrl $tgz 5000000 'ComfyUI source'
  if (-not $got) {
    Info 'primary mirror failed, trying codeload...'
    if (-not (Get-File $ComfyAlt $tgz 5000000 'ComfyUI source')) { Fail 'ComfyUI source download failed' }
  }
  Info 'extracting...'
  $tmp = Join-Path $env:TEMP ('comfyui-x-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $code = Invoke-Native 'tar.exe' @('-xzf', "$tgz", '-C', "$tmp")
  if ($code -ne 0) { Fail 'tar extract failed' }
  $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
  # The target may already exist from an interrupted run (or a pre-seeded
  # models/ folder), so merge instead of renaming.
  if (Test-Path $ComfyDir) {
    Get-ChildItem $inner.FullName -Force | ForEach-Object {
      Move-Item $_.FullName (Join-Path $ComfyDir $_.Name) -Force
    }
    Remove-Item $inner.FullName -Recurse -Force -ErrorAction SilentlyContinue
  } else {
    Move-Item $inner.FullName $ComfyDir
  }
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $tgz -Force -ErrorAction SilentlyContinue
  Ok 'ComfyUI-0.45.0 ready'
}

# ---------------------------------------------------------------- 5) deps
Step 5 'ComfyUI Python dependencies'
$needDeps = $true
$probe = Invoke-Native $VenvPy @('-c', 'import aiohttp, safetensors, einops, transformers, yaml, PIL')
if ($probe -eq 0) { $needDeps = $false }
if ($needDeps) {
  Info 'installing from requirements.txt (torch is excluded on purpose)'
  # requirements.txt pins torch/torchvision, which would pull the CPU build again.
  $reqAll = Join-Path $ComfyDir 'requirements.txt'
  $reqNoTorch = Join-Path $env:TEMP 'comfyui-requirements-notorch.txt'
  Get-Content $reqAll | Where-Object { $_ -notmatch '^\s*(torch|torchvision|torchaudio)\b' } |
    Set-Content -Path $reqNoTorch -Encoding ASCII
  $code = 1
  foreach ($idx in $PipIndexes) {
    $code = Invoke-Native $VenvPy @('-m', 'pip', 'install', '-r', $reqNoTorch, '--retries', '5', '--timeout', '60', '--index-url', $idx)
    if ($code -eq 0) { break }
    Info "mirror failed, trying the next one..."
  }
  if ($code -ne 0) { Fail 'pip could not install requirements.txt' }
  Ok 'dependencies installed'
} else {
  Skip 'dependencies'
}

# requirements.txt lists `torch`, so pip may have swapped in a CPU build.
# Re-assert the cu130 one whenever that happens.
$t = Test-TorchCu -Py $VenvPy
if (-not $t -or -not $t.Cuda) {
  Info 'torch was replaced during dependency install, restoring cu130...'
  $tw = Get-Wheel $TorchWhl 1800000000 'torch 2.9.0+cu130 wheel'
  $vw = Get-Wheel $TvWhl 8000000 'torchvision 0.24.0+cu130 wheel'
  if (-not $tw -or -not $vw) { Fail 'could not download the cu130 wheels' }
  $code = Invoke-Native $VenvPy @('-m', 'pip', 'install', '--no-cache-dir', '--force-reinstall', '--no-deps', $tw, $vw)
  if ($code -ne 0) { Fail 'pip could not restore the cu130 torch build' }
  $null = Repair-TorchDeps $VenvPy $PipIndexes
  $t = Test-TorchCu -Py $VenvPy
  if (-not $t -or -not $t.Cuda) { Fail 'could not restore the CUDA build of torch' }
}
Ok "torch $($t.Version) cuda=True runtime=$($t.Runtime)"

# ---------------------------------------------------------------- 6) model
Step 6 'SDXL checkpoint - Illustrious-XL v1.1 (6.46 GB)'
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
if ((Test-Path $ModelFile) -and (Get-Item $ModelFile).Length -gt 6000000000) {
  Skip "Illustrious-XL-v1.1.safetensors ($(Format-Size (Get-Item $ModelFile).Length))"
} else {
  Info 'from hf-mirror.com (the official host is very slow from CN)'
  Info 'resumable: re-run this script if it drops'
  $code = Invoke-Native 'curl.exe' @('-sSL', '--fail', '--retry', '3', '--retry-delay', '2', '-C', '-', '--progress-bar', '-o', "$ModelFile", "$ModelUrl") -Show
  if ($code -ne 0) { Fail 'model download failed - re-run to resume' }
  $sz = (Get-Item $ModelFile).Length
  if ($sz -lt 6000000000) { Fail "model truncated ($(Format-Size $sz)) - re-run to resume" }
  Ok (Format-Size $sz)
}

# ---------------------------------------------------------------- 7) verify
Step 7 'smoke test'
$check = @'
import torch, sys
print("  torch     ", torch.__version__)
print("  cuda      ", torch.cuda.is_available())
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print("  gpu       ", p.name)
    print("  vram      ", round(p.total_memory/1048576), "MB")
    print("  capability", "%d.%d" % (p.major, p.minor))
a = torch.randn(512, 512, device="cuda")
b = a @ a
print("  matmul    ", tuple(b.shape), "ok")
'@
$checkFile = Join-Path $env:TEMP 'comfy-check.py'
Set-Content -Path $checkFile -Value $check -Encoding ASCII
& $VenvPy $checkFile
if ($LASTEXITCODE -ne 0) { Fail 'smoke test failed' }
Remove-Item $checkFile -Force -ErrorAction SilentlyContinue

$vram = 0
try {
  $vram = [int](& $VenvPy -c "import torch;p=torch.cuda.get_device_properties(0);print(round(p.total_memory/1048576))")
} catch { }
if ($vram -gt 0 -and $vram -lt 6000) {
  Write-Host ''
  Write-Host "  [warn] only $vram MB of VRAM. SDXL at 1024x1024 wants about 7000 MB." -ForegroundColor Yellow
  Write-Host '         It will run, but expect a slower per-image time.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '  Install complete.' -ForegroundColor Green
Write-Host ''
Write-Host '  Next:'
Write-Host '    1. double-click the "start ComfyUI" .bat    -> 127.0.0.1:8188'
Write-Host '    2. double-click the "start slider" .bat     -> 127.0.0.1:8189'
Write-Host '    3. node .\dsh\apply-workflows.mjs      wires the workflows into DSH'
Write-Host ''
$total = 0
foreach ($p in @($PyBase, $Venv, $ComfyDir)) {
  if (Test-Path $p) {
    $total += (Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  }
}
Write-Host "  Disk used: $(Format-Size $total)"
Write-Host ''
