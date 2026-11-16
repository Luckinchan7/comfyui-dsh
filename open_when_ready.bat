@echo off
REM Wait until ComfyUI answers on 127.0.0.1:8188, then open it in the default browser.
REM Called in the background by the launcher bat so the console keeps showing server logs.
setlocal enabledelayedexpansion
set "URL=http://127.0.0.1:8188"

for /l %%i in (1,1,120) do (
    netstat -an | findstr /c:"127.0.0.1:8188" | findstr /i "LISTENING" >nul 2>&1
    if not errorlevel 1 goto :open
    ping -n 2 127.0.0.1 >nul
)
exit /b 1

:open
start "" "%URL%"
exit /b 0
