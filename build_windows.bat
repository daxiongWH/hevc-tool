@echo off
REM =====================================================
REM  HEVC Converter - Windows one-click build script
REM  Output: dist\HEVCConverter.exe (single file, ffmpeg built-in)
REM  NOTE: This script is 100% ASCII (no Chinese) so it can
REM  never be garbled by cmd encoding. Save as ANSI or UTF-8.
REM =====================================================
cd /d "%~dp0"

echo [1/3] Installing Python dependencies...
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple customtkinter psutil pyinstaller

REM ---------- Auto download built-in ffmpeg (one ffmpeg.exe only) ----------
if exist bin\ffmpeg.exe goto HAS_FFMPEG
echo [2/3] Downloading built-in ffmpeg (~30MB), please wait...
if not exist bin mkdir bin
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg.zip'"
powershell -NoProfile -Command "Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'ffmpeg_tmp' -Force"
for /r ffmpeg_tmp %%F in (ffmpeg.exe) do copy /y "%%F" bin\ffmpeg.exe >nul
rmdir /s /q ffmpeg_tmp
del /q ffmpeg.zip
:HAS_FFMPEG

echo [3/3] Building with PyInstaller...
if exist bin\ffmpeg.exe (
  pyinstaller --noconfirm --onefile --windowed --name "HEVCConverter" ^
    --add-binary "bin\ffmpeg.exe;bin" hevc_converter.py
) else (
  echo WARNING: ffmpeg download failed, will rely on system PATH.
  pyinstaller --noconfirm --onefile --windowed --name "HEVCConverter" hevc_converter.py
)

echo.
echo ============================================
echo  BUILD DONE! Output: dist\HEVCConverter.exe
echo  Copy this exe to any Windows PC and run it.
echo  No Python or ffmpeg needed on target PC.
echo ============================================
pause
