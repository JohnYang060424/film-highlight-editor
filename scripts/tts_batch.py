#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_batch.py — 流程步骤7：edge-tts 批量合成解说音频（含超时兜底）
用法:
  python tts_batch.py <texts.json> [--outdir audio] [--voice zh-CN-YunxiNeural]

texts.json 格式:
  [{"name":"trans_01","text":"第一段解说..."}, ...]

行为（与 SKILL.md 一致）:
  - asyncio.wait_for 超时 45s（edge-tts 可能挂起不抛异常，卡死整批）
  - 已存在且 >1KB 的 mp3 跳过
  - 失败自动降级多音色重试: YunxiNeural -> XiaoxiaoNeural -> YunyangNeural
  - v11 音色一致性（manifest 机制）：outdir/tts_manifest.json 记录每个 mp3
    实际使用的音色（缓存文件的音色来自 manifest，不是猜的）。批末若 manifest
    中实际音色 ≥2 种，统一为多数音色（平票回退 --voice）并删除不一致 mp3
    重合成，保证整片旁白音色一致。
    哪吒实战教训：① 降级 fallback 混用男女声听感割裂；② 仅靠"本轮是否降级"
    检测不到缓存文件与新文件的音色差异，必须有 manifest 记账。
"""
import argparse, asyncio, json, os, sys
from collections import Counter

VOICES_FALLBACK = ["zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-YunyangNeural"]
TIMEOUT = 45

async def synth(text, voice, out_mp3):
    import edge_tts
    c = edge_tts.Communicate(text, voice)
    await c.save(out_mp3)

async def synth_with_timeout(text, voice, out_mp3):
    await asyncio.wait_for(synth(text, voice, out_mp3), timeout=TIMEOUT)

def load_manifest(outdir):
    p = os.path.join(outdir, "tts_manifest.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception as ex:
            print(f"[warn] manifest 读取失败: {ex}")
    return {}

def save_manifest(outdir, manifest):
    with open(os.path.join(outdir, "tts_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

def batch(items, outdir, voices, manifest):
    """合成一轮。返回 (ok数, 失败名列表, {name: 实际音色})。
    缓存项的实际音色从 manifest 读取（"(unknown)" 表示无记录）。"""
    ok, fail, used = 0, [], {}
    for it in items:
        name, text = it["name"], it["text"]
        out_mp3 = os.path.join(outdir, name + ".mp3")
        if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1024:
            print(f"[skip] {name} 已存在")
            ok += 1
            used[name] = manifest.get(name, "(unknown)")
            continue
        done = False
        for attempt, voice in enumerate(voices, 1):
            try:
                asyncio.run(synth_with_timeout(text, voice, out_mp3))
                if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1024:
                    print(f"[ok] {name} <- {voice}")
                    ok += 1; used[name] = voice; done = True
                    break
                print(f"[warn] {name} 文件过小，重试")
            except Exception as ex:
                print(f"[warn] {name} {voice} 第{attempt}次失败: {type(ex).__name__} {ex}")
        if not done:
            fail.append(name)
            print(f"[FAIL] {name} 所有音色均失败")
    return ok, fail, used

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texts")
    ap.add_argument("--outdir", default="audio")
    ap.add_argument("--voice", default=VOICES_FALLBACK[0])
    ap.add_argument("--no-unify", action="store_true",
                    help="禁用 v11 音色一致性统一重合成")
    ap.add_argument("--unify-to", default="",
                    help="强制全部条目统一为该音色（含无 manifest 记录的缓存文件），"
                         "用于历史缓存音色未知时人工指定统一音色")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    with open(a.texts, encoding="utf-8") as f:
        items = json.load(f)
    voices = [a.voice] + [v for v in VOICES_FALLBACK if v != a.voice]
    manifest = load_manifest(a.outdir)
    ok, fail, used = batch(items, a.outdir, voices, manifest)
    manifest.update({k: v for k, v in used.items()
                     if v and v not in ("(cached)", "(unknown)")})

    # v11 音色一致性：manifest 实际音色 >=2 种 -> 统一为多数音色（平票回退 --voice）；
    # 历史缓存音色无记录时用 --unify-to 人工指定统一音色
    if not a.no_unify and not fail:
        real = {n: v for n, v in manifest.items() if v and v != "(unknown)"}
        counts = Counter(real.values())
        target = a.unify_to
        if not target and len(counts) > 1:
            target = sorted(counts, key=lambda v: (-counts[v], v != a.voice))[0]
        if target:
            unknown_names = sorted(n for n, v in manifest.items()
                                   if not v or v == "(unknown)")
            if unknown_names:
                print(f"[warn] 缓存项音色无 manifest 记录、无法自动验证: {unknown_names}"
                      f"（若与 {target} 不符请手工删除对应 mp3 后重跑）")
            redo = sorted(n for n in real if real[n] != target)
            if redo:
                print(f"\n[unify] 实际音色 {dict(counts)}，统一为 {target}，"
                      f"重合成 {len(redo)} 项: {redo}")
                for n in redo:
                    p = os.path.join(a.outdir, n + ".mp3")
                    try:
                        os.remove(p)
                    except OSError as ex:
                        print(f"[warn] 删除 {p} 失败: {ex}")
                redo_items = [it for it in items if it["name"] in redo]
                ok2, fail2, used2 = batch(redo_items, a.outdir, [target], manifest)
                manifest.update(used2)
                if fail2:
                    fail = fail2

    save_manifest(a.outdir, manifest)
    print(f"\n[done] 成功 {ok} / 失败 {len(fail)}" + (f"，失败项: {fail}" if fail else ""))
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
