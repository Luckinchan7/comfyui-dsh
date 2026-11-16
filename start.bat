@echo off
REM ComfyUI local launcher - self-contained (python-base + venv + models all under D:\\ComfyUI).
REM --cache-lru 8 caches node results (the default --cache-none re-reads the 6.5 GB
REM weights every image). --reserve-vram 0.3 leaves 300 MB for the desktop. Adding
REM --fast or --enable-triton-backend makes this card SLOWER - see docs/PERFORMANCE.md.
REM Measured: 26-33 s per 832x1216 image, 30 steps, dpmpp_2m/karras, on 8 GB.
cd /d "%~dp0ComfyUI-0.45.0"
"%~dp0venv\Scripts\python.exe" -s main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3
pause
