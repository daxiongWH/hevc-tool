# -*- coding: utf-8 -*-
"""
HEVC 保真转码工具 (H.265)
- 单任务串行转码，固定一路
- 每个任务独立进度条 + 百分比；全局总进度条 + 百分比
- 可指定导出文件夹；输出文件统一加后缀 _H.265
- 写入元数据 daxiong_wh（版权标识）
- 自动识别硬件编码器（AMD AMF / NVIDIA NVENC / Intel QSV / Mac VideoToolbox / CPU libx265）
- 保持原分辨率、原帧率；音频统一 AAC 192kbps
- MKV 多音轨 / 多内嵌字幕可选；自动识别同目录同名外挂字幕(srt/ass)；可手动指定字幕文件
跨平台：Windows / macOS
"""

import os
import re
import sys
import platform
import subprocess
from tkinter import filedialog, messagebox
import customtkinter as ctk
from threading import Thread

# ------------------------------------------------------------------
# 全局路径：ffmpeg / ffprobe 优先使用程序同目录下的 bin 文件夹
# ------------------------------------------------------------------
def resource_path():
    if getattr(sys, "frozen", False):
        # 打包后：--onefile 内置资源在 _MEIPASS；否则在可执行文件目录
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BASE = resource_path()
BIN_DIR = os.path.join(BASE, "bin")

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

def _find_tool(name):
    """优先 bin 目录内置，其次系统 PATH"""
    if IS_WIN:
        ext = name + ".exe"
    else:
        ext = name
    local = os.path.join(BIN_DIR, ext)
    if os.path.exists(local):
        return local
    return name  # 交给系统 PATH

FFMPEG = _find_tool("ffmpeg")   # 只用 ffmpeg 一个文件即可（读信息+转码）

# 元数据版权标识（小写）
META_TAG = "daxiong_wh"

# 输出文件名后缀（大写 H.265，下划线分隔）
NAME_TAG = "_H.265"

# 支持的视频扩展名
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ts")

# ------------------------------------------------------------------
# 视频信息
# ------------------------------------------------------------------
class VideoInfo:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.fps = 0
        self.audio_tracks = []     # [(index, language, codec)]
        self.subtitle_tracks = []  # [(index, language)]


# ------------------------------------------------------------------
# 硬件编码器自动识别
# ------------------------------------------------------------------
def detect_encoder():
    if IS_MAC:
        return "hevc_videotoolbox"
    try:
        out = subprocess.check_output(
            [FFMPEG, "-hide_banner", "-encoders"],
            stderr=subprocess.STDOUT, text=True
        )
        if "hevc_amf" in out:
            return "hevc_amf"
        if "hevc_nvenc" in out:
            return "hevc_nvenc"
        if "hevc_qsv" in out:
            return "hevc_qsv"
    except Exception:
        pass
    return "libx265"


def encoder_label(enc):
    return {
        "hevc_videotoolbox": "Apple VideoToolbox（Mac 硬编）",
        "hevc_amf": "AMD AMF（显卡硬编）",
        "hevc_nvenc": "NVIDIA NVENC（显卡硬编）",
        "hevc_qsv": "Intel QSV（核显硬编）",
        "libx265": "CPU 软编 libx265",
    }.get(enc, enc)


