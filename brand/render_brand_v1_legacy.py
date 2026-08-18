# -*- coding: utf-8 -*-
"""品牌片头/片尾渲染：logo 动态演绎，3s，黑底，三档分辨率。
用法: python render_brand.py <brand_dir> <res: 720p|1080p|4k|all>
产出: intro_<res>.mp4 / outro_<res>.mp4（编码参数与 cover_loop.py 一致：
25fps libx264 crf18 yuv420p + aac 48k stereo 192k，装配可无缝拼接）

片头演绎：图标放大收拢淡入(0-0.9s) → 文字右滑淡入(0.5-1.3s) → 保持 → 尾0.3s淡出
片尾演绎：整logo淡入居中(0-0.5s) → 「完」淡入(0.9-1.5s) → logo缩移至右上水印位
          (1.7-2.5s,「完」同步淡出) → 保持水印位 → 尾0.2s淡出
"""
import sys, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BRAND, RES = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "all")
SIZES = {"720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}
FPS, SEC = 25, 3.0

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
mw = master.width

def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def with_alpha(img, alpha):
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * alpha))
    img.putalpha(a)
    return img

def scale_img(img, w):
    w = max(2, int(w))
    h = max(2, int(round(w * img.height / img.width)))
    return img.resize((w, h), Image.LANCZOS)

def paste(canvas, img, x, y):
    canvas.alpha_composite(img, (int(round(x)), int(round(y))))

FONT = None
def load_font(px):
    global FONT
    for p in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
        try:
            FONT = ImageFont.truetype(p, int(px)); return FONT
        except Exception:
            continue
    return ImageFont.load_default()

def render(kind, W, H):
    s = W / 1920.0
    mx, my = int(32 * s), int(24 * s)
    n = int(FPS * SEC)
    frames = []
    for f in range(n):
        t = f / FPS
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        g_out = 1.0 - ease((t - (SEC - 0.3 if kind == "intro" else SEC - 0.2)) / (0.3 if kind == "intro" else 0.2))
        if kind == "intro":
            tw = 0.55 * W
            e_i = ease(t / 0.9)
            i_scale = 1.25 - 0.25 * e_i
            iw_full = tw * icon.width / mw
            iw = iw_full * i_scale
            ih = iw * icon.height / icon.width
            tw_t = tw * text.width / mw
            th_t = tw_t * text.height / text.width
            total_h = iw_full * icon.height / icon.width
            cy = (H - total_h) / 2
            ix = (W - tw) / 2
            if e_i > 0:
                paste(canvas, with_alpha(scale_img(icon, iw), e_i * g_out),
                      ix + (iw_full - iw) / 2, cy + (iw_full * icon.height / icon.width - ih) / 2)
            e_t = ease((t - 0.5) / 0.8)
            if e_t > 0:
                paste(canvas, with_alpha(scale_img(text, tw_t), e_t * g_out),
                      ix + iw_full + (1 - e_t) * 40 * s, cy + (total_h - th_t) / 2)
        else:
            e_in = ease(t / 0.5)
            p = ease((t - 1.7) / 0.8)
            tw = W * (0.45 - 0.30 * p)
            th = tw * master.height / mw
            cx = (W - tw) / 2 + p * ((W - mx - tw) - (W - tw) / 2)
            cy = (H - th) / 2 + p * (my - (H - th) / 2)
            if e_in > 0:
                paste(canvas, with_alpha(scale_img(master, tw), e_in * g_out), cx, cy)
            e_w = ease((t - 0.9) / 0.6) * (1 - p)
            if e_w > 0:
                font = load_font(0.06 * H)
                txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(txt)
                d.text((W / 2, H * 0.68), "完", font=font, fill=(255, 255, 255, int(255 * e_w * g_out)), anchor="mm")
                canvas.alpha_composite(txt)
        frames.append(canvas.convert("RGB"))
    return frames

def encode(frames, out, W, H):
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{SEC:.3f}",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
           "-r", str(FPS), "-shortest", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for fr in frames:
        p.stdin.write(np.asarray(fr).tobytes())
    p.stdin.close()
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        print("[ffmpeg ERROR]", err[-800:]); sys.exit(1)
    print(f"[ok] {out}")

res_list = list(SIZES) if RES == "all" else [RES]
for r in res_list:
    W, H = SIZES[r]
    for kind in ["intro", "outro"]:
        encode(render(kind, W, H), f"{BRAND}/{kind}_{r}.mp4", W, H)
print("[done]")
