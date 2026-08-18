# -*- coding: utf-8 -*-
"""品牌片头/片尾 v2：打散组装+回弹+伪3D 开场感；片尾新文案+单色emoji。
用法: python render_brand_v2.py <brand_dir> <res: 720p|1080p|4k|all> [intro|outro|all]
产出: intro_<res>.mp4 / outro_<res>.mp4（25fps libx264 crf18 yuv420p + aac48k192k，
与 cover_loop/cut_sync 同参数，assemble normalize 无缝）

片头 v2 时间线（3s）：
  reel  0.10-0.95  深处放大旋入(scale3.0->1, spin -540deg) 落位回弹
  wing  0.35-1.15  左侧翻入(flipx 0.25->1, rot -14->0) 落位回弹
  chars 0.55+i*.12 四散飞入(scale1.6->1, 随机角->0) 落位回弹
  flash 1.55       光晕+扩散光环冲击波
  2.7-3.0 淡出
  伪3D：scale=纵深、元素投影随"高度"变化、reel 旋转/wing 水平翻转模拟三维翻入
片尾 v2.1 时间线（5s，从容版）：
  0-0.6   logo 回弹淡入，居中偏上(0.40H)
  0.9-1.4 「本集完～」升起
  1.5/1.75/2.0/2.35 底行四组依次升起：👍点赞(金) 💬留言(青) ➕关注(珊瑚) ——尾巴(灰)
          「本集完」与底行之间空一行，三色图标不密集
  2.4-3.8 静态停留供阅读
  3.8-4.3 文案淡出；3.8-4.7 logo 缩移右上水印位
  4.75-5.0 淡出
"""
import sys, subprocess, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BRAND = sys.argv[1]
RES = sys.argv[2] if len(sys.argv) > 2 else "all"
WHICH = sys.argv[3] if len(sys.argv) > 3 else "all"
SIZES = {"720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}
FPS = 25
SEC_INTRO, SEC_OUTRO = 3.0, 5.0

wing0 = Image.open(f"{BRAND}/el_wing.png").convert("RGBA")
reel0 = Image.open(f"{BRAND}/el_reel.png").convert("RGBA")
text0 = Image.open(f"{BRAND}/el_text.png").convert("RGBA")

# ---- 文字条按字拆分 ----
ta = np.asarray(text0)[..., 3]
colsum = ta.sum(axis=0)
chars = []
in_c = False
for i, v in enumerate(colsum > 0):
    if v and not in_c:
        cs = i
        in_c = True
    elif not v and in_c:
        chars.append(text0.crop((cs, 0, i, text0.height)))
        in_c = False
if in_c:
    chars.append(text0.crop((cs, 0, text0.width, text0.height)))
print(f"[info] chars={len(chars)} sizes={[c.size for c in chars]}")

# ---- 预渲染光晕/光环 ----
G = 512
glow = Image.new("RGBA", (G, G), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
yy, xx = np.mgrid[0:G, 0:G]
rr = np.sqrt((xx - G / 2) ** 2 + (yy - G / 2) ** 2) / (G / 2)
ga = np.clip(1 - rr, 0, 1) ** 2.2 * 255
garr = np.zeros((G, G, 4), dtype=np.uint8)
garr[..., 0] = 255
garr[..., 1] = 250
garr[..., 2] = 240
garr[..., 3] = ga.astype(np.uint8)
glow = Image.fromarray(garr)
ring = Image.new("RGBA", (G, G), (0, 0, 0, 0))
rd = ImageDraw.Draw(ring)
rd.ellipse([G * 0.40, G * 0.40, G * 0.60, G * 0.60], outline=(255, 255, 255, 255), width=10)
ring = ring.filter(ImageFilter.GaussianBlur(6))

vign = {}


def get_vign(W, H):
    key = (W, H)
    if key not in vign:
        yy, xx = np.mgrid[0:H, 0:W]
        rx = (xx - W / 2) / (W / 2)
        ry = (yy - H / 2) / (H / 2)
        r = np.sqrt(rx ** 2 + ry ** 2) / np.sqrt(2)
        a = (np.clip(r, 0, 1) ** 2 * 46).astype(np.uint8)
        arr = np.zeros((H, W, 4), dtype=np.uint8)
        arr[..., 3] = a
        vign[key] = Image.fromarray(arr)
    return vign[key]


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def eob(t):  # easeOutBack 过冲
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def bounce(u, amp=0.12, decay=6.5, freq=13.0):
    return amp * math.exp(-decay * u) * math.sin(freq * u) if u > 0 else 0.0


def xform(img, scale, angle=0.0, fx=1.0, alpha=1.0):
    w0, h0 = img.size
    fw = max(2, int(w0 * abs(fx) * scale))
    fh = max(2, int(h0 * scale))
    im = img.resize((fw, fh), Image.LANCZOS)
    if angle:
        im = im.rotate(angle, expand=True, resample=Image.BICUBIC)
    if alpha < 1.0:
        r, g, b, a = im.split()
        a = a.point(lambda v: int(v * alpha))
        im.putalpha(a)
    return im


def shadow_of(img, salpha):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    a = img.split()[3]
    sh.putalpha(a.point(lambda v: int(v * salpha)))
    return sh


def paste_c(canvas, img, cx, cy, shadow=0.0, sh_dy=0):
    w, h = img.size
    x, y = int(round(cx - w / 2)), int(round(cy - h / 2))
    if shadow > 0:
        canvas.alpha_composite(shadow_of(img, shadow), (x, y + int(sh_dy)))
    canvas.alpha_composite(img, (x, y))


FONT_ZH, FONT_EMO = None, None


def font_zh(px):
    global FONT_ZH
    FONT_ZH = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", int(px))
    return FONT_ZH


def font_emo(px):
    global FONT_EMO
    FONT_EMO = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", int(px))
    return FONT_EMO


def mixed_width(segs):
    return sum(item[0].getlength(item[1]) for item in segs)


def draw_mixed(canvas, segs, cx, y_baseline, alpha):
    # segs 元素: (font, text) 或 (font, text, (r,g,b))
    tot = sum(f.getlength(s) for f, s, *_ in segs)
    x = cx - tot / 2
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for item in segs:
        f, s = item[0], item[1]
        col = item[2] if len(item) > 2 else (255, 255, 255)
        d.text((x, y_baseline), s, font=f, fill=(col[0], col[1], col[2], 255))
        x += f.getlength(s)
    if alpha < 1.0:
        r, g, b, a = layer.split()
        layer.putalpha(a.point(lambda v: int(v * alpha)))
    canvas.alpha_composite(layer)


# 三色图标：点赞金 / 留言青 / 关注珊瑚；正文白；尾巴暖灰
GOLD, CYAN, CORAL, DIM = (240, 196, 92), (112, 214, 224), (242, 140, 132), (170, 162, 150)
L2_GROUPS = None


def line2_groups(px_zh):
    # 四个依次升起的小组：(图标+词) x3 + 尾巴
    global L2_GROUPS
    if L2_GROUPS is None or L2_GROUPS[0] != px_zh:
        fz, fe = font_zh(px_zh), font_emo(int(px_zh * 1.12))
        L2_GROUPS = (px_zh, [
            [(fe, "👍", GOLD), (fz, " 点赞", GOLD)],
            [(fe, "💬", CYAN), (fz, " 留言", CYAN)],
            [(fe, "➕", CORAL), (fz, " 关注", CORAL)],
            [(fz, "——  翅膀下的风，谢啦 ", DIM), (fe, "✨", DIM)],
        ])
    return L2_GROUPS[1]


def render_intro(W, H):
    s = W / 1920.0
    SEC = SEC_INTRO
    n = int(FPS * SEC)
    # 目标布局：整 logo 宽 0.55W 居中
    icon_w0 = wing0.width
    tw = 0.55 * W
    k = tw / (icon_w0 + text0.width)
    # 各元素目标尺寸（统一按 k 缩放）
    def tgt(im):
        return im.resize((max(2, int(im.width * k)), max(2, int(im.height * k))), Image.LANCZOS)
    wing_t, reel_t = tgt(wing0), tgt(reel0)
    char_t = [tgt(c) for c in chars]
    icon_h = wing_t.height
    cy0 = H / 2
    ix0 = (W - tw) / 2  # icon 左缘
    # icon = wing/reel 同 bbox 叠合；文字字块依次排
    wing_c = (ix0 + icon_w0 * k / 2, cy0)
    reel_c = (ix0 + icon_w0 * k / 2, cy0)
    cx = ix0 + icon_w0 * k
    char_c = []
    for c in char_t:
        pad = 0.006 * W
        cx += pad
        char_c.append((cx + c.width / 2, cy0))
        cx += c.width + pad
    frames = []
    for f in range(n):
        t = f / FPS
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        canvas.alpha_composite(get_vign(W, H))
        g_out = 1.0 - ease((t - (SEC - 0.3)) / 0.3)
        # reel：深处旋入
        p = ease((t - 0.10) / 0.85)
        if p > 0:
            u = max(0.0, t - 0.95)
            sc = (3.0 - 2.0 * p) * (1 + bounce(u, 0.14))
            ang = -540 * (1 - p)
            al = min(1.0, p / 0.4) * g_out
            ox, oy = -0.22 * W * (1 - p), -0.28 * H * (1 - p)
            im = xform(reel_t, sc, ang, 1.0, al)
            paste_c(canvas, im, reel_c[0] + ox, reel_c[1] + oy,
                    shadow=0.30 * al, sh_dy=10 * s * max(0.2, sc - 0.8))
        # wing：左侧翻入
        p = ease((t - 0.35) / 0.80)
        if p > 0:
            u = max(0.0, t - 1.15)
            sc = (1.5 - 0.5 * p) * (1 + bounce(u, 0.12))
            fx = 0.25 + 0.75 * p
            ang = -14 * (1 - p)
            al = min(1.0, p / 0.35) * g_out
            ox = -0.45 * W * (1 - p)
            im = xform(wing_t, sc, ang, fx, al)
            paste_c(canvas, im, wing_c[0] + ox, wing_c[1],
                    shadow=0.28 * al, sh_dy=9 * s * max(0.2, sc - 0.8))
        # 文字：四散飞入
        offs = [(0.30, -0.32), (-0.18, 0.36), (0.34, 0.26), (-0.24, -0.34)]
        angs = [18, -16, 14, -18]
        for i, c in enumerate(char_t):
            p = ease((t - (0.55 + i * 0.12)) / 0.55)
            if p > 0:
                u = max(0.0, t - (1.10 + i * 0.12))
                sc = (1.6 - 0.6 * p) * (1 + bounce(u, 0.15))
                al = min(1.0, p / 0.4) * g_out
                ox, oy = offs[i][0] * W * (1 - p), offs[i][1] * H * (1 - p)
                im = xform(c, sc, angs[i] * (1 - p), 1.0, al)
                paste_c(canvas, im, char_c[i][0] + ox, char_c[i][1] + oy)  # 文字不投影，防光晕亮场露黑影
        # 冲击波光晕+光环
        u = t - 1.55
        if u > 0:
            a_g = max(0.0, 0.85 * math.exp(-4.5 * u)) * g_out
            sz = (0.35 + 1.5 * ease(min(1, u / 0.5))) * W * 0.5
            im = xform(glow, sz / G, 0, 1.0, a_g)
            paste_c(canvas, im, W / 2, H / 2)
            a_r = max(0.0, 0.9 * math.exp(-3.5 * u)) * g_out
            szr = (0.15 + 1.9 * ease(min(1, u / 0.7))) * W * 0.5
            im = xform(ring, szr / G, 0, 1.0, a_r)
            paste_c(canvas, im, W / 2, H / 2)
        # 冲击波瞬间整屏震屏（开场震撼感）
        u_s = t - 1.55
        if u_s > 0:
            amp = 9 * s * math.exp(-5.0 * u_s)
            sx = amp * math.sin(2 * math.pi * 17 * u_s)
            sy = amp * math.cos(2 * math.pi * 13 * u_s)
            outc = Image.new("RGBA", (W, H), (0, 0, 0, 255))
            outc.alpha_composite(canvas, (int(round(sx)), int(round(sy))))
            canvas = outc
        frames.append(canvas.convert("RGB"))
    return frames


def render_outro(W, H):
    s = W / 1920.0
    SEC = SEC_OUTRO
    mx, my = int(32 * s), int(24 * s)
    n = int(FPS * SEC)
    mw0 = wing0.width + text0.width
    full = Image.new("RGBA", (mw0, wing0.height), (0, 0, 0, 0))
    full.alpha_composite(wing0)
    full.alpha_composite(reel0)
    full.alpha_composite(text0, (wing0.width, 0))
    groups = line2_groups(0.037 * H)
    gws = [mixed_width(g) for g in groups]
    gap_g = 0.045 * W
    row_w = sum(gws) + gap_g * 3
    x0 = (W - row_w) / 2
    g_cx = []
    ax = x0
    for w in gws:
        g_cx.append(ax + w / 2)
        ax += w + gap_g
    # 时间锚点
    T_LOGO_IN, T_L1, T_G = 0.6, 0.9, [1.5, 1.75, 2.0, 2.35]
    T_TXT_OUT, T_MOVE, T_FADE = 3.8, 3.8, 4.75
    frames = []
    for f in range(n):
        t = f / FPS
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        canvas.alpha_composite(get_vign(W, H))
        g_out = 1.0 - ease((t - T_FADE) / (SEC - T_FADE))
        p = ease((t - T_MOVE) / 0.9)
        e_in = eob(t / T_LOGO_IN) if t > 0 else 0
        tw = W * (0.42 - 0.30 * p)
        th = tw * wing0.height / mw0
        cx = (W - tw) / 2 + p * ((W - mx - tw) - (W - tw) / 2)
        cy = (H - th) / 2 - 0.10 * H + p * (my - ((H - th) / 2 - 0.10 * H))
        sc = (0.92 + 0.08 * min(1, e_in)) * (1 + bounce(max(0.0, t - T_LOGO_IN), 0.06))
        if e_in > 0:
            im = xform(full, tw / mw0 * sc, 0, 1.0, min(1, e_in) * g_out)
            paste_c(canvas, im, cx + tw / 2, cy + th / 2, shadow=0.22, sh_dy=8 * s)
        # 文案独立淡出（3.8-4.3s），与 logo 移走同步
        txt_out = 1.0 - ease((t - T_TXT_OUT) / 0.5)
        # 「本集完～」
        e1 = ease((t - T_L1) / 0.5) * txt_out
        if e1 > 0:
            f1 = font_zh(0.056 * H)
            draw_mixed(canvas, [(f1, "本集完～")], W / 2,
                       H * 0.615 + (1 - min(1, ease((t - T_L1) / 0.5))) * 30 * s, e1)
        # 底行四组依次升起（三色）
        for i, g in enumerate(groups):
            e2 = ease((t - T_G[i]) / 0.5) * txt_out
            if e2 > 0:
                draw_mixed(canvas, g, g_cx[i],
                           H * 0.775 + (1 - min(1, ease((t - T_G[i]) / 0.5))) * 26 * s, e2)
        frames.append(canvas.convert("RGB"))
    return frames


def encode(frames, out, W, H, sec):
    # v13.4：优先混入品牌音效（render_brand_audio.py 产出），无则静音（向后兼容）
    wav = None
    if "intro" in os.path.basename(out):
        cand = f"{BRAND}/intro_audio.wav"
    else:
        cand = f"{BRAND}/outro_audio.wav"
    if os.path.exists(cand):
        wav = cand
    if wav:
        ain = ["-i", wav]
    else:
        ain = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    cmd += ain
    cmd += ["-t", f"{sec:.3f}",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            "-r", str(FPS), "-shortest", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for fr in frames:
        proc.stdin.write(np.asarray(fr).tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        print("[ffmpeg ERROR]", err[-800:]); sys.exit(1)
    print(f"[ok] {out}")


res_list = list(SIZES) if RES == "all" else [RES]
for r in res_list:
    W, H = SIZES[r]
    if WHICH in ("all", "intro"):
        encode(render_intro(W, H), f"{BRAND}/intro_{r}.mp4", W, H, SEC_INTRO)
    if WHICH in ("all", "outro"):
        encode(render_outro(W, H), f"{BRAND}/outro_{r}.mp4", W, H, SEC_OUTRO)
print("[done]")