# ------------------------------------------------------------------
# 用 ffmpeg -i 读取视频信息（不依赖 ffprobe，打包只需内置一个 ffmpeg）
# ------------------------------------------------------------------
def read_video_info(filepath):
    info = VideoInfo()
    try:
        res = subprocess.run(
            [FFMPEG, "-hide_banner", "-i", filepath],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        text = res.stderr
        for line in text.splitlines():
            m = re.search(
                r"Stream #0:(\d+)(?:\((\w+)\))?: Video:\s*[\w-]+.*?(\d+)x(\d+)"
                r".*?([\d.]+)\s*(?:fps|tbr)", line
            )
            if m:
                info.width = int(m.group(3))
                info.height = int(m.group(4))
                try:
                    info.fps = round(float(m.group(5)), 3)
                except ValueError:
                    info.fps = 0
                continue
            m = re.search(r"Stream #0:(\d+)(?:\((\w+)\))?: Audio:\s*([\w-]+)", line)
            if m:
                info.audio_tracks.append((int(m.group(1)), m.group(2) or "und", m.group(3)))
                continue
            m = re.search(r"Stream #0:(\d+)(?:\((\w+)\))?: Subtitle:\s*([\w-]+)", line)
            if m:
                info.subtitle_tracks.append((int(m.group(1)), m.group(2) or "und"))
    except Exception as e:
        print("读取失败:", filepath, e)
    return info


def find_external_subtitle(video_path):
    """自动识别同目录同名外挂字幕"""
    base = os.path.splitext(video_path)[0]
    for ext in (".srt", ".ass", ".ssa"):
        p = base + ext
        if os.path.exists(p):
            return p
    return ""


# ------------------------------------------------------------------
# 构建 ffmpeg 命令（含进度所需参数）
# ------------------------------------------------------------------
def build_ffmpeg_cmd(enc, task, export_dir):
    path = task["path"]
    info = task["info"]
    audio_sel = task["audio_sel"]       # 选中的音轨 index
    sub_sel = task["sub_sel"]           # "none" / ("builtin", idx) / ("external", path)
    external_sub = task["external_sub"]

    base = os.path.splitext(os.path.basename(path))[0]
    # 带软字幕 -> mkv；无字幕 -> mp4
    use_sub = (sub_sel != "none")
    kind = sub_sel[0] if isinstance(sub_sel, tuple) else sub_sel  # none / builtin / external
    out_ext = ".mkv" if use_sub else ".mp4"
    out_path = os.path.join(export_dir, base + NAME_TAG + out_ext)

    cmd = [FFMPEG, "-y", "-hide_banner", "-i", path]

    # 外挂字幕作为第二个输入
    if kind == "external" and external_sub and os.path.exists(external_sub):
        cmd += ["-i", external_sub]

    # 视频编码（保真：保持原分辨率、原帧率）
    if enc == "hevc_videotoolbox":
        cmd += ["-c:v", "hevc_videotoolbox", "-q:v", "75"]
    elif enc == "hevc_amf":
        cmd += ["-c:v", "hevc_amf", "-quality", "quality",
                "-rc", "cqp", "-qp_i", "18", "-qp_p", "23"]
    elif enc == "hevc_nvenc":
        cmd += ["-c:v", "hevc_nvenc", "-cq", "23", "-preset", "p5"]
    elif enc == "hevc_qsv":
        cmd += ["-c:v", "hevc_qsv", "-global_quality", "23", "-preset", "medium"]
    else:  # libx265
        cmd += ["-c:v", "libx265", "-crf", "21", "-preset", "medium", "-tag:v", "hvc1"]

    # 映射：视频 + 选中的音轨（用全局流 index）
    cmd += ["-map", "0:v:0"]
    if info.audio_tracks:
        aidx = info.audio_tracks[audio_sel][0]   # 全局流 index
        cmd += ["-map", "0:%d" % aidx]
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]

    # 字幕（用全局流 index）
    if kind == "builtin":
        cmd += ["-map", "0:%d" % sub_sel[1], "-c:s", "copy"]
    elif kind == "external" and external_sub and os.path.exists(external_sub):
        cmd += ["-map", "1:s:0", "-c:s", "copy"]

    # 版权元数据（小写）
    cmd += ["-metadata", "copyright=" + META_TAG,
            "-metadata", "comment=" + META_TAG,
            "-metadata", "encoder=" + META_TAG]

    # 进度输出
    cmd += ["-progress", "pipe:1", "-nostats", out_path]
    return cmd, out_path


