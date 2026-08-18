#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contact_sheet.py — 流程步骤1：全片缩略图 contact sheet
用法:
  python contact_sheet.py <视频> <输出目录> [--interval 60] [--cols 6] [--win 120-300,900-1000] [--win-interval 5]
全片按 interval 秒采样拼 sheet；--win 指定重点窗口按 win-interval 秒密集采样（大图 480x270，便于认人认景）。
输出: sheet_full.png 及 sheet_win_<i>.png。
"""
import argparse, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

def find_font(size):
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()

def fmt_ts(sec):
    h = int(sec // 3600); m = int(sec % 3600 // 60); s = sec % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"

def probe_duration(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)

def sample_frames(video, start, end, interval, thumb_w, thumb_h):
    """返回 [(t, PIL.Image)]。用 fps 滤镜采样，rawvideo 管道读回。"""
    dur = end - start
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", video,
           "-vf", f"fps=1/{interval},scale={thumb_w}:{thumb_h}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.run(cmd, capture_output=True, check=True)
    raw = p.stdout
    frame_bytes = thumb_w * thumb_h * 3
    n = len(raw) // frame_bytes
    frames = []
    for i in range(n):
        img = Image.frombytes("RGB", (thumb_w, thumb_h), raw[i*frame_bytes:(i+1)*frame_bytes])
        t = start + i * interval
        frames.append((t, img))
    return frames

def tile(frames, out_path, cols, thumb_w, thumb_h, caption_h=22):
    if not frames:
        print(f"[skip] 无帧: {out_path}"); return
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + caption_h)), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    font = find_font(caption_h - 4)
    for i, (t, img) in enumerate(frames):
        r, c = divmod(i, cols)
        x, y = c * thumb_w, r * (thumb_h + caption_h)
        sheet.paste(img, (x, y))
        draw.text((x + 4, y + thumb_h + 2), fmt_ts(t), fill=(255, 255, 0), font=font)
    sheet.save(out_path)
    print(f"[ok] {out_path}  ({len(frames)} 帧)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("outdir")
    ap.add_argument("--interval", type=float, default=60, help="全片采样间隔秒，默认60")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--win", default="", help="重点窗口 a-b[,a-b...]")
    ap.add_argument("--win-interval", type=float, default=5)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    dur = probe_duration(a.video)
    print(f"片长 {dur:.1f}s")
    full = sample_frames(a.video, 0, dur, a.interval, 320, 180)
    tile(full, os.path.join(a.outdir, "sheet_full.png"), a.cols, 320, 180)
    if a.win:
        for wi, w in enumerate(a.win.split(",")):
            s, e = [float(x) for x in w.split("-")]
            fr = sample_frames(a.video, s, min(e, dur), a.win_interval, 480, 270)
            tile(fr, os.path.join(a.outdir, f"sheet_win_{wi}.png"), a.cols, 480, 270)

if __name__ == "__main__":
    main()
