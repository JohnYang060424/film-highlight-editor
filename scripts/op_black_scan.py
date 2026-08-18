#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
op_black_scan.py — 流程步骤3.5：OP/片头/过场黑场免疫扫描
用法:
  python op_black_scan.py <视频> [-o op_black.json] [--min-dur 3] [--raw 临时.rawvideo]

方法（与 SKILL.md 一致）:
  ffmpeg -vf fps=1,scale=240:135 落盘 rawvideo(rgb24) → memmap 逐帧统计
  黄/白/黑像素占比 → 连续 >=min-dur 秒的区间判定为 logo/黑场区。
阈值兜底: 除固定颜色阈值外，额外检测"低方差纯色帧"（std<12 且亮度<40 判黑场，
         std<12 且亮度>200 判白/亮底），防深蓝/红色片头漏检。
输出: [{"start":..,"end":..,"type":"yellow|white|black|solid"}, ...]
并打印与 clips 边界核对提示（需配合 keyframes.py --op-black 使用）。
"""
import argparse, json, os, subprocess
import numpy as np

W, H = 240, 135
PIXELS = W * H

def scan(video, raw_path):
    if not os.path.exists(raw_path) or os.path.getsize(raw_path) < PIXELS * 3:
        print("[1/2] ffmpeg 抽帧落盘 rawvideo（240x135 @1fps）...")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", video,
             "-vf", f"fps=1,scale={W}:{H}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", raw_path],
            check=True)
    print(f"[2/2] 分析 {os.path.getsize(raw_path)//(PIXELS*3)} 帧 ...")
    mm = np.memmap(raw_path, dtype=np.uint8, mode="r")
    n = mm.size // (PIXELS * 3)
    frames = mm.reshape(n, H, W, 3).astype(np.int32)
    r, g, b = frames[..., 0], frames[..., 1], frames[..., 2]
    yellow = ((r > 190) & (g > 140) & (b < 110)).reshape(n, -1).mean(1)
    white = ((r > 200) & (g > 200) & (b > 200)).reshape(n, -1).mean(1)
    black = ((r < 40) & (g < 40) & (b < 40)).reshape(n, -1).mean(1)
    std = frames.reshape(n, -1, 3).std(axis=1).mean(1)   # 每帧平均通道方差
    meanlum = frames.reshape(n, -1).mean(1)
    solid_dark = (std < 12) & (meanlum < 40)
    solid_bright = (std < 12) & (meanlum > 200)
    return dict(yellow=yellow, white=white, black=black,
                solid_dark=solid_dark, solid_bright=solid_bright)

def runs(mask, min_dur):
    """1fps 下连续 True 帧 >=min_dur 的区间 [start,end]（闭区间秒）。"""
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_dur:
                out.append([s, i - 1])
            s = None
    if s is not None and len(mask) - s >= min_dur:
        out.append([s, len(mask) - 1])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default="op_black.json")
    ap.add_argument("--min-dur", type=int, default=3)
    ap.add_argument("--raw", default="")
    ap.add_argument("--ratio", type=float, default=0.85, help="像素占比阈值")
    a = ap.parse_args()
    raw_path = a.raw or os.path.join(os.path.dirname(os.path.abspath(a.out)), "scan_240x135.rawvideo")
    m = scan(a.video, raw_path)
    intervals = []
    for typ, mask in [("yellow", m["yellow"] >= a.ratio),
                      ("white", m["white"] >= a.ratio),
                      ("black", m["black"] >= a.ratio),
                      ("solid", m["solid_dark"] | m["solid_bright"])]:
        for s, e in runs(mask, a.min_dur):
            intervals.append({"start": float(s), "end": float(e), "type": typ})
    # 合并重叠区间
    intervals.sort(key=lambda x: x["start"])
    merged = []
    for iv in intervals:
        if merged and iv["start"] <= merged[-1]["end"] + 1:
            merged[-1]["end"] = max(merged[-1]["end"], iv["end"])
            if iv["type"] not in merged[-1]["type"]:
                merged[-1]["type"] += "|" + iv["type"]
        else:
            merged.append(dict(iv))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[ok] 发现 {len(merged)} 个 logo/黑场区间 -> {a.out}")
    for iv in merged:
        print(f"  {iv['start']:8.1f} - {iv['end']:8.1f}  [{iv['type']}]")
    if not a.raw:
        try: os.remove(raw_path)
        except OSError: pass  # 沙箱可能禁用删除，保留 rawvideo 不影响结果

if __name__ == "__main__":
    main()
