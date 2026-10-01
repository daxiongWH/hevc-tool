# HEVC 保真转码工具 (H.265)

一个可视化视频转码工具：**单任务串行**把视频转成 H.265(HEVC)，**保持原分辨率、原帧率**，肉眼保真，用于备份 / 腾空网盘空间。

## 功能
- ✅ 单任务逐条转码，**每个任务独立进度条 + 百分比**
- ✅ 全局**总进度条 + 总百分比**（任务 N / 总数）
- ✅ **可指定导出文件夹**；未指定则输出到源文件所在目录
- ✅ 输出文件统一重命名，尾部加下划线后缀 **`_H.265`**（如 `movie.mkv` → `movie_H.265.mkv`）
- ✅ 写入版权元数据 **`daxiong_wh`**（小写），用于标识备份来源，万一外流可追溯
- ✅ **自动识别硬件编码器**：AMD AMF / NVIDIA NVENC / Intel QSV / Mac VideoToolbox；无硬编自动回退 CPU libx265
- ✅ 保持原分辨率、原帧率；音频统一 AAC 192kbps
- ✅ **MKV 多音轨 / 多内嵌字幕**：每行下拉手动选择音轨、字幕轨道
- ✅ **外挂字幕**：自动识别同目录同名 `.srt / .ass`；也可点“选字幕文件”手动指定
- ✅ 跨平台：Windows(exe) 与 macOS(app)

## 目录结构
```
hevc_converter/
├── hevc_converter.py      # 主程序（含 --selftest 自检）
├── requirements.txt       # Python 依赖
├── build_windows.bat      # Windows 一键打包脚本
├── build_mac.sh           # macOS 一键打包脚本
└── bin/                   # （打包时生成）内置 ffmpeg
```

## 打包方法（二选一，按你的系统执行）
> 打包脚本会**全自动下载并内置 ffmpeg**，用户拿到成品无需再装任何东西。

### Windows → 生成 `.exe`
```bat
双击 build_windows.bat
```
产物：`dist\HEVC转码工具.exe`

### macOS → 生成 `.app`
```bash
chmod +x build_mac.sh
bash build_mac.sh
```
产物：`dist/HEVC转码工具.app`
> Mac 端脚本会自动下载 M 系列(arm64) 或 Intel(x64) 对应版本的静态 ffmpeg，无需手动安装；仅当自动下载失败时才需 `brew install ffmpeg`。

## 使用说明
1. 打开程序 → 点【导入文件夹】选择视频所在目录（自动扫描 mkv/mp4/avi/mov 等）
2. 每行视频可下拉切换：音轨、字幕轨道 / 外挂字幕；无字幕视频可点【选字幕文件】单独指定
3. 点【选择导出目录】指定输出位置（可选）
4. 点【开始转码】，观察每行进度条 + 底部总进度条
5. 完成后在导出目录找到 `xxx_H.265.mkv / .mp4`，已自动写入 `daxiong_wh` 元数据

## 硬件编码说明
| 你的硬件 | 使用的编码器 |
|---|---|
| AMD RX6000/7000（如 6700XT） | `hevc_amf` 硬编 |
| NVIDIA GTX/RTX | `hevc_nvenc` 硬编 |
| Intel 核显 / Arc | `hevc_qsv` 硬编 |
| Apple M1/M2/M3 | `hevc_videotoolbox` 硬编 |
| 无可用硬编 | `libx265` CPU 软编 |

> 程序固定**单任务串行**，一次只调用 1 路编码器，规避了显卡硬编并发路数限制。
> 保真参数：硬编用恒定质量(CQ/QP)，软编用 CRF=21，肉眼几乎无损失。
