#!/usr/bin/env bash
# =====================================================
#  HEVC 转码工具 - macOS 一键打包脚本（傻瓜式）
#  用法: 在终端中执行  bash build_mac.sh
#  全程自动：装依赖 -> 自动下载对应架构的静态 ffmpeg -> 打包 .app
#  产物: dist/HEVC转码工具.app （已内置 ffmpeg，双击即用）
#  注意: M 系列(M1/M2/M3) 会自动下载 arm64 版；Intel 下载 x64 版
# =====================================================
set -e
cd "$(dirname "$0")"

echo "[1/3] 检查 Python 依赖..."
pip3 install -i https://pypi.tuna.tsinghua.edu.cn/simple customtkinter psutil pyinstaller

# ---------- 自动下载静态 ffmpeg（只需一个文件，无需 brew）----------
ADD_BIN=()
if [ -f bin/ffmpeg ]; then
  echo "[2/3] 已找到内置 ffmpeg"
else
  echo "[2/3] 正在下载内置 ffmpeg（静态版，约 30MB）..."
  mkdir -p bin
  ARCH=$(uname -m)
  if [ "$ARCH" = "arm64" ]; then
    URL="https://github.com/eugeneware/ffmpeg-static/releases/latest/download/darwin-arm64"
  else
    URL="https://github.com/eugeneware/ffmpeg-static/releases/latest/download/darwin-x64"
  fi
  echo "     下载地址: $URL"
  curl -L --fail -o bin/ffmpeg "$URL" || true
  if [ -s bin/ffmpeg ]; then
    chmod +x bin/ffmpeg
    echo "     下载成功: bin/ffmpeg ($ARCH)"
  else
    rm -f bin/ffmpeg
    echo "     !! 自动下载失败。回退尝试系统 ffmpeg ..."
    FF=$(command -v ffmpeg || true)
    if [ -n "$FF" ]; then
      cp "$FF" bin/ffmpeg
      chmod +x bin/ffmpeg
      echo "     已使用系统 ffmpeg: $FF"
    else
      echo "     !! 未能获取 ffmpeg。请先执行:  brew install ffmpeg  后重试"
      echo "     （程序仍会打包，但运行时需系统已装 ffmpeg）"
    fi
  fi
fi

if [ -f bin/ffmpeg ] && [ -s bin/ffmpeg ]; then
  ADD_BIN=(--add-binary "bin/ffmpeg:bin")
fi

echo "[3/3] PyInstaller 打包中..."
pyinstaller --noconfirm --windowed --name "HEVC转码工具" \
  "${ADD_BIN[@]}" \
  hevc_converter.py

echo ""
echo "============================================"
echo "  完成! 成品在这里:  dist/HEVC转码工具.app"
echo "  把这个 .app 拷到任何 Mac 电脑都能直接运行，"
echo "  不需要安装任何依赖或 ffmpeg。"
echo "============================================"
