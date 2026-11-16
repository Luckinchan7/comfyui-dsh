@echo off
setlocal
title ComfyUI

REM ============================================================
REM  ComfyUI launcher - ASCII copy of the Chinese-named one, same logic.
REM  Default: server only, no browser. Pass -open to open one.
REM
REM  ComfyUI launcher - portable layout (python-base + venv + models in D:\ComfyUI)
REM
REM  Measured on RTX 5060 Laptop 8GB: 26-33 s per 832x1216 30-step image (hot).
REM  Do NOT add --fast or --enable-triton-backend - both measured 3-4x SLOWER
REM  on this card. See docs/PERFORMANCE.md.
REM
REM  Already running? This opens the browser and exits instead of
REM  dying with "Port 8188 is already in use".
REM  Close this window (or Ctrl+C) to stop ComfyUI.
REM ============================================================

REM --- options ----------------------------------------------------------------
REM   no argument        start the server, do NOT open a browser (default)
REM   -open / --open     start the server, open the browser when ready
REM   --no-browser       explicit no-browser (same as default)
REM  When the server is already running, only -open opens the browser.
REM  Everything stays ASCII on purpose: a Chinese filename or comment inside a
REM  .bat breaks under a non-936 console codepage.
set "OPEN_BROWSER=0"
for %%a in (%*) do (
    if /i "%%~a"=="-open"        set "OPEN_BROWSER=1"
    if /i "%%~a"=="--open"       set "OPEN_BROWSER=1"
    if /i "%%~a"=="--no-browser" set "OPEN_BROWSER=0"
)

set "ROOT=%~dp0.."
if not exist "%ROOT%\ComfyUI-0.45.0\main.py" set "ROOT=D:\ComfyUI"

if not exist "%ROOT%\ComfyUI-0.45.0\main.py" goto :bad_layout
if not exist "%ROOT%\venv\Scripts\python.exe" goto :bad_layout

REM --- already listening on 8188? (pipe form: no temp files, no stale state) ---
netstat -an | findstr /c:"127.0.0.1:8188" | findstr /i "LISTENING" >nul 2>&1
if not errorlevel 1 goto :running

echo.
echo   Starting ComfyUI from %ROOT%
echo   URL:        http://127.0.0.1:8188
if "%OPEN_BROWSER%"=="1" echo   The browser opens by itself once the server is up.
if "%OPEN_BROWSER%"=="0" echo   Server only. Open http://127.0.0.1:8188 when you need it.
echo   First image includes a 30-60 s model load; after that ~26-33 s at 832x1216.
echo.

cd /d "%ROOT%\ComfyUI-0.45.0"
if "%OPEN_BROWSER%"=="1" if exist "%ROOT%\open_when_ready.bat" start "" /b "%ROOT%\open_when_ready.bat"
"%ROOT%\venv\Scripts\python.exe" -s main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3

echo.
echo   ComfyUI stopped.
pause
exit /b 0

:running
echo.
echo   ComfyUI is already running.
echo   URL: http://127.0.0.1:8188
echo.
echo   To restart: end python.exe in Task Manager, then run this file again.
echo.
if "%OPEN_BROWSER%"=="1" (
    start "" http://127.0.0.1:8188
    ping -n 4 127.0.0.1 >nul
)
exit /b 0

:bad_layout
echo.
echo   [ERROR] This folder does not look like a complete install.
echo.
echo   Expected:
echo     %ROOT%\ComfyUI-0.45.0\main.py
echo     %ROOT%\venv\Scripts\python.exe
echo.
echo   Run install.ps1 first:
echo     powershell -ExecutionPolicy Bypass -File "%ROOT%\install.ps1"
echo.
pause
exit /b 1
