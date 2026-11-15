@echo off
setlocal
title Denoise Slider

REM ============================================================
REM  Denoise slider - zero dependency Node server on port 8189
REM  Talks to ComfyUI on 127.0.0.1:8188, so start ComfyUI first.
REM ============================================================

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "SLIDER=%HERE%"
if not exist "%SLIDER%\server.mjs" set "SLIDER=%~dp0slider"
if not exist "%SLIDER%\server.mjs" (
  echo [ERROR] server.mjs not found.
  echo         Looked in "%HERE%" and "%~dp0slider"
  pause
  exit /b 1
)

REM ---- locate node: bundled DSH runtime first, then a normal install, then PATH ----
set "NODE_EXE="
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe" set "NODE_EXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
if not defined NODE_EXE if exist "C:\Program Files\nodejs\node.exe" set "NODE_EXE=C:\Program Files\nodejs\node.exe"
if not defined NODE_EXE (
  for /f "delims=" %%N in ('where node 2^>nul') do if not defined NODE_EXE set "NODE_EXE=%%N"
)
if not defined NODE_EXE (
  echo [ERROR] node.exe not found.
  echo         Install Node.js 18+ from https://nodejs.org/ and run this again.
  pause
  exit /b 1
)

REM ---- already running? ----
netstat -an > "%TEMP%\slider-ns.txt" 2>nul
findstr ":8189" "%TEMP%\slider-ns.txt" | findstr "LISTENING" > "%TEMP%\slider-hit.txt" 2>nul
set "RUNNING="
for /f "usebackq tokens=*" %%A in ("%TEMP%\slider-hit.txt") do set "RUNNING=1"
del "%TEMP%\slider-ns.txt" "%TEMP%\slider-hit.txt" >nul 2>nul
if defined RUNNING (
  echo.
  echo   Slider already running: http://127.0.0.1:8189
  start "" http://127.0.0.1:8189
  ping -n 4 127.0.0.1 >nul
  exit /b 0
)

REM ---- ComfyUI reachable? warn but still start (the page shows the status) ----
netstat -an > "%TEMP%\comfy-ns.txt" 2>nul
findstr /c:"127.0.0.1:8188" "%TEMP%\comfy-ns.txt" | findstr /i "LISTENING" > "%TEMP%\comfy-hit.txt" 2>nul
set "COMFY="
for /f "usebackq tokens=*" %%A in ("%TEMP%\comfy-hit.txt") do set "COMFY=1"
del "%TEMP%\comfy-ns.txt" "%TEMP%\comfy-hit.txt" >nul 2>nul

echo.
echo   Denoise Slider
echo   folder : %SLIDER%
echo   node   : %NODE_EXE%
echo   url    : http://127.0.0.1:8189
if not defined COMFY (
  echo.
  echo   [note] ComfyUI is not listening on 8188 yet.
  echo          Start ComfyUI first ^(run the other .bat^), otherwise generation will fail.
)
echo.
echo   Keep this window open. Close it to stop the slider.
echo.

set "COMFY_ROOT=%HERE%\ComfyUI-0.45.0"
if not exist "%COMFY_ROOT%\main.py" set "COMFY_ROOT=D:\ComfyUI\ComfyUI-0.45.0"
set "PORT=8189"
set "COMFY_API=http://127.0.0.1:8188"

ping -n 2 127.0.0.1 >nul
start "" http://127.0.0.1:8189

cd /d "%SLIDER%"
"%NODE_EXE%" "%SLIDER%\server.mjs"
echo.
echo   Slider stopped.
pause
