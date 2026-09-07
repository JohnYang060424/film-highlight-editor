#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_bailian.py — 流程步骤7：百炼（阿里云 Model Studio）TTS 批量合成解说音频（v14 主力引擎）

引擎: qwen3-tts-flash（voice=Bellona，即官方"精品百人-燕铮莺"）。
     ※ cosyvoice-v3.5-plus 系统音色表【没有】燕铮莺（复刻音色除外，实测挂 Bellona 报 418
       InvalidParameter）；"燕铮莺/Bellona" 属百炼 Qwen-TTS 家族。同 key 同账号，非浏览器 TTS。

用法:
  python tts_bailian.py <texts.json> [--outdir audio] [--voice Bellona] [--model qwen3-tts-flash]

texts.json 格式（与 tts_batch.py 兼容，多可选 "engine"/"voice" 覆盖）:
  [{"name":"trans_01","text":"第一段解说..."}, ...]

行为:
  - API key 读取顺序: 环境变量 DASHSCOPE_API_KEY -> HERMES_CUSTOM_AISIA_CFY_BAILIAN_API_KEY
    -> 从 cwd 向上找 .env（技能包根/工作根，只补不覆盖）。绝不写死在代码里。
  - 每段独立合成，流式 chunk 逐段 base64 解码后拼 PCM 帧（注意：chunk 的 data 字段是
    独立 base64 段，跨 chunk 先 join 字符串再 b64decode 会解坏——实测只有首帧 0.32s）。
  - 段级缓存: outdir/<name>.wav 已存在且 >4KB 则跳过；--force 全量重合成。
  - 重试: 每段最多 3 次（间隔 2s），仍失败 → 非零退出并列出失败段名（失败隔离在台账层）。
  - 超长校验: 单段 >512 字符直接 FAIL（模型上限），要求上游拆段。
  - 产出: outdir/<name>.wav（24kHz mono PCM）+ outdir/tts_manifest.json
    （engine/voice/每段 sha256 前8位/时长/采样率；供 cut_sync 与台账核对）。

开源/密钥纪律: 本文件不含任何密钥字面量；.env 已在 .gitignore。
"""
import argparse, base64, hashlib, json, os, sys, time


def load_env_upwards(cwd=None, levels=5):
    p = os.path.join(cwd or os.getcwd(), ".env")
    for _ in range(levels):
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
            return True
        p = os.path.join(os.path.dirname(p), ".env")
    return False


def get_key():
    load_env_upwards()
    for k in ("DASHSCOPE_API_KEY", "HERMES_CUSTOM_AISIA_CFY_BAILIAN_API_KEY"):
        v = os.environ.get(k)
        if v and v.startswith("sk-"):
            return v
    return None


def _strip_wav_header(b):
    """返回 (pcm_bytes, sample_rate)；RIFF 头按 data 子块定位（头长可能 44/58 不等）。"""
    import struct
    if b[:4] != b"RIFF":
        return b, 24000
    pos, sr, pcm = 12, 24000, None
    while pos + 8 <= len(b):
        cid = b[pos:pos + 4]
        sz = struct.unpack("<I", b[pos + 4:pos + 8])[0]
        if cid == b"fmt ":
            sr = struct.unpack("<I", b[pos + 8 + 4:pos + 8 + 8])[0]
        elif cid == b"data":
            pcm = b[pos + 8:pos + 8 + sz] if pos + 8 + sz <= len(b) else b[pos + 8:]
            break
        pos += 8 + sz + (sz & 1)
    return (pcm if pcm is not None else b[44:]), sr


def synth_one(dashscope, text, voice, model):
    """流式合成一段。坑：每个 chunk 的 data 是【独立 base64 的整 wav 帧】（各自带
    RIFF 头，首帧 size 字段是占位值），直接拼接再按 wave 读会得假时长(实测 44739s)。
    正确做法：逐 chunk 剥头拼 PCM，最后用真实 PCM 长度重写 wav 头。"""
    import struct
    resp = dashscope.MultiModalConversation.call(
        model=model, text=text, voice=voice, stream=True, language_type="Chinese")
    pcm, sr = b"", 24000
    for c in resp:
        try:
            data = c.output.audio.data
        except Exception:
            data = None
        if data:
            one, srr = _strip_wav_header(base64.b64decode(data))
            sr = srr or sr
            pcm += one
    if len(pcm) < 1000:
        raise RuntimeError("empty audio (engine returned no stream chunks)")
    hdr = struct.pack("<4sI4s", b"RIFF", 36 + len(pcm), b"WAVE")
    hdr += struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, sr, sr * 2, 2, 16)
    hdr += struct.pack("<4sI", b"data", len(pcm))
    return hdr + pcm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texts")
    ap.add_argument("--outdir", default="audio")
    ap.add_argument("--voice", default="Bellona")
    ap.add_argument("--model", default="qwen3-tts-flash")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    key = get_key()
    if not key:
        sys.exit("FAIL: no DASHSCOPE_API_KEY (env or .env upwards). 见本文件头。")
    import dashscope
    dashscope.api_key = key

    items = json.load(open(a.texts, encoding="utf-8"))
    os.makedirs(a.outdir, exist_ok=True)
    manifest_path = os.path.join(a.outdir, "tts_manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:
            manifest = {}
    manifest.setdefault("segments", {})

    failed = []
    for it in items:
        name, text = it["name"], it["text"].strip()
        voice = it.get("voice", a.voice)
        out = os.path.join(a.outdir, name + ".wav")
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        if len(text) > 512:
            failed.append((name, f"text too long ({len(text)}>512) — split upstream"))
            continue
        cached = (not a.force and os.path.exists(out) and os.path.getsize(out) > 4096
                  and manifest["segments"].get(name, {}).get("hash") == h)
        if cached:
            print(f"cache {name}", flush=True)
            continue
        ok = False
        for attempt in range(1, 4):
            try:
                wav = synth_one(dashscope, text, voice, a.model)
                tmp = out + ".part"
                open(tmp, "wb").write(wav)
                os.replace(tmp, out)
                import wave, io
                with wave.open(io.BytesIO(wav)) as w:
                    dur = w.getnframes() / w.getframerate()
                    sr = w.getframerate()
                manifest["segments"][name] = {"hash": h, "voice": voice,
                                              "model": a.model, "dur": round(dur, 2),
                                              "sr": sr}
                json.dump(manifest, open(manifest_path, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                print(f"ok {name} {dur:.1f}s", flush=True)
                ok = True
                break
            except Exception as e:
                print(f"retry {attempt} {name}: {str(e)[:120]}", flush=True)
                time.sleep(2)
        if not ok:
            failed.append((name, "3 attempts failed"))

    if failed:
        print("FAILED:", failed, flush=True)
        sys.exit(2)
    print(f"DONE {len(items)} segments -> {a.outdir}/", flush=True)


if __name__ == "__main__":
    main()
