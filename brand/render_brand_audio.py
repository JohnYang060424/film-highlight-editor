# -*- coding: utf-8 -*-
"""品牌音效合成（v13.4 用户钦定）：
  intro：工具组合感——金属碰撞声(whoosh/clank)在前，元素到位时组合落位音(clunk+shimmer)
  outro：舒缓旋律（五声音阶钢琴式正弦+泛音），结尾慢慢消音到0

用法: python render_brand_audio.py <brand_dir>
产出: brand/intro_audio.wav (3s) / brand/outro_audio.wav (5s)
随后 render_brand_v2.py 已改为优先混入这两个 wav（无文件则静音，向后兼容）。

合成方法：numpy 加法合成 → scipy-free wav 写入（用 wave 模块手写 PCM）。
"""
import math
import os
import sys
import wave

import numpy as np

BRAND = sys.argv[1]
SR = 48000
SEC_INTRO, SEC_OUTRO = 3.0, 5.0


def env_adsr(n, a=0.005, d=0.0, s=1.0, r=0.0, total=None):
    t = np.arange(n) / SR
    e = np.ones(n)
    e[:int(a * SR)] = np.linspace(0, 1, int(a * SR))
    if r > 0:
        e[-int(r * SR):] *= np.linspace(1, 0, int(r * SR))
    return e


def tone(freq, dur, amp=0.3, decay=3.0, harmonics=((1, 1.0), (2, 0.35), (3, 0.12), (4.16, 0.06))):
    """钢琴式音色：基频+泛音，指数衰减"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for h, w in harmonics:
        y += w * np.sin(2 * math.pi * freq * h * t)
    y *= amp * np.exp(-decay * t) * env_adsr(n, a=0.004)
    return y


def noise_burst(dur, amp=0.25, decay=18.0, hp=1200.0):
    """金属碰撞的噪声成分：白噪声高通+快衰减"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.random.default_rng(7).standard_normal(n)
    # 简单一阶高通
    y = np.diff(np.concatenate(([0], y))) * 0.5 + y * 0.5
    y *= amp * np.exp(-decay * t)
    return y


def clang(freq, dur=0.5, amp=0.3):
    """金属clank：非谐泛音(inharmonic partials)+噪声"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for h, w, d in ((1.0, 1.0, 7), (2.76, 0.5, 9), (5.4, 0.25, 12), (8.9, 0.12, 15)):
        y += w * np.sin(2 * math.pi * freq * h * t) * np.exp(-d * t)
    y = y * amp + noise_burst(dur, amp * 0.5, 22)
    y *= env_adsr(n, a=0.002)
    return y


def whoosh(dur=0.5, amp=0.12, f0=300, f1=2400):
    """上升扫频带限噪声=工具飞入的嗖声"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    ph = 2 * math.pi * np.cumsum(f) / SR
    y = np.sin(ph) * 0.3 + np.random.default_rng(3).standard_normal(n) * 0.7
    y *= amp * np.sin(math.pi * t / dur) ** 2
    return y


def add_at(buf, sig, t0):
    i0 = int(t0 * SR)
    i1 = min(len(buf), i0 + len(sig))
    buf[i0:i1] += sig[:i1 - i0]


def write_wav(path, buf, sec):
    n = int(sec * SR)
    buf = buf[:n]
    peak = np.max(np.abs(buf)) or 1.0
    buf = buf / peak * 0.85
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"[ok] {path} ({sec}s, peak-norm 0.85)")


# ---------------- intro 3s：金属碰撞 → 组合 ----------------
buf = np.zeros(int(SEC_INTRO * SR) + SR)
# 0.10 reel 旋入：低频 whoosh + 到位 0.95 clank
add_at(buf, whoosh(0.85, 0.10, 250, 1800), 0.10)
add_at(buf, clang(520, 0.45, 0.28), 0.93)
# 0.35 wing 翻入：高频 whoosh + 到位 1.15 clank（不同音高）
add_at(buf, whoosh(0.80, 0.09, 500, 3000), 0.35)
add_at(buf, clang(780, 0.4, 0.24), 1.13)
# chars 飞入：4 连短促 ticks（工具卡位）
for i in range(4):
    add_at(buf, clang(1100 + i * 160, 0.18, 0.14), 1.08 + i * 0.12)
# 1.55 冲击波：大 clunk（组合落位）+ shimmer 泛音簇
add_at(buf, clang(320, 0.8, 0.4), 1.53)
for i, f in enumerate((1568, 1976, 2637)):
    add_at(buf, tone(f, 1.2, 0.10, 4.0, ((1, 1.0), (2, 0.2))), 1.58 + i * 0.05)
write_wav(f"{BRAND}/intro_audio.wav", buf, SEC_INTRO)

# ---------------- outro 5s：舒缓旋律，消音到0 ----------------
buf = np.zeros(int(SEC_OUTRO * SR) + SR)
# C 大调五声：C5 E5 G5 A5 G5 E5 C5，0.55s 间隔，从 0.35s 起
notes = [(523.25, 0.35), (659.25, 0.95), (783.99, 1.55), (880.0, 2.15),
         (783.99, 2.75), (659.25, 3.35), (523.25, 3.95)]
for f, t0 in notes:
    add_at(buf, tone(f, 1.6, 0.22, 2.2), t0)
    add_at(buf, tone(f / 2, 1.8, 0.08, 2.0), t0)  # 低八度衬底
# 整体包络：前0.3s 淡入，3.6s 起余音慢慢消到0（到 SEC_OUTRO 恰好静）
n = len(buf)
t = np.arange(n) / SR
g = np.ones(n)
g[:int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
i_f = int(3.6 * SR)
j_f = int(SEC_OUTRO * SR)
g[i_f:j_f] *= np.cos(np.linspace(0, math.pi / 2, j_f - i_f)) ** 1.5
g[j_f:] = 0.0
buf *= g
write_wav(f"{BRAND}/outro_audio.wav", buf, SEC_OUTRO)
print("[done]")
