#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ad_scan.py —— v13.3 片源头尾广告风控扫描 + 骨架边界校验

背景（用户钦定 v13.3 规则③）：片源可能来自互联网，头尾是广告重灾区——
二维码、"荐片/jianpian/BT种子/迅雷/P2P/福利/扫码保存"等推广水印字样。
剪进任何一帧都会触发 B 站风控，被判定嵌入商业广告。

两个子命令：
  scan  对片源【前 5 分钟 + 后 5 分钟】按 10s（默认）间隔抽帧拼大图，
        供目检广告/二维码/推广水印；发现可疑区间记入 ad_zones.json 黑名单。
  check 用黑名单校验切点清单（clips.json / clips_snap.json）：
        任何段与禁区重叠 = FAIL；段落在头尾重灾区内 = WARN（必须已目核）。

用法：
  python ad_scan.py scan  <video> <outdir> [--interval 10] [--head-sec 300]
                          [--tail-sec 300] [--w 384] [--cols 5]
  python ad_scan.py check <video> <clips.json> [--zones ad_zones.json]
                          [--head-sec 300] [--tail-sec 300]

ad_zones.json 格式（目检后手工/脚本登记禁区）：
  {"zones": [{"start": 0.0, "end": 45.0, "reason": "片头厂标+片名+演职员"},
             {"start": 6780.0, "end": 6806.0, "reason": "结尾二维码推广"}]}

