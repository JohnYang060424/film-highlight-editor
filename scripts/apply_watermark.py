# -*- coding: utf-8 -*-
"""成片水印窗口（v12.1 用户钦定）：开头段与结尾段显示右上水印，中间正片干净。
用法: python apply_watermark.py <in.mp4> <wm.png> <out.mp4> [--head 180] [--tail 180] [--alpha 0.9]
默认窗口（成片布局 = intro+正片+outro）：
  头窗口 = [intro后, intro后+head]   即正片开头 head 秒
  尾窗口 = [D-tail-outro, D-outro]   即正片结尾 tail 秒（outro 自带水印位落款，不叠）
  intro 按 3s、outro 按 5s 计（v13 片尾改 5s；--intro/--outro 可调）
水印尺寸 = 主视频宽 12%，右上边距 32/24 按 1080p 比例缩放（与 brand 嵌入规则一致）。
重编码视频 crf18（与流水线一致），音频 copy。
"""
import sys, subprocess, argparse

def probe(path, entries):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries,
                        "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True)
    return [float(x) for x in r.stdout.split()]

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("wm"); ap.add_argument("out")
ap.add_argument("--head", type=float, default=180)
ap.add_argument("--tail", type=float, default=180)
ap.add_argument("--intro", type=float, default=3.0)
ap.add_argument("--outro", type=float, default=5.0)
ap.add_argument("--alpha", type=float, default=0.9)
a = ap.parse_args()

W, H, D = probe(a.inp, "stream=width,height:format=duration")
W, H = int(W), int(H)
wmw = int(W * 0.12)
s = W / 1920.0
mx, my = int(32 * s), int(24 * s)
t0 = a.intro
t1 = a.intro + a.head
t2 = max(t1, D - a.tail - a.outro)
t3 = D - a.outro
expr = f"between(t,{t0:.3f},{t1:.3f})+between(t,{t2:.3f},{t3:.3f})"
print(f"[info] {W}x{H} D={D:.2f}s wm={wmw} win=[{t0:.1f},{t1:.1f}]+[{t2:.1f},{t3:.1f}]")

cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.inp, "-i", a.wm,
       "-filter_complex",
       f"[1:v]scale=w={wmw}:h=-2,colorchannelmixer=aa={a.alpha}[wm];"
       f"[0:v][wm]overlay=x=W-w-{mx}:y={my}:enable='{expr}'[v]",
       "-map", "[v]", "-map", "0:a",
       "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "copy", a.out]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print("[ffmpeg ERROR]", r.stderr[-800:]); sys.exit(1)
print(f"[ok] {a.out}")
