#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble.py — 流程步骤10：拼接（音画同步生死线，v7 归一化根治版）
用法:
  python assemble.py <order.txt> [--final final.mp4] [--mode normalize|copy]

order.txt: 每行一个文件路径（绝对或相对），按拼接顺序排列，# 开头为注释。
  ⚠ 必须与 clips 清单逐段核对（增删段后最易漏改 order）。

--mode normalize（默认，v8 网格量化版，2026-08-11 实测根治）:
  拼接前对每段做"帧网格量化"归一化，再 concat filter 完整重编码:
    时长量化: V = round(段真实时长 × FPS)  →  段输出时长 = V/FPS
    视频: fps=FPS,scale,setpts=N/FPS/TB,trim=end_frame=V,setpts  → 恰好 V 帧
    音频: aresample=48000,asetpts,apad,atrim=end_sample=V×(48000/FPS),
          asetpts  → 恰好与视频同长的样本数
    ⚠ v7 的 atrim=duration 不是逐样本精确的（按音频帧边界舍入，单段实测
      多留 7ms 尾巴），且 fps 滤镜会给段尾补帧 —— 两者误差在 concat 边界
      不能抵消，逐边界累积 +3~4ms 漂移（32 分钟成片尾部实测音频滞后 90ms，
      对白嘴型明显错位）。v8 双流按 end_frame/end_sample 裁成严格等长，
      边界误差恒为 0，不再累积；量化尾差 ≤半帧（40ms@25fps 时 ≤20ms）
      落在每个剪切点上，观感无感。
  然后 concat=n=N:v=1:a=1 + libx264 crf18 + AAC 48k 192k 单一 CFR 流。
  装配后校验成片视频帧数 == Σ V（不等即装配失步，必须报错）。

  为什么必须归一化（旧方案实测数据）:
  - concat filter 直接拼原始段: 混合链路转场后段标记 +0.050s（不可接受）
  - concat demuxer -c copy: 段边界 edit list 泄漏，残余 ~0.04s
  - MPEG-TS 路径: 音频抢前+尾部裁剪，4 段累积 +0.14s
  三者均被 normalize 方案根治。

--mode copy（快速路径，仅当确认各段已归一化/参数严格一致时）:
  concat demuxer 直接拼参数统一的 MP4，全程 -c copy，速度最快无重编码。
  ⚠ 前提苛刻: 每段视频帧网格、音频时长都必须已与视频严格对齐；
  cut_segments 产出的段虽已统一编码参数，但 AAC priming 仍在，混合链路
  下仍有累积风险 → 交付级成片一律用 normalize。
