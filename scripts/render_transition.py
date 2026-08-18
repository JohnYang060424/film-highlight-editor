#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_transition.py — 流程步骤8：转场解说视频（PIL 渲染长条 + ffmpeg 滚动）
用法:
  python render_transition.py --title "第一章 起因" --text "解说文本…" \
      --audio audio/trans_01.mp3 --out trans_01.mp4 [--fps 25] [--size 1920x1080]

步骤（与 SKILL.md 一致）:
  1) PIL 渲染透明长条 PNG：金色章名(#FFD700) + 白色正文，黑底可读；
     左右各留 10% 边距（pad_x = width*0.10）。
  2) PIL 渲染垂直淡入淡出遮罩 PNG（黑底+alpha 梯度）：
     顶部 0~10% alpha=255（绝对空黑）、10%~16% alpha 255→0 线性淡入；
     底部镜像（84%~90% 淡出、90%~100% 绝对空黑）。
     即滚动显示区=中间 80%（含两端各 6% 的软淡入淡出带），
     上下各 10% 永远空黑，文字绝不顶天立地。
  3) ffmpeg color=black + overlay 长条 + overlay 遮罩
     speed = (video_h + strip_h) / (audio_dur + 1.0)
  4) -r 锁定帧率；x264 crf18 + AAC 立体声 48k 192k。
"""
import argparse, os, subprocess, sys, textwrap
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]

def load_font(size):
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    raise FileNotFoundError("未找到中文字体，请确认 Windows/Fonts 下有 msyh*.ttc")

def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)

def wrap_text(text, font, max_width, draw):
    """按像素宽度软换行。"""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_width:
            cur += ch
        else:
            if cur: lines.append(cur)
            cur = ch
    if cur: lines.append(cur)
    return lines

def build_mask(width, height, workdir):
    """垂直安全区遮罩：黑底 + alpha 梯度。
    0~10%   alpha=255（顶边绝对空黑）
    10~16%  alpha 255->0（软淡入，滚动区上界）
    84~90%  alpha 0->255（软淡出，滚动区下界）
    90~100% alpha=255（底边绝对空黑）
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    top = int(height * 0.10); fade = int(height * 0.06)
    bot = int(height * 0.90)
    for y in range(height):
        if y < top or y >= bot:
            a = 255
        elif y < top + fade:
            a = int(255 * (top + fade - y) / fade)
        elif y >= bot - fade:
            a = int(255 * (y - (bot - fade)) / fade)
        else:
            a = 0
        row = Image.new("RGBA", (width, 1), (0, 0, 0, a))
        img.paste(row, (0, y))
    png = os.path.join(workdir, "mask.png")
    img.save(png)
    return png

def build_strip(title, text, width, workdir):
    title_font = load_font(72)
    body_font = load_font(46)
    tmp = Image.new("RGBA", (width, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    pad_x = int(width * 0.10)
    body_w = width - pad_x * 2
    lines = wrap_text(text, body_font, body_w, d)
    line_h = int(46 * 1.7)
    title_h = 72 + 40
    strip_h = title_h + line_h * len(lines) + 80
    strip = Image.new("RGBA", (width, strip_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(strip)
    # 章名居中金色
    d.text(((width - d.textlength(title, font=title_font)) / 2, 40),
           title, fill=(255, 215, 0, 255), font=title_font)
    # 正文居中白色
    y = title_h + 20
    for ln in lines:
        d.text(((width - d.textlength(ln, font=body_font)) / 2, y),
               ln, fill=(255, 255, 255, 255), font=body_font)
        y += line_h
    png = os.path.join(workdir, "strip.png")
    strip.save(png)
    return png, strip_h

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--size", default="1920x1080")
    a = ap.parse_args()
    w, h = [int(x) for x in a.size.split("x")]
    workdir = os.path.dirname(os.path.abspath(a.out)) or "."
    os.makedirs(workdir, exist_ok=True)
    adur = audio_duration(a.audio)
    png, strip_h = build_strip(a.title, a.text, w, workdir)
    mask = build_mask(w, h, workdir)
    speed = (h + strip_h) / (adur + 1.0)
    total = adur + 1.0
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={a.fps}:d={total:.3f}",
           "-i", png, "-i", mask, "-i", a.audio,
           "-filter_complex",
           f"[0:v][1:v]overlay=x=0:y='H-t*{speed:.4f}'[sc];[sc][2:v]overlay=0:0[v]",
           "-map", "[v]", "-map", "3:a",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
           "-r", str(a.fps), "-shortest", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg ERROR]", r.stderr[-1000:], file=sys.stderr); sys.exit(1)
    print(f"[ok] {a.out}  ({total:.1f}s, strip_h={strip_h}, speed={speed:.1f}px/s)")

if __name__ == "__main__":
    main()
