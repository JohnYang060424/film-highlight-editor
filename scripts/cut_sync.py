#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cut_sync.py — "切香肠式"切段：单命令对原片同时切 v/a，解码重编码，杜绝关键帧回吸。

与旧版 cut_segments.py 的本质区别:
  旧版: 视频 -c:v copy (stream-copy) → 起点被 ffmpeg 回吸到 s 前最近关键帧(1~3s)
       音频单独 -ss s 精确切 → v/a 相对关系被破坏 → 段内画面超前音频
       然后再把两个文件合并 = "把馅掏出来重新卷"，引入错位
  新版: ffmpeg -ss s -t D -i src -map 0:v:0 -map 0:a:0 -c:v libx264 -c:a aac
       一条命令，v/a 都从精确 s 起、解码重编码，保持源片 v/a 相对关系
       = "切香肠不断馅"，从根上消除回吸

输入: clips_snap.json (含 s/e)，s 已是关键帧/黑场免疫后的起点
输出: segs/mNN.mp4 (v/a 同切)
"""
import argparse, json, os, subprocess, sys

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg ERROR]", r.stderr[-1200:], file=sys.stderr)
        sys.exit(1)

def probe_dur(path, stream):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream,
                        "-show_entries", "stream=duration",
                        "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True).stdout.strip()
    try:
        return float(r)
    except ValueError:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("clips")
    ap.add_argument("--outdir", default="segs")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="veryfast")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    with open(a.clips, encoding="utf-8") as f:
        clips = json.load(f)

    report = []
    for i, c in enumerate(clips):
        s, e = float(c["s"]), float(c["e"])
        dur = e - s
        name = f"{i:02d}"
        out_f = os.path.join(a.outdir, f"m{name}.mp4")
        if os.path.exists(out_f) and os.path.getsize(out_f) > 1000:
            print(f"[skip] m{name} 已存在"); continue
        # 单命令同切 v/a，解码重编码，从精确 s 起，杜绝回吸
        run(["ffmpeg", "-v", "error", "-y",
             "-ss", f"{s:.3f}", "-t", f"{dur:.3f}",
             "-i", a.video,
             "-map", "0:v:0", "-map", "0:a:0",
             "-c:v", "libx264", "-crf", str(a.crf), "-preset", a.preset,
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
             out_f])
        vd = probe_dur(out_f, "v:0"); ad = probe_dur(out_f, "a:0")
        drift = abs(vd - ad) if (vd and ad) else 0.0
        print(f"[ok] m{name}: s={s:.3f} dur={dur:.2f} v_dur={vd:.2f} a_dur={ad:.2f} drift={drift:.3f} "
              f"{'OK' if drift<=0.1 else 'WARN>0.1s'}")
        report.append({**c, "file": os.path.abspath(out_f),
                       "v_dur": vd, "a_dur": ad, "drift": round(drift, 3)})

    with open(os.path.join(a.outdir, "cut_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(report)} 段，报告 -> {os.path.join(a.outdir,'cut_report.json')}")

if __name__ == "__main__":
    main()