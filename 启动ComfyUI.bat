@echo off
setlocal
title ComfyUI

REM ============================================================
REM  ComfyUI launcher for the portable layout (python-base + venv + models)
REM  If port 8188 is already listening it just tells you and exits.
REM  Close this window (or Ctrl+C) to stop ComfyUI.
REM ============================================================

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\ComfyUI-0.45.0\main.py" goto :bad_layout
if not exist "%ROOT%\venv\Scripts\python.exe" goto :bad_layout

REM --- already listening on 8188? ---
netstat -an > "%TEMP%\comfyui-ns.txt" 2>nul
findstr /c:"127.0.0.1:8188" "%TEMP%\comfyui-ns.txt" | findstr /i "LISTENING" > "%TEMP%\comfyui-hit.txt" 2>nul
set "ALREADY="
for /f "usebackq tokens=*" %%A in ("%TEMP%\comfyui-hit.txt") do set "ALREADY=1"
del "%TEMP%\comfyui-ns.txt" "%TEMP%\comfyui-hit.txt" >nul 2>nul
if defined ALREADY goto :running

echo.
echo   Starting ComfyUI from %ROOT%
echo   URL:        http://127.0.0.1:8188
echo   First image includes a 30-60 s model load; after that ~20-30 s at 832x1216.
echo.

cd /d "%ROOT%\ComfyUI-0.45.0"
REM --cache-lru 8 keeps node results across runs; --cache-none (ComfyUI default off,
REM but a common bad copy) re-reads the 6.5 GB weights for every single image.
REM --reserve-vram 0.3 leaves 300 MB for the desktop. Do NOT add --fast or
REM --enable-triton-backend: both are slower on 8 GB cards (see docs/PERFORMANCE.md).
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
ping -n 7 127.0.0.1 >nul
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
