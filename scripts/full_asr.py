#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
full_asr.py — 全片离线 ASR（vosk-zh），产出带时间戳的台词轴（v14 通读素材用）

用法:
  python full_asr.py <视频或wav路径> <输出前缀> [--sr 16000]
产物:
  <前缀>.json   [{start,end,text}...]（秒，float）
  <前缀>.txt    [MM:SS-MM:SS] 文本   （人读通读稿）
说明:
  - 模型固定用技能包 models/vosk-zh（相对本脚本解析，零硬编码盘符）
  - 输入非 wav 时自动 ffmpeg 抽 16k 单声道临时 wav（写到输出前缀旁，完成后删除）
  - 141 分钟片约 10-20 分钟跑完（CPU 实时率 8-15x）
"""
import os, sys, json, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.abspath(os.path.join(HERE, '..', 'models', 'vosk-zh'))

def _ascii_model_path(path):
    """vosk C++ 层不吃非 ASCII 路径（模型本身没坏）。路径含非 ASCII 时，
    在本脚本 scratch 处建 ASCII 名 junction 指回模型目录。"""
    try:
        path.encode('ascii')
        return path
    except UnicodeEncodeError:
        pass
    import _winapi, tempfile
    j = os.path.join(tempfile.gettempdir(), 'film_hde_vosk_junction')
    try:
        if os.path.islink(j) or os.path.isdir(j):
            os.rmdir(j)  # junction 用 rmdir 解链，不伤目标
    except OSError:
        pass
    try:
        _winapi.CreateJunction(path, j)
        return j
    except OSError:
        return path  # 兜底：仍返回原路径（失败时报错文案里有真实模型名，便于定位）

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    src, out_prefix = sys.argv[1], sys.argv[2]
    sr = 16000
    if '--sr' in sys.argv:
        sr = int(sys.argv[sys.argv.index('--sr') + 1])
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    os.makedirs(os.path.dirname(os.path.abspath(out_prefix)) or '.', exist_ok=True)

    wav = src
    tmp = None
    if not src.lower().endswith('.wav'):
        tmp = out_prefix + '.16k.wav'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
                        '-ac', '1', '-ar', str(sr), '-c:a', 'pcm_s16le', tmp], check=True)
        wav = tmp

    t0 = time.time()
    model = Model(_ascii_model_path(MODEL))
    rec = KaldiRecognizer(model, sr)
    rec.SetWords(False)
    segments = []
    consumed = 0.0      # 已喂入音频秒数
    seg_start = 0.0      # 当前段起点=上次出结果时的 consumed
    import wave
    with wave.open(wav, 'rb') as wf:
        chunk = int(sr * 0.4)  # 0.4s per chunk
        while True:
            data = wf.readframes(chunk)
            if not data:
                break
            consumed += len(data) / 2 / sr
            if rec.AcceptWaveform(data):
                r = json.loads(rec.Result())
                if r.get('text'):
                    segments.append({'start': round(seg_start, 2), 'end': round(consumed, 2),
                                     'text': r['text']})
                seg_start = consumed
            if int(consumed * 10) % 2000 == 0:
                print(f'  ... {consumed/60:.1f} min processed, {len(segments)} segs', flush=True)
    r = json.loads(rec.FinalResult())
    if r.get('text'):
        segments.append({'start': round(seg_start, 2), 'end': round(consumed, 2), 'text': r['text']})

    # 段边界用累计文本长度粗略对齐即可；如需精确时间戳用 SetWords(True) 版
    with open(out_prefix + '.json', 'w', encoding='utf-8') as f:
        json.dump(segments, f, ensure_ascii=False, indent=1)
    def mmss(t): return f'{int(t)//60:02d}:{int(t)%60:02d}'
    with open(out_prefix + '.txt', 'w', encoding='utf-8') as f:
        for s in segments:
            f.write(f'[{mmss(s["start"])}-{mmss(s["end"])}] {s["text"]}\n')
    if tmp and os.path.exists(tmp):
        os.remove(tmp)
    print(f'ASR DONE segs={len(segments)} elapsed={time.time()-t0:.0f}s -> {out_prefix}.json/.txt')

if __name__ == '__main__':
    main()