产物：ad_scan_head.png / ad_scan_tail.png / ad_scan_report.json
"""
import argparse
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

KEYWORDS = ("二维码", "荐片", "jianpian", "BT种子", "迅雷", "P2P",
            "福利", "扫码保存", "网址/站名水印", "Telegram群")


def find_font(size):
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def fmt_ts(sec):
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def probe_duration(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def sample_frames(video, start, end, interval, thumb_w, thumb_h):
    """返回 [(t, PIL.Image)]，fps 滤镜采样 rawvideo 管道读回。"""
    dur = end - start
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", video,
           "-vf", f"fps=1/{interval},scale={thumb_w}:{thumb_h}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.run(cmd, capture_output=True, check=True)
    raw = p.stdout
    frame_bytes = thumb_w * thumb_h * 3
    n = len(raw) // frame_bytes
    frames = []
    for i in range(n):
        img = Image.frombytes("RGB", (thumb_w, thumb_h),
                              raw[i * frame_bytes:(i + 1) * frame_bytes])
        frames.append((start + i * interval, img))
    return frames


def tile(frames, out_path, cols, thumb_w, thumb_h, caption_h=28):
    if not frames:
        print(f"[skip] 无帧: {out_path}")
        return
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + caption_h)), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    font = find_font(caption_h - 6)
    for i, (t, img) in enumerate(frames):
        r, c = divmod(i, cols)
        x, y = c * thumb_w, r * (thumb_h + caption_h)
        sheet.paste(img, (x, y))
        draw.text((x + 4, y + thumb_h + 3), fmt_ts(t), fill=(255, 220, 0), font=font)
    sheet.save(out_path)
    print(f"[ok] {out_path}  ({len(frames)} 帧)")


def cmd_scan(a):
    os.makedirs(a.outdir, exist_ok=True)
    dur = probe_duration(a.video)
    print(f"片长 {dur:.1f}s ({dur/60:.1f}min)")
    head_end = min(a.head_sec, dur)
    tail_start = max(0.0, dur - a.tail_sec)

    windows = []
    if tail_start <= head_end:
        windows.append(("full", 0.0, dur))
        print("[warn] 片长短于头尾窗口之和，全片扫描")
    else:
        windows.append(("head", 0.0, head_end))
        windows.append(("tail", tail_start, dur))

    for tag, s, e in windows:
        frames = sample_frames(a.video, s, e, a.interval, a.w, int(a.w * 9 / 16))
        tile(frames, os.path.join(a.outdir, f"ad_scan_{tag}.png"),
             a.cols, a.w, int(a.w * 9 / 16))

    report = {
        "video": os.path.abspath(a.video),
        "duration": dur,
        "interval": a.interval,
        "windows": [{"tag": t, "start": s, "end": e} for t, s, e in windows],
        "check_keywords": list(KEYWORDS),
        "note": "目检发现广告/二维码/推广字样 → 记入 ad_zones.json 禁区；"
                "片头区还要标出片头结束点（正片第一帧）、片尾区标出片尾起点（片尾曲/字幕第一帧）",
    }
    rp = os.path.join(a.outdir, "ad_scan_report.json")
    json.dump(report, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[ok] {rp}")
    print("\n=== 目检清单（逐帧看，发现即弃）===")
    print("1. 关键词字样：" + "、".join(KEYWORDS))
    print("2. 片头区：厂标/logo/片名页/演职员表 → 记录片头结束点（正片第一帧秒数）")
    print("3. 片尾区：片尾曲/字幕页/鸣谢/彩蛋/二维码 → 记录片尾起点（第一帧秒数）")
    print("4. 结论写入 ad_zones.json（zones: start/end/reason）")


def cmd_check(a):
    dur = probe_duration(a.video)
    clips = json.load(open(a.clips, encoding="utf-8"))
    zones = []
    if a.zones and os.path.exists(a.zones):
        zones = json.load(open(a.zones, encoding="utf-8")).get("zones", [])
    elif a.zones:
        print(f"[warn] 禁区文件不存在: {a.zones}（只查重灾区提示）")

    fails, warns = [], []
    for c in clips:
        name = c.get("name", "?")
        s = float(c.get("s", c.get("start", 0)))
        e = float(c.get("e", c.get("end", 0)))
        for z in zones:
            if s < float(z["end"]) and e > float(z["start"]):
                fails.append(f"{name} [{s:.1f},{e:.1f}] 与禁区 "
                             f"[{z['start']:.1f},{z['end']:.1f}]({z.get('reason','')}) 重叠")
        if s < a.head_sec:
            warns.append(f"{name} 起点 {s:.1f}s 在片头重灾区(前{a.head_sec}s)内"
                         "——必须已目核 ad_scan_head.png，且起点在片头结束点之后")
        if e > dur - a.tail_sec:
            warns.append(f"{name} 止点 {e:.1f}s 在片尾重灾区(后{a.tail_sec}s)内"
                         "——必须已目核 ad_scan_tail.png，且止点在片尾起点之前")

    print(f"片长 {dur:.1f}s | 段数 {len(clips)} | 禁区 {len(zones)} 个")
    if fails:
        print(f"\n=== FAIL {len(fails)} 项（段与禁区重叠，禁止采用）===")
        for x in fails:
            print("  ✗ " + x)
    else:
        print("=== 禁区重叠：0（PASS）===")
    if warns:
        print(f"\n=== WARN {len(warns)} 项（重灾区，须已目核）===")
        for x in warns:
            print("  ! " + x)
    sys.exit(1 if fails else 0)


def main():
    ap = argparse.ArgumentParser(description="v13.3 片源头尾广告风控扫描")
    ap.add_argument("mode", choices=["scan", "check"])
    ap.add_argument("video", help="scan: 片源; check: 片源(取时长)")
    ap.add_argument("arg2", nargs="?", default="",
                    help="scan: outdir; check: clips.json")
    ap.add_argument("--zones", default="ad_zones.json", help="check: 禁区清单")
    ap.add_argument("--interval", type=float, default=10, help="采样间隔秒，默认10")
    ap.add_argument("--head-sec", type=float, default=300, help="片头重灾区秒，默认300")
    ap.add_argument("--tail-sec", type=float, default=300, help="片尾重灾区秒，默认300")
    ap.add_argument("--w", type=int, default=384, help="缩略图宽，默认384")
    ap.add_argument("--cols", type=int, default=5)
    a = ap.parse_args()

    if a.mode == "scan":
        if not a.arg2:
            ap.error("scan 需要 <outdir>")
        a.outdir = a.arg2
        cmd_scan(a)
    else:
        if not a.arg2:
            ap.error("check 需要 <clips.json>")
        a.clips = a.arg2
        cmd_check(a)


if __name__ == "__main__":
    main()
