# -*- coding: utf-8 -*-
"""render_prologue.py —— v13 故事脉络片头（转场段，不计正片时长）

品牌 intro 之后、正片之前的"30秒主线前情"：虚化背景 + 一句话梗概 +
2x2 四幕卡片（截图+金色标题+白字正文），TTS 逐句朗读驱动画面——
总结先读，四张卡片随各自旁白回弹滑入（左右交替），尾 0.6s 淡黑接正片。

用法：
  python render_prologue.py <config.json> [out.mp4]
config.json（路径相对 config 所在目录）：
{
  "bg": "bg_full.jpg",                      # 全片最经典一帧（全分辨率）
  "summary": "一句话故事梗概",
  "summary_audio": "00_summary.mp3",
  "cards": [ {"title":"01 起因 · xx","img":"t900.jpg","body":"一句正文约24字","audio":"01_x.mp3"}, x4 ],
  "W": 1920, "H": 1080                      # 可选，默认1080p；分辨率自适应缩放
}

内容来源：summary/四幕 title+body 直接复用 v11 读片骨架；img 每幕中段自动抽 1-2 候选人工选一；
旁白 edge-tts YunyangNeural rate=+12%，单句目标<10s（超长就压文案）。
编码与 cover_loop 一致（25fps crf18 yuv420p + aac 48k），assemble normalize 无缝。
"""
import json
import os
import subprocess
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

FF = "ffmpeg"
FPS = 25

GOLD = (216, 168, 74)
GOLD_DIM = (216, 168, 74, 150)
WHITE = (235, 231, 222)
CARD_BG = (16, 24, 33, 210)


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    l = (im.width - w) // 2
    t = (im.height - h) // 2
    return im.crop((l, t, l + w, t + h))


