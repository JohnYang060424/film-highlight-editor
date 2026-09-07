# -*- coding: utf-8 -*-
"""check_delivery.py —— 交付数字自检（v13.2，交付前必跑）

背景：三件套文案里的数字（N个名场面/N章解说/总时长）靠人工核对，
蝴蝶效应首战曾出现"19个名场面"与实际 18 段不符（人肉才发现）。
本脚本自动核对文案数字 vs order.txt 实际段数与实测时长，不一致即告警。

用法：
  python check_delivery.py <B站三件套.txt> <order.txt> [--final final.mp4]

核对项：
  1. 文案 "N个名场面" vs order 里正片段数（basename 匹配 m\\d+.mp4）
  2. 文案 "N章...解说/N个转场" vs order 里转场数（trans_*.mp4）
  3. 文案 "XX.Xmin/X分X秒"（若提及总时长）vs --final 实测时长（±0.5min 容差）
全部一致 PASS；任一不符 FAIL 并列出正确值供修正文案。
"""
import argparse
import os
import re
import subprocess
import sys


def ffprobe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", help="B站三件套.txt")
    ap.add_argument("order", help="order.txt")
    ap.add_argument("--final", default=None, help="成片 mp4（核对总时长用）")
    a = ap.parse_args()

    txt = open(a.text, encoding="utf-8").read()
    lines = [ln.strip() for ln in open(a.order, encoding="utf-8")
             if ln.strip() and not ln.strip().startswith("#")]

    n_segs = sum(1 for ln in lines
                 if re.search(r"m\d+\.mp4", os.path.basename(ln.replace("\\", "/"))))
    n_trans = sum(1 for ln in lines
                  if re.search(r"(trans_\d+|card_\d+)\.mp4", os.path.basename(ln.replace("\\", "/"))))

    errors = []

    for m in re.finditer(r"(\d+)\s*个名场面", txt):
        claim = int(m.group(1))
        if claim != n_segs:
            errors.append(f"文案 '{claim}个名场面' ≠ 实际正片段 {n_segs} 段")

    for m in re.finditer(r"(\d+)\s*(?:章|个)(?:深度)?(?:解说|转场)", txt):
        claim = int(m.group(1))
        if claim != n_trans:
            errors.append(f"文案 '{m.group(0)}' ≠ 实际转场 {n_trans} 个")

    if a.final:
        dur = ffprobe_dur(a.final)
        if dur is None:
            errors.append(f"无法读取成片时长: {a.final}")
        else:
            dur_min = dur / 60
            for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:min|分钟)", txt):
                # 上下文含"原片/原作/原剧/原著"= 描述素材片长，不是成片时长声明，跳过
                ctx = txt[max(0, m.start() - 12):m.end() + 12]
                if re.search(r"原片|原作|原剧|原著|小说|版本", ctx):
                    continue
                claim = float(m.group(1))
                if abs(claim - dur_min) > 0.5:
                    errors.append(f"文案 '{m.group(0)}' ≠ 实测 {dur_min:.1f}min")

    print(f"实际：正片段 {n_segs} 段 / 转场 {n_trans} 个 / order 共 {len(lines)} 行")
    if a.final:
        d = ffprobe_dur(a.final)
        print(f"成片实测：{d/60:.1f}min")
    if errors:
        print("[FAIL] 数字不符：")
        for e in errors:
            print("  ✗", e)
        sys.exit(1)
    print("[PASS] 三件套数字与 order/实测一致")


if __name__ == "__main__":
    main()