"""
import argparse, os, subprocess, sys

def run_ffprobe(args):
    return subprocess.run(["ffprobe", "-v", "error"] + args,
                          capture_output=True, text=True, check=True).stdout.strip()

def ffprobe_dur(path, stream="v:0"):
    r = run_ffprobe(["-select_streams", stream, "-show_entries",
                     "stream=duration", "-of", "default=nw=1:nk=1", path]).split()
    if not r:
        r = run_ffprobe(["-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", path]).split()
    try:
        return float(r[0])
    except (IndexError, ValueError):
        return 0.0

def video_real_duration(path):
    """视频真实时长 = 解码帧数 / 帧率（容器 duration 受 priming/舍入影响，不可信）。"""
    fps = run_ffprobe(["-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                       "-of", "default=nw=1:nk=1", path])
    num, _, den = fps.partition("/")
    fps_f = float(num) / float(den or 1)
    frames = run_ffprobe(["-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=nb_read_frames",
                          "-of", "default=nw=1:nk=1", path])
    return int(frames) / fps_f, fps_f

def seg_params(path):
    """返回 (视频参数串, 音频参数串)，copy 模式拼接前一致性校验用。"""
    def q(sel, entries):
        return "|".join(x.strip() for x in run_ffprobe(
            ["-select_streams", sel, "-show_entries", entries,
             "-of", "default=nw=1", path]).splitlines())
    return (q("v:0", "stream=codec_name,width,height,r_frame_rate,pix_fmt"),
            q("a:0", "stream=codec_name,sample_rate,channels"))

def concat_copy(filelist, final):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", filelist, "-c", "copy", "-movflags", "+faststart", final],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg ERROR]", r.stderr[-1000:], file=sys.stderr)
        sys.exit(1)

def assemble_normalize(files, final, crf=18, preset="medium"):
    """网格量化归一化拼接 (v8, 零边界漂移, 2026-08-11 实测根治)。

    每段: V = round(真实时长 × FPS) 帧, N = V × (48000/FPS) 样本
      视频: fps,scale,setpts=N/FPS/TB,tpad(末帧克隆兜底),trim=end_frame=V,setpts
      音频: aresample=48000,asetpts,apad,atrim=end_sample=N,asetpts
    双流裁成严格等长 → concat 每个边界 v/a 误差恒为 0，漂移无从累积。
    tpad/apad 保证"够长可裁"（fps 尾帧舍入可能差 1 帧，克隆补齐无碍观感）。
    ⚠ 勿改回 v7 的 atrim=duration：它按音频帧边界舍入（单段实测多留 7ms），
      叠加 fps 尾帧补齐，逐边界累积 +3~4ms（30 段成片尾部音频滞后 90ms）。
    装配后校验成片帧数 == Σ V，不等即失败退出。
    """
    # 以第一段为基准统一分辨率/帧率
    wh = run_ffprobe(["-select_streams", "v:0", "-show_entries", "stream=width,height",
                      "-of", "csv=p=0", files[0]])
    w, h = [int(x) for x in wh.split(",")]
    _, fps_f = video_real_duration(files[0])
    fps_f = round(fps_f, 3)
    spr = 48000.0 / fps_f                    # 每帧对应 48k 样本数

    fc, Vs = [], []
    for i, src in enumerate(files):
        dur, _ = video_real_duration(src)
        V = int(round(dur * fps_f)); Vs.append(V)
        N = int(round(V * spr))
        fc.append(f"[{i}:v]fps={fps_f:g},scale={w}:{h},setpts=N/{fps_f:g}/TB,"
                  f"tpad=stop_duration={2/fps_f:.3f},trim=end_frame={V},"
                  f"setpts=PTS-STARTPTS[v{i}]")
        fc.append(f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS,apad,"
                  f"atrim=end_sample={N},asetpts=PTS-STARTPTS[a{i}]")
        print(f"  [{i:02d}] {os.path.basename(src):>28}  {dur:8.3f}s -> {V:5d} 帧 ({V/fps_f:.3f}s)")
    n = len(files)
    inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filtergraph = ";\n".join(fc) + f";\n{inputs}concat=n={n}:v=1:a=1[v][a]"
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for src in files:
        cmd += ["-i", src]
    cmd += ["-filter_complex", filtergraph,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            "-movflags", "+faststart", final]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg ERROR]", r.stderr[-1200:], file=sys.stderr)
        sys.exit(1)
    # 装配完整性校验: 成片帧数必须 == Σ V（v8 由构造保证，失配即失败）
    fr = int(run_ffprobe(["-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=nb_read_frames",
                          "-of", "default=nw=1:nk=1", final]))
    exp = sum(Vs)
    if fr != exp:
        print(f"[FATAL] 装配失步: 成片 {fr} 帧 != 期望 {exp} 帧", file=sys.stderr)
        sys.exit(1)
    print(f"[ok] 帧网格校验通过: 成片 {fr} 帧 == Σ 段帧数 {exp}")
    return sum(Vs) / fps_f

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("order")
    ap.add_argument("--final", default="final.mp4")
    ap.add_argument("--mode", default="normalize", choices=["normalize", "copy"])
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    a = ap.parse_args()
    with open(a.order, encoding="utf-8") as f:
        files = [ln.strip() for ln in f
                 if ln.strip() and not ln.strip().startswith("#")]
    for src in files:
        if not os.path.exists(src):
            print(f"[FATAL] 不存在: {src}"); sys.exit(1)
    print(f"共 {len(files)} 个输入段，模式 = {a.mode}")

    if a.mode == "copy":
        base_v, base_a = seg_params(files[0])
        for i, src in enumerate(files[1:], 1):
            v, au = seg_params(src)
            if v != base_v or au != base_a:
                print(f"[FATAL] 段参数不一致，copy 直拼会失步/报错:")
                print(f"  seg0                : v[{base_v}] a[{base_a}]")
                print(f"  seg{i} {os.path.basename(src)}: v[{v}] a[{au}]")
                print("  → 改用 --mode normalize（归一化重编码，无此限制）")
                sys.exit(1)
        total_v = sum(ffprobe_dur(s) for s in files)
        filelist = a.final + ".filelist.txt"
        with open(filelist, "w", encoding="utf-8") as f:
            for src in files:
                f.write(f"file '{os.path.abspath(src)}'\n")
        concat_copy(filelist, a.final)
    else:
        total_v = assemble_normalize(files, a.final, a.crf, a.preset)

    fv = ffprobe_dur(a.final); fa = ffprobe_dur(a.final, "a:0")
    print(f"\n[ok] 成片 {a.final}")
    print(f"     输入段 v 时长合计 {total_v:.3f}s | 成片 v={fv:.3f}s a={fa:.3f}s")
    print(f"     v-a 总差 = {abs(fv-fa):.3f}s  (≤0.1s 属正常: AAC priming + fps 尾帧取整；")
    print(f"       内容级同步与时长无关，交付前必跑 verify_sync.py 做 PTS/内容级验证)")

if __name__ == "__main__":
    main()