def wrap_cjk(text, font, max_w, draw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    if len(lines) > 1 and len(lines[-1]) <= 3:  # 孤行并入上一行
        lines[-2] += lines[-1]
        lines.pop()
    return lines


def ease_out_cubic(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_out_back(p):
    p = min(max(p, 0.0), 1.0)
    c1 = 1.2
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("out", nargs="?", default=None)
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.config))
    cfg = json.load(open(a.config, encoding="utf-8"))
    P = lambda p: p if os.path.isabs(p) else os.path.join(base, p)

    W = int(cfg.get("W", 1920))
    H = int(cfg.get("H", 1080))
    s = H / 1080.0
    F_SUM = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", int(38 * s))
    F_TTL = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", int(32 * s))
    F_BODY = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", int(25 * s))

    # ---- 背景：经典帧强虚化+压暗+提亮 ----
    bg = cover(Image.open(P(cfg["bg"])).convert("RGB"), W, H)
    bg = bg.filter(ImageFilter.GaussianBlur(int(22 * s)))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (13, 20, 30)), 0.52)
    bg = ImageEnhance.Brightness(bg).enhance(1.35).convert("RGBA")

    # ---- 卡片层 ----
    cw, ch, gap = int(840 * s), int(356 * s), int(44 * s)
    y0 = int(264 * s)
    pos = [(int(100 * s), y0), (int(100 * s) + cw + gap, y0),
           (int(100 * s), y0 + ch + gap), (int(100 * s) + cw + gap, y0 + ch + gap)]
    slide_dir = [-1, 1, -1, 1]

    def build_card(c):
        layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=int(14 * s),
                            fill=CARD_BG, outline=GOLD_DIM, width=1)
        iw, ih = int(340 * s), int(230 * s)
        iy = (ch - ih) // 2
        im = Image.open(P(c["img"])).convert("RGB")
        im = cover(im, im.width, int(im.height * 0.75))       # 裁底25%去硬字幕
        im = ImageEnhance.Brightness(im).enhance(1.5)
        im = cover(im, iw, ih)
        layer.paste(im, (int(26 * s), iy))
        d.rounded_rectangle((int(26 * s), iy, int(26 * s) + iw, iy + ih),
                            radius=int(6 * s), outline=GOLD_DIM, width=1)
        tx = iw + int(56 * s)
        d.text((tx, int(54 * s)), c["title"], font=F_TTL, fill=GOLD,
               stroke_width=1, stroke_fill=(60, 45, 15))
        bl = wrap_cjk(c["body"], F_BODY, cw - tx - int(36 * s), d)
        lines_pos, by = [], int(128 * s)
        for ln in bl:
            lines_pos.append((ln, by))
            by += int(46 * s)
        return layer, (tx, lines_pos)

    cards = cfg["cards"]
    layers, text_info = [], []
    for c in cards:
        ly, ti = build_card(c)
        layers.append(ly)
        text_info.append(ti)

    # ---- 时间线（音频驱动） ----
    aud = [P(cfg["summary_audio"])] + [P(c["audio"]) for c in cards]
    durs = [dur(p) for p in aud]
    GAP, T0 = 0.35, 0.5
    t_sum = T0 + durs[0]
    t_acc, starts = t_sum + GAP, []
    for i in range(len(cards)):
        starts.append(t_acc - 0.3)
        t_acc += durs[i + 1] + GAP
    total = t_acc - GAP + 1.0 + 0.6
    n = int(total * FPS)
    print("durs:", [round(x, 2) for x in durs], "total:", round(total, 2))

    tmp = Image.new("RGBA", (10, 10))
    sum_lines = wrap_cjk(cfg["summary"], F_SUM, W - int(200 * s), ImageDraw.Draw(tmp))

    # ---- 音频轨 ----
    SR = 48000

    def silence(k):
        return b"\x00\x00" * k

    chunks = [silence(int(T0 * SR))]
    wavs = []
    for i, p in enumerate(aud):
        wv = p + ".pro.wav"
        subprocess.run([FF, "-loglevel", "error", "-y", "-i", p,
                        "-ar", str(SR), "-ac", "1", wv], check=True)
        wavs.append(wv)
        with wave.open(wv) as w:
            chunks.append(w.readframes(w.getnframes()))
        if i < len(aud) - 1:
            chunks.append(silence(int(GAP * SR)))
    chunks.append(silence(max(int((total - (t_acc - GAP)) * SR), 0)))
    audio_wav = os.path.join(base, "_prologue_audio.wav")
    with wave.open(audio_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(chunks))

    # ---- 逐帧渲染 ----
    vf = os.path.join(base, "_prologue_v.mp4")
    cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", vf]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    CARD_ANIM, LINE_STAG = 0.45, 0.18
    for f in range(n):
        t = f / FPS
        canvas = bg.copy()
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for li, ln in enumerate(sum_lines):
            al = ease_out_cubic((t - (T0 + li * 0.45)) / 0.4)
            if al <= 0:
                continue
            dy = int((1 - al) * 22 * s)
            d.text((int(100 * s), int(78 * s) + li * int(58 * s) + dy), ln, font=F_SUM,
                   fill=(GOLD[0], GOLD[1], GOLD[2], int(255 * al)),
                   stroke_width=1, stroke_fill=(60, 45, 15, int(255 * al)))
        for i in range(len(cards)):
            p_in = ease_out_back((t - starts[i]) / CARD_ANIM)
            if p_in <= 0:
                continue
            p_in = min(p_in, 1.12)
            x, y = pos[i]
            dx = int((1 - p_in) * 140 * s * slide_dir[i])
            alpha = ease_out_cubic((t - starts[i]) / 0.3)
            ly = layers[i].copy()
            if alpha < 1:
                ly.putalpha(ly.getchannel("A").point(lambda v: int(v * alpha)))
            canvas.paste(ly, (x + dx, y), ly)
            tx, lines_pos = text_info[i]
            for lj, (ln, by) in enumerate(lines_pos):
                la = ease_out_cubic((t - (starts[i] + 0.25 + lj * LINE_STAG)) / 0.3)
                if la <= 0:
                    continue
                d.text((x + tx + dx, y + by), ln, font=F_BODY,
                       fill=(WHITE[0], WHITE[1], WHITE[2], int(255 * la)))
        canvas = Image.alpha_composite(canvas, ov)
        if t > total - 0.6:
            fade = max(0.0, (total - t) / 0.6)
            canvas = Image.blend(canvas, Image.new("RGBA", (W, H), (0, 0, 0, 255)), 1 - fade)
        p.stdin.write(canvas.convert("RGB").tobytes())
    p.stdin.close()
    p.wait()

    out = a.out or os.path.join(base, "prologue.mp4")
    subprocess.run([FF, "-loglevel", "error", "-y", "-i", vf, "-i", audio_wav,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-ac", "2", "-shortest", out], check=True)
    for wv in wavs + [audio_wav, vf]:
        try:
            os.remove(wv)
        except OSError:
            pass
    print("saved", out, round(total, 2), "s")


if __name__ == "__main__":
    main()
