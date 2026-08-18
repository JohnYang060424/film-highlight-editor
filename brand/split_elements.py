# -*- coding: utf-8 -*-
"""logo 元素拆分：master -> 翅膀 / 电影胶圈 / 文字 三张透明 PNG。
用法: python split_elements.py <brand_dir> [--inspect]
--inspect 只输出 icon 放大图与统计，不做拆分（用于定几何参数）。
拆分几何（相对 icon bbox 的比例）在 INSPECT 后硬编码于下方 GEO。
"""
import sys
import numpy as np
from PIL import Image

BRAND = sys.argv[1]
INSPECT = "--inspect" in sys.argv

master = Image.open(f"{BRAND}/logo_master.png").convert("RGBA")
arr = np.asarray(master)
colmask = arr[..., 3].sum(axis=0)
zero = colmask == 0
best = cur = 0
bs = cs = 0
for i, z in enumerate(zero):
    if z:
        cur += 1
        if cur > best:
            best, bs = cur, i - cur + 1
    else:
        cur = 0
split = bs + best // 2
icon = master.crop((0, 0, split, master.height))
text = master.crop((split, 0, master.width, master.height))
iw, ih = icon.size
print(f"[info] master {master.size} icon {icon.size} text {text.size}")

ia = np.asarray(icon)[..., 3]
ys, xs = np.where(ia > 12)
print(f"[info] icon bbox x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]")

if INSPECT:
    big = icon.resize((iw * 6, ih * 6), Image.NEAREST)
    big.save(f"{BRAND}/icon_big.png")
    # 列轮廓：每列 alpha>12 像素的 y 范围，辅助判断圆环位置
    for cx in range(0, iw, 4):
        col = np.where(ia[:, cx] > 12)[0]
        if len(col):
            print(f"x={cx:3d} y[{col.min():3d},{col.max():3d}] n={len(col):3d}")
        else:
            print(f"x={cx:3d} -")
    print("[inspect done]")
    sys.exit(0)

# ---- 拆分几何（相对 icon 宽高比例，inspect 后核定）----
# 圆环中心/半径（比例），翅膀 = icon - 圆盘
GEO = {"cx": 0.66, "cy": 0.58, "r": 0.445}
cx = GEO["cx"] * iw
cy = GEO["cy"] * ih
r = GEO["r"] * ih
yy, xx = np.mgrid[0:ih, 0:iw]
disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2

icon_arr = np.asarray(icon).copy()
wing_arr = icon_arr.copy()
reel_arr = icon_arr.copy()
wing_arr[disk] = [0, 0, 0, 0]          # 翅膀 = 盘外
# reel = 完整图标（含翅作底层）：单飞时轮廓完整；翅膀落位后完全重合覆盖，无缝
Image.fromarray(wing_arr).save(f"{BRAND}/el_wing.png")
Image.fromarray(reel_arr).save(f"{BRAND}/el_reel.png")
text.save(f"{BRAND}/el_text.png")
print(f"[ok] el_wing / el_reel (disk c=({cx:.0f},{cy:.0f}) r={r:.0f}) / el_text")
