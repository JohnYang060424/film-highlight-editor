#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tail_guard.py —— v13.4 "找字游戏"双兜底（短片尾部截断人声检测）

问题（用户钦定 v13.4③）：成片短片结尾仍会"人讲话讲一半被截断"，观众难受。
产物标准：短片结尾 1-3s 应该是物体声/背景音/无声；**话说完+环境音收尾=合格**。

双兜底（对每段尾窗 [e-10, e] 做两层检测）：
  第1层 OCR：2fps 批量抽帧底部 40% 区域跑 RapidOCR，含≥2中文字符且非片尾
         字幕页白名单 = 有人讲话（中国发行片源几乎都带中文字幕，底部中文=说话）。
  第2层 ASR：尾窗音频走 vosk 中文小模型，产出≥2中文字符 = 有人讲话。

判定语义（v13.4 钦定）：
  PASS：最后 3s（--tail-clean，默认3）无命中——前面的对白已说完，环境音收尾；
  FAIL：最后 3s 有命中 = 截断人声。自动处置（零人工）：
    ① 先向后找：[e, e+6] 内找连续 3s 全干净窗，找到 → suggest_e = 窗末端；
    ② 找不到 → 向前躲：suggest_e = 尾窗内首个命中 - 0.3s。

性能：每段仅 2 次 ffmpeg（尾窗抽帧 + 尾窗+extend 抽 pcm）。

用法：
  python tail_guard.py <video> <clips_snap.json> [--win 10] [--tail-clean 3]
                       [--extend 6] [--model 模型目录] [--ocr-only] [--asr-only]
  单段调试：python tail_guard.py <video> --seg 120.0 137.64
依赖：rapidocr_onnxruntime + vosk；模型 ../models/vosk-zh（small-cn-0.22）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

FF = "ffmpeg"

CREDITS_RE = re.compile(
    r"(导演|主演|编剧|制片人|出品|监制|摄影|剪辑|美术|录音|作曲|作词|字幕组|"
    r"译制|配音|制作公司|发行|鸣谢|特别感谢|剧终|完|THE END|CAST|CREW|DIRECTED)")
ZH_RE = re.compile(r"[一-鿿]")