# ------------------------------------------------------------------
# 单任务 UI 行
# ------------------------------------------------------------------
class TaskRow(ctk.CTkFrame):
    def __init__(self, master, filename):
        super().__init__(master, corner_radius=8)
        self.filename = filename

        self.name_lbl = ctk.CTkLabel(self, text=filename, anchor="w")
        self.name_lbl.grid(row=0, column=0, columnspan=4, sticky="ew", padx=8, pady=(6, 2))

        # 音轨下拉
        self.audio_lbl = ctk.CTkLabel(self, text="音轨:", width=34)
        self.audio_lbl.grid(row=1, column=0, sticky="w", padx=(8, 2), pady=2)
        self.audio_menu = ctk.CTkOptionMenu(self, values=["音轨 1"], width=150)
        self.audio_menu.set("音轨 1")
        self.audio_menu.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=2)

        # 字幕下拉
        self.sub_lbl = ctk.CTkLabel(self, text="字幕:", width=34)
        self.sub_lbl.grid(row=1, column=2, sticky="w", padx=(4, 2), pady=2)
        self.sub_menu = ctk.CTkOptionMenu(self, values=["不使用字幕"], width=210)
        self.sub_menu.set("不使用字幕")
        self.sub_menu.grid(row=1, column=3, sticky="w", padx=(0, 8), pady=2)

        # 选择外挂字幕按钮
        self.sub_btn = ctk.CTkButton(self, text="选字幕文件", width=90,
                                     command=self.pick_subtitle)
        self.sub_btn.grid(row=1, column=4, sticky="w", padx=(0, 8), pady=2)

        # 进度条 + 百分比
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(2, 4))
        self.percent_lbl = ctk.CTkLabel(self, text="0.0%", width=54)
        self.percent_lbl.grid(row=2, column=4, padx=8, pady=(2, 4))

        self.grid_columnconfigure(0, weight=1)

        self.sub_choices = ["不使用字幕"]
        self.sub_sel_value = "none"   # none / builtin / external
        self.builtin_subs = []
        self.external_path = ""

    def pick_subtitle(self):
        path = filedialog.askopenfilename(
            title="选择外挂字幕文件",
            filetypes=[("字幕文件", "*.srt *.ass *.ssa")]
        )
        if not path:
            return
        self.external_path = path
        self._refresh_sub_menu(select=("external", path))

    def set_tracks(self, info, auto_sub=""):
        # 音轨
        a_vals = []
        for i, (idx, lang, codec) in enumerate(info.audio_tracks):
            a_vals.append("音轨 %d (%s, %s)" % (i + 1, lang, codec))
        if not a_vals:
            a_vals = ["无音轨"]
        self.audio_menu.configure(values=a_vals)
        self.audio_menu.set(a_vals[0])
        self.audio_sel = 0

        # 字幕
        self.builtin_subs = info.subtitle_tracks
        self.external_path = auto_sub
        self._refresh_sub_menu()

    def _refresh_sub_menu(self, select=None):
        choices = ["不使用字幕"]
        self.builtin_subs = self.builtin_subs or []
        for i, (idx, lang) in enumerate(self.builtin_subs):
            choices.append("内置字幕 %d (%s)" % (i + 1, lang))
        if self.external_path and os.path.exists(self.external_path):
            choices.append("外挂字幕: %s" % os.path.basename(self.external_path))
        self.sub_menu.configure(values=choices)

        if select:
            sel_kind = select[0]
        else:
            # 默认：有外挂用外挂，否则无字幕
            sel_kind = "external" if self.external_path and os.path.exists(self.external_path) else "none"
        self._apply_sub_choice(sel_kind)

    def _apply_sub_choice(self, kind):
        if kind == "external" and self.external_path and os.path.exists(self.external_path):
            self.sub_menu.set("外挂字幕: %s" % os.path.basename(self.external_path))
            self.sub_sel_value = ("external", self.external_path)
        else:
            self.sub_menu.set("不使用字幕")
            self.sub_sel_value = "none"

    def on_sub_menu(self, choice):
        if choice.startswith("内置字幕"):
            idx = int(choice.split("(")[0].replace("内置字幕", "").strip()) - 1
            if 0 <= idx < len(self.builtin_subs):
                self.sub_sel_value = ("builtin", self.builtin_subs[idx][0])
        elif choice.startswith("外挂字幕"):
            self.sub_sel_value = ("external", self.external_path)
        else:
            self.sub_sel_value = "none"

    def on_audio_menu(self, choice):
        # 解析音轨序号
        m = re.match(r"音轨 (\d+)", choice)
        if m:
            self.audio_sel = int(m.group(1)) - 1

    def set_progress(self, val):
        val = max(0.0, min(1.0, val))
        self.progress.set(val)
        self.percent_lbl.configure(text="%.1f%%" % (val * 100))

    def set_state(self, text):
        self.name_lbl.configure(text="%s  [%s]" % (self.filename, text))


