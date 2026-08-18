#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_marker_measure.py — 采样级音画对齐测量（onset 对 onset，金标准校验器）
用法: python sync_marker_measure.py <成片.mp4>

配套测试源构造法：用 ffmpeg 造 beep(1kHz 0.15s)+闪白(0.15s) 同时开始的
标记源（标记间留白 ≥1s），按生产链路切割/拼接后测量，onset-onset 差即
真实音画偏差。判定：单标记 |偏差|≤0.045s 且首尾变化≈0 为 PASS。

测量原理：
beep 起点 = 第一个 |sample|>thr 的采样时刻（精确到 1/48000 s）
闪白起点 = 第一个均值>thr_v 的帧时刻（25fps 帧网格）
事件 ≥0.12s 过滤杂音；±0.4s 最近邻配对。
本脚本已三重校验：坏样本 final4_base 显示 +0.115s 累积、
好样本 final4_mp4concat 干净（max 0.037s）、源 marker4_src ≈ -0.0001s。
"""
import subprocess, sys
import numpy as np

SR, FPS = 48000, 25

def probe(path, thr_a=0.3, thr_v=200, min_dur=0.12):
    wav = subprocess.run(["ffmpeg","-v","error","-i",path,"-map","0:a:0",
        "-ac","1","-ar",str(SR),"-f","s16le","-"],capture_output=True,check=True).stdout
    a = np.abs(np.frombuffer(wav,dtype=np.int16).astype(np.float32)/32768.0)
    # 1ms 包络找事件段，事件>=min_dur 才算标记 beep（过滤短杂音）
    bin_n = SR//1000
    nb = len(a)//bin_n
    env = a[:nb*bin_n].reshape(nb,bin_n).max(axis=1)
    hit = env > thr_a
    beeps = []
    i = 0
    while i < nb:
        if hit[i]:
            j = i
            while j < nb and hit[j]: j += 1
            if (j-i)/1000 >= min_dur:
                seg = a[i*bin_n:j*bin_n]
                on = np.nonzero(seg > thr_a)[0]
                beeps.append((i*bin_n + on[0])/SR)   # 采样级 onset
            i = j
        else:
            i += 1
    w,h = 320,180
    raw = subprocess.run(["ffmpeg","-v","error","-i",path,"-map","0:v:0",
        "-vf",f"scale={w}:{h},format=gray","-f","rawvideo","-pix_fmt","gray","-"],
        capture_output=True,check=True).stdout
    assert len(raw)%(w*h)==0
    means = np.frombuffer(raw,dtype=np.uint8).reshape(-1,h*w).astype(np.float32).mean(axis=1)
    fl = means > thr_v
    flashes, i = [], 0
    while i < len(fl):
        if fl[i]:
            j = i
            while j < len(fl) and fl[j]: j += 1
            if (j-i) >= 2:
                flashes.append(i/FPS)   # 帧 onset
            i = j
        else:
            i += 1
    print(f"成片 {path}")
    print(f"  beep onset: {[round(x,4) for x in beeps]}")
    print(f"  flash onset: {[round(x,4) for x in flashes]}")
    if not beeps or not flashes:
        print("  !! 无配对"); return
    diffs = []
    for k, ft in enumerate(flashes):
        cands = [(abs(bt-ft),bt) for bt in beeps if abs(bt-ft) < 0.4]
        if not cands:
            print(f"  标记{k+1}: 画面@{ft:.4f} 无邻近beep"); continue
        _, bt = min(cands)
        d = ft-bt
        diffs.append(d)
        flag = "✓" if abs(d) <= 0.045 else "✗"
        print(f"  标记{k+1}: 声音@{bt:.4f} 画面@{ft:.4f}  画面-声音={d:+.4f}s {flag}")
    if len(diffs) >= 2:
        print(f"  最大|偏差|={max(abs(x) for x in diffs):.4f}s  首尾变化={diffs[-1]-diffs[0]:+.4f}s")

if __name__=="__main__":
    probe(sys.argv[1])
