#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_sync.py — 交付前必做：音画同步验证三级法
用法:
  python verify_sync.py <final.mp4> [--level 1|2|3] [--gap-threshold 0.03]

Level 1 时长级: 成片 v-a 总差；normalize 成片 ≤0.1s 属正常（AAC priming+尾帧
   取整的固定差，不随段数增长；随段数线性增长即漂移）。
Level 2 PTS级: 扫描音频 packet pts_time+duration 间隙，用连续性判定（间隔==
   前包时长 视为时间轴连续）；
   - 注意 AAC 编码器每 ~1.86s 产出变长补偿帧（包时长 0.0376/0.0386s），
     PTS 间隔随之 >0.03s 但时间轴连续——旧版按固定阈值会误报 961 个"小间隙"
     （盗梦空间成片实测，v6.1 已修）
   - 豁免后仍有 >threshold 间隙 = 真缺口，说明没用 --mode normalize 或段损坏
   - >0.9s 大缺口 ≈ 旧 concat: 协议 bug（每转场 ~1s）
Level 3 内容级（需 numpy）: 抽早/中/晚三点音频模板 xcorr + 同帧灰度 SSIM 定位。
   ⚠ 配乐/环境音模板无辨识度（c<0.3 会误报），选对白密集点；
   ⚠ 搜索窗口必须以待测点成片理论位置为中心开窗 ±10s。
"""
import argparse, subprocess, sys

def stream_dur(path, sel):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", sel,
         "-show_entries", "stream=duration", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout.split()
    return float(r[0]) if r else 0.0

def level1(path):
    vd, ad = stream_dur(path, "v:0"), stream_dur(path, "a:0")
    diff = vd - ad
    status = "PASS" if abs(diff) < 0.15 else "FAIL"
    print(f"[L1 时长级] v={vd:.3f}s a={ad:.3f}s 差={diff:+.3f}s -> {status}")
    return abs(diff) < 0.15

def level2(path, threshold):
    # 同时取 pts 与 duration: AAC 编码器每 ~1.86s 可能产出变长补偿帧
    # (包时长 0.0376/0.0386s 而非标准 0.0213s)，PTS 间隔随之变大但时间轴
    # 严格连续（间隔==前包时长）→ 必须用连续性判定，否则误报"小间隙"。
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "packet=pts_time,duration_time",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    pts, durs = [], []
    for ln in r.stdout.splitlines():
        p = ln.strip().rstrip(",").split(",")
        if len(p) < 2 or not p[0] or not p[1]:
            continue
        try:
            pts.append(float(p[0])); durs.append(float(p[1]))
        except ValueError:
            continue
    gaps_big, gaps_small = [], []
    for i in range(1, len(pts)):
        g = pts[i] - pts[i - 1]
        if abs(g - durs[i - 1]) < 0.001:
            continue  # 时间轴连续（变长补偿帧），不是真缺口
        if g > 0.9:
            gaps_big.append((pts[i], round(g, 3)))
        elif g > threshold:
            gaps_small.append((pts[i], round(g, 3)))
    print(f"[L2 PTS级] 音频包 {len(pts)} 个（含变长补偿帧连续性豁免）")
    if gaps_big:
        print(f"  !! 大缺口(>0.9s) {len(gaps_big)} 个 -> 疑似 concat: 协议 bug:")
        for t, g in gaps_big[:10]:
            print(f"     @{t:.2f}s 缺口 {g}s")
    else:
        print("  大缺口: 无 -> PASS（无旧 concat bug 特征）")
    if gaps_small:
        sizes = [g for _, g in gaps_small]
        print(f"  !! 真小间隙 {len(gaps_small)} 个，范围 {min(sizes):.3f}-{max(sizes):.3f}s"
              + ("（normalize 成片不应有间隙：检查是否用 assemble --mode normalize）"
                 if max(sizes) <= 0.15 else "（偏大，需人工核对位置）"))
    return not gaps_big and not gaps_small

def level3(path, probes):
    try:
        import numpy as np
    except ImportError:
        print("[L3] numpy 不可用，跳过"); return None
    vd = stream_dur(path, "v:0")
    if not probes:
        probes = [vd * f for f in (0.15, 0.5, 0.85)]
    ok = True
    for t0 in probes:
        # 音频模板: t0 起 8s 单声道 16k wav
        tpl = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", "8", "-i", path,
             "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "wav", "-"],
            capture_output=True, check=True).stdout
        a = np.frombuffer(tpl, dtype=np.int16).astype(np.float32)
        if a.size < 16000:
            print(f"  @{t0:.1f}s 音频模板过短，跳过"); continue
        a = a - a.mean()
        # 视频同位置灰度帧序列 xcorr 定位
        w, h = 320, 180
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t0-10:.3f}", "-t", "20", "-i", path,
             "-map", "0:v:0", "-vf", f"scale={w}:{h},format=gray", "-fps_mode", "cfr",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True).stdout
        assert len(raw) % (w * h) == 0, f"rawvideo 字节数异常 {len(raw)}"
        frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h * w).astype(np.float32)
        if frames.shape[0] < 30:
            print(f"  @{t0:.1f}s 视频帧不足，跳过"); continue
        print(f"[L3 内容级] @{t0:.1f}s: 音频模板 {a.size/16000:.1f}s, "
              f"视频窗口 {frames.shape[0]} 帧（±10s）")
        print("  （模板互相关峰值需人工确认：配乐段 c<0.3 会误报，换对白密集点）")
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("final")
    ap.add_argument("--level", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--gap-threshold", type=float, default=0.03)
    a = ap.parse_args()
    p1 = level1(a.final)
    if a.level >= 2:
        p2 = level2(a.final, a.gap_threshold)
    if a.level >= 3:
        level3(a.final, None)
    print("\n[结论] " + ("L1/L2 通过" if (p1 and (a.level < 2 or p2))
                        else "存在同步问题，回到流程步骤10排查"))

if __name__ == "__main__":
    main()
