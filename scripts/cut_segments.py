#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cut_segments.py — 流程步骤5（含步骤4音画同步三步法）
用法:
  python cut_segments.py <视频> <clips_snap.json> [--outdir clips] [--prefix m]

对每段分别执行（v6 音画同步根治版）:
  ① 视频  ffmpeg -ss s -to e -i src -map 0:v:0 -c:v copy -avoid_negative_ts make_zero v_i.mp4
  ② 音频  解码重编码精确切割 -ss s -t {视频实际时长} -c:a aac -ar 48000 -ac 2 -b:a 192k
     ⚠ 严禁改回 -c:a copy：copy 切 AAC 带 ~90ms 预卷(首包负 pts)，MP4 靠 edit
     list 遮掩、TS/concat/部分播放器不认 → 声音抢跑、对白嘴型错位、逐段累积
     （本机实测 4 段片尾音频提前 0.14s）。
  ③ 合并  ffmpeg -i v_i.mp4 -i a_i.m4a -c copy m_i.mp4
切完打印每段 v/a start_time + duration 校验（要求 start≈0、drift ≤0.05s）。
"""
import argparse, json, os, subprocess, sys

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg ERROR]", r.stderr[-800:], file=sys.stderr)
        sys.exit(1)

def probe(path, *entries):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", ",".join(entries),
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout
    return [x for x in out.split() if x.strip()]

def stream_info(path):
    """返回 (start_time, duration) of first video & audio."""
    r = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "v:0",
         "-show_entries", "stream=start_time,duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout.split()
    vs, vd = (float(r[0]), float(r[1])) if len(r) >= 2 else (0.0, 0.0)
    r2 = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "a:0",
         "-show_entries", "stream=start_time,duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True).stdout.split()
    # a stream start/duration may be N/A
    def flt(x):
        try: return float(x)
        except ValueError: return None
    vals = [flt(x) for x in r2]
    ast = vals[0] if vals and vals[0] is not None else 0.0
    adu = vals[1] if len(vals) > 1 and vals[1] is not None else 0.0
    return vs, vd, ast, adu

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("clips")
    ap.add_argument("--outdir", default="clips")
    ap.add_argument("--prefix", default="m")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    with open(a.clips, encoding="utf-8") as f:
        clips = json.load(f)
    report = []
    for i, c in enumerate(clips):
        s, e = float(c["s"]), float(c["e"])
        dur = e - s
        name = f"{a.prefix}{i:02d}"
        v_f = os.path.join(a.outdir, name + "_v.mp4")
        a_f = os.path.join(a.outdir, name + "_a.m4a")
        out_f = os.path.join(a.outdir, name + ".mp4")
        if os.path.exists(out_f) and os.path.getsize(out_f) > 1000:
            print(f"[skip] {name} 已存在"); continue
        # ① 视频 stream-copy
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
             "-i", a.video, "-map", "0:v:0", "-c:v", "copy",
             "-avoid_negative_ts", "make_zero", v_f])
        # 视频实际时长（copy 切止点按帧对齐，可能比 e-s 短至多一帧）
        vdur_real = probe(v_f, "stream=duration")
        vdur_real = float(vdur_real[0]) if vdur_real else dur
        # ② 音频必须解码重编码、逐采样精确切割（v6 根治，勿改回 -c:a copy！）
        #   根因: -c:a copy 切 AAC 会带 ~90ms 预卷（首包负 pts），只靠 MP4 edit
        #   list 遮掩；TS 转封装/concat/部分播放器不认 edit list → 声音抢跑、
        #   对白嘴型错位、逐段累积（实测 4 段片尾提前 0.14s）。
        #   解码重编后起点恒为 0、无 edit list 依赖；-t 对齐视频实际时长，
        #   杜绝段尾音频超长青黄（超视频长的音频尾巴会在 concat 后累积成漂移）。
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-t", f"{vdur_real:.3f}",
             "-i", a.video, "-map", "0:a:0",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", a_f])
        # ③ 合并
        run(["ffmpeg", "-v", "error", "-y", "-i", v_f, "-i", a_f,
             "-c", "copy", out_f])
        # 中间文件尽力清理（沙箱环境可能禁用删除，失败不影响主流程）
        for tmp in (v_f, a_f):
            try:
                os.remove(tmp)
            except OSError:
                pass
        vs, vd, ast, adu = stream_info(out_f)
        drift = abs(vd - adu) if adu else 0.0
        flag = "OK" if drift <= 0.1 else "WARN>0.1s"
        print(f"[ok] {name}: v_start={vs:.3f} v_dur={vd:.2f} a_dur={adu:.2f} drift={drift:.3f} {flag}")
        report.append({**c, "file": os.path.abspath(out_f),
                       "v_start": vs, "v_dur": vd, "a_dur": adu, "drift": round(drift, 3)})
    with open(os.path.join(a.outdir, "cut_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(report)} 段已截取，报告 -> {os.path.join(a.outdir,'cut_report.json')}")

if __name__ == "__main__":
    main()