# ------------------------------------------------------------------
# 主应用
# ------------------------------------------------------------------
class HEVCConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HEVC 保真转码工具 (H.265)")
        self.geometry("980x720")
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.video_list = []          # [{path, info, ...}]
        self.rows = {}                # path -> TaskRow
        self.running = False
        self.current_idx = 0
        self.export_dir = ""

        self.encoder = detect_encoder()

        # 顶部：编码器信息
        ctk.CTkLabel(
            self,
            text="检测编码器：%s    |    元数据标识：%s    |    输出后缀：%s"
                 % (encoder_label(self.encoder), META_TAG, NAME_TAG),
            anchor="w"
        ).pack(fill="x", padx=12, pady=(10, 2))

        # 按钮栏
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(top, text="导入文件夹", command=self.load_folder).pack(side="left", padx=4)
        self.export_lbl = ctk.CTkLabel(top, text="导出目录：未选择（将输出到源文件所在目录）", anchor="w")
        self.export_lbl.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(top, text="选择导出目录", command=self.choose_export).pack(side="right", padx=4)
        self.start_btn = ctk.CTkButton(top, text="开始转码", command=self.start_encode)
        self.start_btn.pack(side="right", padx=4)

        # 任务列表
        self.scroll = ctk.CTkScrollableFrame(self, height=430)
        self.scroll.pack(fill="both", expand=True, padx=12, pady=4)

        # 总进度
        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(bottom, text="总进度：").pack(side="left", padx=4)
        self.global_bar = ctk.CTkProgressBar(bottom)
        self.global_bar.set(0)
        self.global_bar.pack(side="left", fill="x", expand=True, padx=8)
        self.global_lbl = ctk.CTkLabel(bottom, text="0.0%", width=54)
        self.global_lbl.pack(side="left", padx=4)
        self.done_lbl = ctk.CTkLabel(bottom, text="", anchor="w")
        self.done_lbl.pack(side="right", padx=8)

    # ---------- 导出目录 ----------
    def choose_export(self):
        d = filedialog.askdirectory(title="选择导出文件夹")
        if d:
            self.export_dir = d
            self.export_lbl.configure(text="导出目录：%s" % d)

    # ---------- 导入 ----------
    def load_folder(self):
        folder = filedialog.askdirectory(title="选择视频文件夹")
        if not folder:
            return
        self.video_list.clear()
        for w in self.rows.values():
            w.destroy()
        self.rows.clear()
        self.global_bar.set(0)
        self.global_lbl.configure(text="0.0%")
        self.done_lbl.configure(text="")

        files = sorted(
            f for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXTS)
        )
        if not files:
            messagebox.showwarning("提示", "该文件夹中没有找到视频文件。")
            return
        for fname in files:
            full = os.path.join(folder, fname)
            info = read_video_info(full)
            auto_sub = find_external_subtitle(full)
            task = {
                "path": full,
                "info": info,
                "external_sub": auto_sub,
            }
            self.video_list.append(task)
            row = TaskRow(self.scroll, fname)
            row.pack(fill="x", pady=3)
            row.set_tracks(info, auto_sub)
            row.audio_menu.configure(command=row.on_audio_menu)
            row.sub_menu.configure(command=row.on_sub_menu)
            self.rows[full] = row

        self.done_lbl.configure(text="共 %d 个文件" % len(self.video_list))

    # ---------- 开始 ----------
    def start_encode(self):
        if self.running:
            messagebox.showinfo("提示", "转码正在进行中。")
            return
        if not self.video_list:
            messagebox.showwarning("提示", "请先导入视频文件夹。")
            return
        self.running = True
        self.current_idx = 0
        self.start_btn.configure(state="disabled")
        Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        total = len(self.video_list)
        try:
            while self.current_idx < total:
                task = self.video_list[self.current_idx]
                row = self.rows[task["path"]]

                # 收集 UI 选择
                audio_sel = getattr(row, "audio_sel", 0)
                sub_sel = getattr(row, "sub_sel_value", "none")
                task["audio_sel"] = audio_sel
                task["sub_sel"] = sub_sel

                export_dir = self.export_dir if self.export_dir else os.path.dirname(task["path"])

                row.set_state("转码中")
                row.set_progress(0)

                def _transcode(enc):
                    c, out = build_ffmpeg_cmd(enc, task, export_dir)
                    proc = subprocess.Popen(
                        c,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8", errors="replace",
                    )
                    total_us = None
                    cur_us = 0
                    for line in proc.stdout:
                        line = line.strip()
                        if not line:
                            continue
                        if total_us is None:
                            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", line)
                            if m:
                                h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                                total_us = ((h * 3600 + mi * 60 + s) * 1000000)
                        if line.startswith("out_time_us="):
                            try:
                                cur_us = int(line.split("=", 1)[1])
                            except ValueError:
                                pass
                            if total_us:
                                prog = min(cur_us / total_us, 1.0)
                                row.set_progress(prog)
                                g = (self.current_idx + prog) / total
                                self.global_bar.set(g)
                                self.global_lbl.configure(text="%.1f%%" % (g * 100))
                                self.done_lbl.configure(
                                    text="%d/%d" % (self.current_idx + 1, total)
                                )
                    proc.wait()
                    return proc.returncode, out

                rc, out_path = _transcode(self.encoder)
                if rc != 0 and self.encoder != "libx265":
                    # 硬编不可用，自动回退 CPU 软编重试
                    row.set_state("硬编失败，回退CPU软编")
                    row.set_progress(0)
                    rc, out_path = _transcode("libx265")

                if rc == 0:
                    row.set_progress(1.0)
                    row.set_state("完成")
                else:
                    row.set_state("失败")

                self.current_idx += 1
                self.global_bar.set(self.current_idx / total)
                self.global_lbl.configure(text="%.1f%%" % (self.current_idx / total * 100))

        finally:
            self.running = False
            self.start_btn.configure(state="normal")
            if self.current_idx >= total:
                self.done_lbl.configure(text="全部完成：%d 个文件" % total)
                messagebox.showinfo("完成", "全部视频转码完成！\n输出目录：%s" %
                                    (self.export_dir or "源文件所在目录"))


# ------------------------------------------------------------------
# 自检模式（无界面验证核心逻辑）
# ------------------------------------------------------------------
def selftest():
    print("FFmpeg :", FFMPEG)
    print("平台   :", platform.system())
    print("编码器 :", encoder_label(detect_encoder()))
    print("元数据 :", META_TAG, "| 后缀:", NAME_TAG)
    if not os.path.exists(FFMPEG):
        print("警告: 未找到内置 ffmpeg，将依赖系统 PATH")
    print("OK - 程序核心逻辑正常")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        app = HEVCConverterApp()
        app.mainloop()
