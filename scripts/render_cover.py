#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_cover.py — B站爆款封面模板（参考图版式基因，2026-09-07 定版）

版式规范（照爆款参考图复刻）：
  · 背景：正片人物面部有戏剧张力的一帧；裁掉原片硬字幕行；文字侧压暗蒙版
  · 标题：横排 2 行、等大粗黑体、左对齐、占右半幅（x≈46% 起）
  · 双色字：白=铺垫/连接词，黄=强调钩子（两行黄色连读=完整悬念句），句末 !/？
  · 描边：粗黑 stroke + 高斯投影；左上红底白字片名/导演小标签
用法（Windows 中文路径安全：全部 Python 内处理，不走 shell 转义）:
  python render_cover.py --bg frame.jpg --out cover.png \
    --line1 "他认定新邻居是:特务" --line2 "一盯就是:40年" \
    --tag "冯小刚导演《抓特务》" [--fontsize 175] [--accent FFE600]
冒号左边白字、右边强调字；也可整行无冒号=全白。
"""
import argparse, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
FONT_CANDIDATES = [
    r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\simhei.ttf',
    r'C:\Windows\Fonts\Dengb.ttf', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]

def pick_font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    raise SystemExit('[FATAL] 找不到中文字体（msyhbd/simhei/wqy）')

def split_hook(s):
    """'白字:强调字' -> (white, accent)；无冒号则强调段为空。"""
    if ':' in s:
        w, a = s.split(':', 1)
        return w, a
    return s, ''

def text_with_shadow(draw_layer, xy, s, font, fill, stroke, shadow_off=(10, 14), blur=6):
    """在 RGBA 层画粗描边字 + 同形投影（投影单独羽化后先贴）。"""
    sh = Image.new('RGBA', draw_layer.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.text((xy[0] + shadow_off[0], xy[1] + shadow_off[1]), s, font=font,
            fill=(0, 0, 0, 205), stroke_width=stroke, stroke_fill=(0, 0, 0, 205))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    draw_layer.alpha_composite(sh)
    ImageDraw.Draw(draw_layer).text(xy, s, font=font, fill=fill,
                                    stroke_width=stroke, stroke_fill=(8, 8, 8, 255))

def draw_line(layer, x, y, segs, font, stroke):
    """segs=[(text,(r,g,b,a)),...] 依次绘制，返回结束 x。"""
    for txt, col in segs:
        text_with_shadow(layer, (x, y), txt, font, col + (255,), stroke)
        x += font.getlength(txt)
    return x

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bg', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--line1', required=True, help='"白:强调" 两段式')
    ap.add_argument('--line2', required=True)
    ap.add_argument('--tag', default='', help='左上红底白字标签（片名/导演）')
    ap.add_argument('--fontsize', type=int, default=175)
    ap.add_argument('--accent', default='FFE600', help='强调字色，默认爆款黄')
    ap.add_argument('--accent2', default='FF3B30', help='标签红底')
    ap.add_argument('--cropsub', type=float, default=0.87,
                    help='裁掉底部字幕行比例(保留高度占比)，0=不裁')
    ap.add_argument('--anchor', default='right', choices=['right', 'left'],
                    help='标题块靠哪侧（背景人物在另一侧）')
    a = ap.parse_args()

    accent = tuple(int(a.accent[i:i+2], 16) for i in (0, 2, 4))
    tagred = tuple(int(a.accent2[i:i+2], 16) for i in (0, 2, 4))

    # 1) 背景：加载→裁硬字幕→铺满 1920x1080
    bg = Image.open(a.bg).convert('RGB')
    if a.cropsub and a.cropsub < 1:
        ch = int(bg.height * a.cropsub)
        crop_top = max(0, (bg.height - ch) // 2)   # 居中保面部
        bg = bg.crop((0, crop_top, bg.width, crop_top + ch))
    bg = bg.resize((W, H), Image.Resampling.LANCZOS)
    canvas = bg.convert('RGBA')

    # 2) 文字侧压暗横向渐变蒙版（60%→100% 宽度线性加深到 alpha 170）
    mask = Image.new('L', (W, H), 0)
    md = ImageDraw.Draw(mask)
    x0, x1 = int(W * 0.40), int(W * 0.72)
    for x in range(x0, W):
        alpha = min(170, int(170 * (x - x0) / max(1, x1 - x0)))
        md.line([(x, 0), (x, H)], fill=alpha)
    if a.anchor == 'left':
        mask = mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    black = Image.new('RGBA', (W, H), (6, 6, 10, 255))
    canvas.paste(black, (0, 0), mask)

    # 3) 两行大标题：自动缩字号保证两行都不超右半幅(≥86%宽收边)
    tx = int(W * (0.40 if a.anchor == 'right' else 0.05))
    maxw = W - tx - int(W * 0.07) - 40
    fs = a.fontsize
    while fs > 90:
        f = pick_font(fs)
        l1w = f.getlength(a.line1.replace(':', ''))
        l2w = f.getlength(a.line2.replace(':', ''))
        if max(l1w, l2w) <= maxw:
            break
        fs -= 5
    f = pick_font(fs)
    stroke = max(8, fs // 14)
    lh = int(fs * 1.18)
    block_h = lh * 2
    y0 = int(H * 0.42) - block_h // 2 + int(fs * 0.35)

    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    w1, a1 = split_hook(a.line1)
    w2, a2 = split_hook(a.line2)
    draw_line(layer, tx, y0, [(w1, (255, 255, 255)), (a1, accent)], f, stroke)
    draw_line(layer, tx, y0 + lh, [(w2, (255, 255, 255)), (a2, accent)], f, stroke)
    canvas.alpha_composite(layer)

    # 4) 左上红底白字标签
    if a.tag:
        tf = pick_font(int(fs * 0.36))
        tw = tf.getlength(a.tag)
        pad_x, pad_y = int(tw * 0.06) + 18, 14
        bx, by = int(W * 0.045), int(H * 0.075)   # 永远左上角，与右下标题对角平衡
        lab = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lab)
        ld.rounded_rectangle([bx, by, bx + tw + pad_x * 2, by + tf.size + pad_y * 2],
                             radius=12, fill=tagred + (255,))
        ld.text((bx + pad_x, by + pad_y - 4), a.tag, font=tf, fill=(255, 255, 255, 255))
        canvas.alpha_composite(lab)

    # 5) 输出 png + jpg(95)
    out = canvas.convert('RGB')
    out.save(a.out, quality=95)
    jpg = os.path.splitext(a.out)[0] + '.jpg'
    out.save(jpg, quality=92)
    print(f'[ok] {a.out} + {jpg} (fontsize={fs})')

if __name__ == '__main__':
    main()
