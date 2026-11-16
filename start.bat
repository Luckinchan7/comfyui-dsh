@echo off
REM ============================================================
REM  ComfyUI launcher (ASCII-only clone of the Chinese-named one)
REM
REM  Why this file exists: a .bat that references a Chinese filename
REM  breaks when the console codepage is not 936, so this variant
REM  avoids non-ASCII text entirely and duplicates the logic.
REM
REM  Measured on RTX 5060 Laptop 8GB: 26-33 s per 832x1216 30-step
REM  image (hot). Do NOT add --fast or --enable-triton-backend -
REM  both measured 3-4x SLOWER on this card. See docs/PERFORMANCE.md.
REM ============================================================
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\ComfyUI-0.45.0\main.py" goto :bad_layout
if not exist "%ROOT%\venv\Scripts\python.exe" goto :bad_layout

netstat -an > "%TEMP%\comfyui-ns.txt" 2>nul
findstr /c:"127.0.0.1:8188" "%TEMP%\comfyui-ns.txt" | findstr /i "LISTENING" > "%TEMP%\comfyui-hit.txt" 2>nul
set "ALREADY="
for /f "usebackq tokens=*" %%A in ("%TEMP%\comfyui-hit.txt") do set "ALREADY=1"
del "%TEMP%\comfyui-ns.txt" "%TEMP%\comfyui-hit.txt" >nul 2>nul
if defined ALREADY goto :running

echo.
echo   Starting ComfyUI from %ROOT%
echo   URL:        http://127.0.0.1:8188
echo   The browser opens by itself once the server is up.
echo   First image includes a 30-60 s model load; after that ~26-33 s at 832x1216.
echo.

cd /d "%ROOT%\ComfyUI-0.45.0"
if exist "%ROOT%\open_when_ready.bat" start "" /b "%ROOT%\open_when_ready.bat"
"%ROOT%\venv\Scripts\python.exe" -s main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3

echo.
echo   ComfyUI stopped.
pause
exit /b 0

:running
echo.
echo   ComfyUI is already running - opening it in your browser.
echo   URL: http://127.0.0.1:8188
echo.
echo   To restart: end python.exe in Task Manager, then run this file again.
echo.
start "" http://127.0.0.1:8188
ping -n 4 127.0.0.1 >nul
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