def grab_frames(video, t0, dur, fps, w=640, h=360):
    """单次 ffmpeg 批量抽帧，返回 [(t, arr)]"""
    p = subprocess.run(
        [FF, "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", video,
         "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    if p.returncode != 0:
        return []
    raw = p.stdout
    fb = w * h * 3
    n = len(raw) // fb
    return [(t0 + i / fps,
             np.frombuffer(raw[i * fb:(i + 1) * fb], dtype=np.uint8).reshape(h, w, 3))
            for i in range(n)]


def grab_pcm(video, t0, dur):
    """单次 ffmpeg 抽 16k mono pcm，返回 (pcm16, t0)"""
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            [FF, "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}",
             "-i", video, "-vn", "-ar", "16000", "-ac", "1", "-f", "wav", tmp],
            check=True, capture_output=True)
        import wave
        wf = wave.open(tmp, "rb")
        pcm16 = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        wf.close()
        return pcm16, t0
    except Exception as e:
        print(f"[warn] pcm 解码失败: {e}")
        return np.zeros(0, dtype=np.int16), t0
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


class OcrLayer:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR()

    def scan(self, video, t0, dur, fps=2.0):
        hits = []
        for t, arr in grab_frames(video, t0, dur, fps):
            res, _ = self.engine(arr[:, int(360 * 0.60):, ::-1])
            if not res:
                continue
            joined = " ".join(line[1] for line in res)
            if len("".join(ZH_RE.findall(joined))) >= 2 and not CREDITS_RE.search(joined):
                hits.append((t, joined.strip()))
        return hits


class AsrLayer:
    def __init__(self, model_dir):
        from vosk import Model, KaldiRecognizer
        self.rec = KaldiRecognizer(Model(model_dir), 16000)

    def scan_pcm(self, pcm16, t0):
        hits = []
        seg_len = 32000
        pos = 0
        while pos + seg_len <= len(pcm16):
            if self.rec.AcceptWaveform(pcm16[pos:pos + seg_len].tobytes()):
                txt = json.loads(self.rec.Result()).get("text", "")
            else:
                txt = json.loads(self.rec.PartialResult()).get("partial", "")
            if len("".join(ZH_RE.findall(txt))) >= 2:
                hits.append((t0 + pos / 16000.0, txt.strip()))
            pos += 4000
        final = json.loads(self.rec.FinalResult()).get("text", "")
        if len("".join(ZH_RE.findall(final))) >= 2:
            hits.append((t0 + len(pcm16) / 16000.0 - 0.5, final.strip()))
        return hits


def main():
    ap = argparse.ArgumentParser(description="v13.4 找字游戏双兜底")
    ap.add_argument("video")
    ap.add_argument("clips", nargs="?", default="")
    ap.add_argument("--seg", nargs=2, type=float, metavar=("S", "E"))
    ap.add_argument("--win", type=float, default=10.0)
    ap.add_argument("--tail-clean", type=float, default=3.0)
    ap.add_argument("--extend", type=float, default=6.0)
    ap.add_argument("--model", default="")
    ap.add_argument("--ocr-only", action="store_true")
    ap.add_argument("--asr-only", action="store_true")
    a = ap.parse_args()

    segs = ([{"name": "seg", "s": a.seg[0], "e": a.seg[1]}] if a.seg
            else json.load(open(a.clips, encoding="utf-8")))

    ocr = None if a.asr_only else OcrLayer()
    asr = None
    if not a.ocr_only:
        mdir = a.model or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "models", "vosk-zh")
        asr = AsrLayer(mdir) if os.path.isdir(mdir) else \
            print(f"[warn] vosk 模型缺失: {mdir} → 跳过 ASR 层")

    fails = passes = 0
    for c in segs:
        name = c.get("name", "?")
        s, e = float(c.get("s", c.get("start", 0))), float(c.get("e", c.get("end", 0)))
        win = min(a.win, e - s - 1.0)
        if win < a.tail_clean + 1:
            continue
        # 一次性抽 [e-16, e+6]（lo 量化 0.5s 网格锁绝对相位，收敛确定）
        lo = round(max(s + 1.0, e - 16.0) * 2) / 2
        hi = e + a.extend
        ocr0 = ocr.scan(a.video, lo, hi - lo, fps=2.0) if ocr else []
        # 相位确认：对每个相位0命中，定向抽 t+0.25 单帧复核（省全窗二次扫描）
        conf_ocr = []
        if ocr:
            for t, tx in ocr0:
                t2 = min(t + 0.25, hi - 0.1)
                arr = None
                for fr in grab_frames(a.video, t2, 0.5, 2.0, 640, 360)[:1]:
                    arr = fr[1]
                if arr is None:
                    continue
                res, _ = ocr.engine(arr[:, int(360 * 0.60):, ::-1])
                if res and len("".join(ZH_RE.findall(
                        " ".join(l[1] for l in res)))) >= 2:
                    conf_ocr.append((t, tx))
        asr_hits = []
        if asr:
            pcm, _ = grab_pcm(a.video, lo, hi - lo)
            asr_hits = asr.scan_pcm(pcm, lo)
        confirmed = [(t, "OCR", tx) for t, tx in conf_ocr] + \
                    [(t, "ASR", tx) for t, tx in asr_hits if t <= hi]
        union = [(t, "OCR", tx) for t, tx in ocr0] + \
                [(t, "ASR", tx) for t, tx in asr_hits if t <= hi]
        tail3 = [h for h in confirmed if h[0] >= e - a.tail_clean]
        if not tail3:
            n = len([h for h in confirmed if h[0] < e])
            note = f"（前段 {n} 处对白已说完，环境音收尾）" if n else ""
            print(f"[PASS] {name} e={e:.1f} 结尾{a.tail_clean:.0f}s 干净{note}")
            passes += 1
            continue
        # FAIL：在 [e-16, e+6] 内找"尾3s干净"的最大候选出点（并集严格搜索）
        # 命中按区间覆盖：OCR 字幕持续≈3s、ASR 语句≈2s，避免单点漏检
        ivals = [(t, t + (3.0 if layer == "OCR" else 2.0)) for t, layer, _ in union]

        def clean_at(cand):
            return not any(t0 < cand and t1 > cand - a.tail_clean
                           for t0, t1 in ivals)
        cands = np.arange(max(s + 2.0, e - 16.0), hi + 0.5, 0.5)
        clean_cands = [c for c in cands if clean_at(c)]
        mode = None
        suggest = None
        best_late = max([c for c in clean_cands if c >= e - 0.25], default=None)
        if best_late is not None:
            suggest = round(min(best_late, hi), 2)
            mode = "向后延" if best_late > e else "微前移"
        else:
            best_early = max([c for c in clean_cands if c <= e], default=None)
            if best_early is not None:
                suggest = round(best_early, 2)
                mode = "向前躲"
        if suggest is None or suggest < s + 2.0:
            first_t = min(h[0] for h in tail3)
            suggest = round(max(s + 2.0, first_t - 0.3), 2)
            mode = "向前躲"
        fails += 1
        print(f"[FAIL] {name} e={e:.1f} 结尾{a.tail_clean:.0f}s 截断人声:")
        for t, layer, tx in tail3[:4]:
            print(f"    {layer}@{t:.1f}s: {tx[:40]}")
        print(f"    自动处置({mode}) → suggest_e={suggest}")

    print(f"\n=== 找字游戏汇总：{passes} PASS / {fails} FAIL ===")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
