#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover_loop.py — 流程步骤9：封面图 -> 3s 静音片头 loop
用法:
  python cover_loop.py <cover.png> <out.mp4> [--seconds 3] [--size 1920x1080] [--fps 25]

说明: 封面本体（ImageGen/平台作图 + PIL 叠字）由上层完成，本脚本只负责把
成品封面图转成 3 秒静音视频片头（anullsrc 静音轨）。
"""
import argparse, subprocess, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cover"); ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=25)
    a = ap.parse_args()
    size_filter = a.size.replace("x", ":")
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-loop", "1", "-i", a.cover,
           "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
           "-t", f"{a.seconds:.3f}",
           "-vf", f"scale={size_filter}:force_original_aspect_ratio=decrease,pad={size_filter}:(ow-iw)/2:(oh-ih)/2",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
           "-r", str(a.fps), "-shortest", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg ERROR]", r.stderr[-1000:], file=sys.stderr); sys.exit(1)
    print(f"[ok] {a.out}")

if __name__ == "__main__":
    main()
