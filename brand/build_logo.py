# -*- coding: utf-8 -*-
"""品牌 logo 资产构建：暗底白 logo -> 透明 PNG master + 三档分辨率水印。
用法: python build_logo.py <src_png> <out_dir>
产出:
  logo_master.png   透明底原始分辨率 master（紧裁）
  wm_720p.png       水印档（屏宽12%，v12.1 用户钦定比15%缩小20%）
  wm_1080p.png
  wm_4k.png
  preview_dark_1080p.png / preview_light_1080p.png  嵌入位置预览
"""
import sys
import numpy as np
from PIL import Image

SRC, OUT = sys.argv[1], sys.argv[2]

im = Image.open(SRC).convert("RGB")
a = np.asarray(im).astype(np.float32)
R, G, B = a[..., 0], a[..., 1], a[..., 2]
luma = 0.299 * R + 0.587 * G + 0.114 * B
h, w = luma.shape

corners = np.concatenate([
    luma[:12, :12].ravel(), luma[:12, -12:].ravel(),
    luma[-12:, :12].ravel(), luma[-12:, -12:].ravel()])
bg = float(np.median(corners))
print(f"[info] size={w}x{h} bg_luma={bg:.1f} max={luma.max():.1f}")

lo, hi = min(bg + 30, 60), 210.0
alpha = np.clip((luma - lo) / (hi - lo), 0, 1)
alpha = (alpha ** 0.9) * 255.0

rgba = np.empty((h, w, 4), dtype=np.uint8)
rgba[..., 0] = 255
rgba[..., 1] = 255
rgba[..., 2] = 255
rgba[..., 3] = alpha.astype(np.uint8)

mask = alpha > 12
ys, xs = np.where(mask)
y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
print(f"[info] crop bbox x[{x0},{x1}] y[{y0},{y1}]")
master = Image.fromarray(rgba[y0:y1 + 1, x0:x1 + 1], "RGBA")
mw, mh = master.size
print(f"[info] master {mw}x{mh} ratio={mw / mh:.2f}")
master.save(f"{OUT}/logo_master.png")

for tag, screen_w in [("720p", 1280), ("1080p", 1920), ("4k", 3840)]:
    tw = int(screen_w * 0.12)
    th = int(round(tw * mh / mw))
    small = master.resize((tw, th), Image.LANCZOS)
    small.save(f"{OUT}/wm_{tag}.png")
    print(f"[ok] wm_{tag}.png {tw}x{th}")

pw, ph = 1920, 1080
wm = Image.open(f"{OUT}/wm_1080p.png")
ww, wh = wm.size
margin_x, margin_y = 32, 24
for name, bgcol in [("dark", (18, 20, 26)), ("light", (228, 226, 218))]:
    canvas = Image.new("RGB", (pw, ph), bgcol)
    canvas.paste(wm, (pw - ww - margin_x, margin_y), wm)
    canvas.save(f"{OUT}/preview_{name}_1080p.png")
    print(f"[ok] preview_{name}_1080p.png")
print("[done]")
