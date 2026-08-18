#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
keyframes.py — 流程步骤3：全片关键帧表 + 切点 snap 计算
用法:
  python keyframes.py <视频> <clips.json> [--op-black <op_black.json>]

clips.json 输入格式（目标时间戳，秒）:
  [{"name":"段1","start":120.0,"end":150.0}, ...]

规则（与 SKILL.md 一致）:
  - 起点: 向后 snap 到 <=start 的最近关键帧（回吸前关键帧）
  - 止点: 精确时间戳精确 cut（不吸后关键帧）
  - 例外: 若回吸后的起点落进 OP/黑场/logo 区间（op_black.json），
          该段起点改为向前 snap 到黑场后第一个关键帧。
  - 片尾段（end 接近片长）: 起点改前向 snap（ks=min(k>=目标)）。

op_black.json 格式: [{"start":0.0,"end":80.0,"type":"op"}, ...]
输出: clips_snap.json（补上 snap 后的 s/e 与 v/a 截取参数）。
"""
import argparse, json, os, subprocess

def keyframe_times(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-skip_frame", "nokey",
         "-select_streams", "v:0", "-show_entries", "frame=pts_time",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout
    return sorted(float(x) for x in out.split() if x.strip())

def duration(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)

def snap_back(kfs, t):
    cand = [k for k in kfs if k <= t]
    return cand[-1] if cand else (kfs[0] if kfs else t)

def snap_forward(kfs, t):
    cand = [k for k in kfs if k >= t]
    return cand[0] if cand else (kfs[-1] if kfs else t)

def in_black(t, intervals):
    for iv in intervals:
        if iv["start"] <= t <= iv["end"]:
            return iv
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("clips")
    ap.add_argument("--op-black", default="")
    ap.add_argument("--tail-ratio", type=float, default=0.98,
                    help="end/片长 >= 该比例视为片尾段")
    ap.add_argument("-o", "--out", default="clips_snap.json")
    a = ap.parse_args()

    kfs = keyframe_times(a.video)
    dur = duration(a.video)
    intervals = []
    if a.op_black and os.path.exists(a.op_black):
        with open(a.op_black, encoding="utf-8") as f:
            intervals = json.load(f)
    with open(a.clips, encoding="utf-8") as f:
        clips = json.load(f)

    res = []
    for c in clips:
        s, e = float(c["start"]), float(c["end"])
        is_tail = e >= dur * a.tail_ratio
        s_snap = snap_forward(kfs, s) if is_tail else snap_back(kfs, s)
        note = []
        hit = in_black(s_snap, intervals)
        if hit and not is_tail:
            # 起点落进黑场/OP 区 -> 向前 snap 到区间后第一个关键帧
            s_snap = snap_forward(kfs, hit["end"])
            note.append(f"起点避开{hit.get('type','black')}区[{hit['start']:.1f}-{hit['end']:.1f}]，前向snap")
        if is_tail:
            note.append("片尾段前向snap")
        # v10 段内含黑检查（黑场免疫盲区修复：旧版只查"起点落黑"，
        # 漏查 snap 后段内包进黑场/OP 区间，如片头 credits 被回吸进段内）
        # v11 门槛：<4s 的黑场/黑闪视为转场闪切（影片自身叙事语言），
        # 不触发回退与告警——哪吒实战 n00/n03/n07 误触发的均为 2-3s 转场黑闪，
        # 回退后目核原始起点与 snap 点画面同源，属过度防御。
        inner = [iv for iv in intervals
                 if iv["start"] >= s_snap + 0.2 and iv["end"] <= e - 0.2
                 and iv["end"] - iv["start"] >= 4.0]
        if inner:
            desc = ",".join(f"[{iv['start']:.1f}-{iv['end']:.1f}]" for iv in inner)
            note.append(f"⚠段内含黑场/OP区间{desc}，回退原始起点{s:.3f}")
            s_snap = s
        # 止点贴黑场（区间横跨段尾）-> 只告警不自动改，由人工收紧止点
        tail_hit = [iv for iv in intervals
                    if iv["start"] < e - 0.2 < iv["end"] or (iv["start"] < e <= iv["end"])]
        if tail_hit:
            note.append(f"⚠止点贴{tail_hit[0].get('type','black')}区，建议收紧止点")
        res.append({**c, "s": round(s_snap, 3), "e": round(e, 3),
                    "dur": round(e - s_snap, 3), "notes": note})
        print(f"{c['name']:>14}: start {s:.2f}->{s_snap:.3f}  end {e:.2f}  dur {e-s_snap:.2f}  {';'.join(note)}")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"[ok] 写入 {a.out}  共 {len(res)} 段")

if __name__ == "__main__":
    main()
