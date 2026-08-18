# -*- coding: utf-8 -*-
"""cutprobe_sheet.py —— 切点探针（v13.2 硬流程，定剪前必做）

背景：contact_sheet 的时间戳标签可能系统性漂移（实测 part3 标签比真实早 ~6min），
"抽帧目核定切点"若只依赖带标签的 sheet = 拿错地图走。
本脚本对【定稿的切点清单】实时逐点抽帧，拼成带真实时间标签的校验 sheet，
用真实画面确认每个切点确实落在预期桥段上，再进 cut_sync。

规则（v13.2 钦定）：sheet 只做粗定位；定剪前必须跑本探针并目核全部切点帧。

用法：
  python cutprobe_sheet.py <video> <clips_snap.json> [--out probe_sheet.png]
                            [--cols 6] [--w 320]
  对 clips_snap.json 里每段的 s（入点）与 e（出点）各抽一帧，
  标签写真实秒数与 mm:ss，拼成 grid。

产物：probe_sheet.png（及逐帧 jpg 缓存目录 _cutprobe/）
"""
import argparse
import json
import os
import subprocess
import sys

FF = "ffmpeg"


def probe_frame(video, t, w, out):
    subprocess.run(
        [FF, "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video,
         "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "3", out, "-y"],
        check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("clips", help="clips_snap.json（吸附后切点）")
    ap.add_argument("--out", default="probe_sheet.png")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--w", type=int, default=320)
    a = ap.parse_args()

    from PIL import Image, ImageDraw, ImageFont

    clips = json.load(open(a.clips, encoding="utf-8"))
    pts = []
    for seg in clips:
        pts.append((float(seg["s"]), f"{seg['name']}-IN"))
        pts.append((float(seg["e"]), f"{seg['name']}-OUT"))

    chh = int(a.w * 9 / 16)
    rows = (len(pts) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (a.cols * a.w, rows * (chh + 26)), (10, 10, 10))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
    except OSError:
        f = ImageFont.load_default()

    os.makedirs("_cutprobe", exist_ok=True)
    for i, (t, tag) in enumerate(pts):
        p = os.path.join("_cutprobe", f"{i:03d}.jpg")
        probe_frame(a.video, t, a.w, p)
        im = Image.open(p).convert("RGB")
        x, y = (i % a.cols) * a.w, (i // a.cols) * (chh + 26)
        sheet.paste(im, (x, y + 26))
        mm, ss = divmod(int(t), 60)
        d.text((x + 6, y + 2), f"{tag} {t:.2f}s {mm:02d}:{ss:02d}",
               font=f, fill=(255, 215, 0))

    sheet.save(a.out)
    print(f"[cutprobe] {len(pts)} 切点帧 -> {a.out}（请逐一目核）")


if __name__ == "__main__":
    main()
