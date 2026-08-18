#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_env_check.py — v10 L3 B类累积漂移判级（50Hz 包络相关，交付判级依据）

为什么不用波形 xcorr（万能钥匙实测教训）:
  - v1 固定模板: 配乐段 c<0.3 不可信，出现 -780ms 假匹配误报 FAIL。
  - v2 滑窗选优+c>=0.3 门槛: AAC 重编码改变波形相位、周期性配乐旁瓣峰高，
    仍出现 ±180ms 假锁峰，高 c 也不保险。
  - v3 包络相关: RMS 能量包络形状对重编码不敏感，9/9 测点 off=±0ms、c=1.000。
  波形 xcorr 仅作初筛，本脚本为判级依据。

判级三件套（三者同真才 PASS）:
  1. 偏移-成片时间 Pearson 相关 ≈0（累积漂移必单调增长，显著正相关才判 FAIL）；
  2. 末段 off ≈0（≤60ms，包络分辨率 20ms 放宽）；
  3. 逐点 |off| ≤ 60ms。
假匹配先验: 偏移在段间震荡而无单调趋势 ⇒ 大概率假匹配，不判 FAIL
（三件套之 Pearson 项即显式检验单调性）。

用法:
  python qc_env_check.py <源片> <成片> <order.txt> <clips_snap.json> [--tests m00,m05,...]

order.txt: 装配顺序纯路径清单（与 assemble.py 输入一致）；
           脚本对每段 ffprobe 解码帧数建"段起点累积表"（不用容器时长）。
clips_snap.json: keyframes.py 输出的 snap 后切点表。
--tests 缺省 = 全部 mNN 段按片长位置均匀抽 9 点（早/中/晚覆盖）。
"""
import argparse, json, os, subprocess
import numpy as np

SR = 8000
ENV_HZ = 50.0            # 包络帧率（20ms 分辨率，足以判 ≥40ms 漂移阈值）
WIN = int(SR / ENV_HZ)
TPL = 4.0                # 模板窗长（秒）
STEP = 1.0               # 段内滑窗步长
SEARCH = 1.5             # 成片搜索半窗（秒）
C_MIN = 0.35             # 包络匹配置信门槛
OFF_MAX = 0.060          # 逐点偏移上限（秒）
CORR_MAX = 0.5           # |Pearson| 超过即判单调增长


def ffprobe_frames(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1",
         path], capture_output=True, text=True, check=True).stdout.strip()
    return int(out)


def ffprobe_fps(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1",
         path], capture_output=True, text=True, check=True).stdout.strip()
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def raw_audio(video, ss, dur):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}",
                        "-t", f"{dur:.3f}", "-i", video, "-vn", "-ac", "1",
                        "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.int16).astype(np.float64)


def envelope(x):
    n = len(x) // WIN
    x = x[:n * WIN].reshape(n, WIN)
    return np.sqrt((x ** 2).mean(axis=1))


def env_xcorr_off(tpl_a, final_env, theo_abs):
    te = envelope(tpl_a)
    tc = te - te.mean()
    tnorm = (tc ** 2).sum()
    if tnorm == 0:
        return None, 0.0
    c_lo = max(0, int((theo_abs - SEARCH) * ENV_HZ))
    c_hi = min(len(final_env), int((theo_abs + SEARCH) * ENV_HZ) + len(tc))
    seg_env = final_env[c_lo:c_hi]
    base = int((theo_abs - SEARCH) * ENV_HZ) - c_lo
    best_c, best_lag = -1e18, base
    for k in range(int(2 * SEARCH * ENV_HZ) + 1):
        lag = base + k
        if lag < 0 or lag + len(tc) > len(seg_env):
            continue
        x = seg_env[lag:lag + len(tc)]
        xc = x - x.mean()
        d = np.sqrt((xc ** 2).sum() * tnorm)
        if d == 0:
            continue
        cc = (xc * tc).sum() / d
        if cc > best_c:
            best_c, best_lag = cc, lag
    return (c_lo + best_lag) / ENV_HZ, best_c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("final")
    ap.add_argument("order"); ap.add_argument("clips")
    ap.add_argument("--tests", default="")
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.order))
    # 起点表算法（万能钥匙回归实测教训）：
    # normalize 装配把每段重采样到成片帧率，成片内该段帧数 V=round(段真实时长×成片fps)，
    # 段在成片中的时长 = V/成片fps（装配校验 成片帧数==ΣV 保证）。
    # 两种常见错法：① 容器 duration 累加（priming/舍入，~0.09s/段偏差）；
    # ② 段文件帧数÷段自身帧率（段文件还是源帧率如 23.976，normalize 重采样后
    #    成片内帧数≠段文件帧数，逐段 -10~+18ms 误差累积出假"单调漂移"，
    #    Pearson 假阳性 FAIL）。正确：先算段真实时长=段帧数÷段帧率，
    #    再 V=round(时长×成片fps)，累加 V/成片fps。
    fps_final = ffprobe_fps(a.final)
    names, starts = [], {}
    acc = 0.0
    for line in open(a.order, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line if os.path.exists(line) else os.path.join(base, line)
        nm = os.path.splitext(os.path.basename(p))[0]
        dur_seg = ffprobe_frames(p) / ffprobe_fps(p)
        V = int(round(dur_seg * fps_final))
        names.append(nm)
        starts[nm] = acc
        acc += V / fps_final

    clips = json.load(open(a.clips, encoding="utf-8"))
    seg_names = [c["name"].split("_")[0] for c in clips]
    # 命名解耦映射（哪吒实战发现）：cut_sync 按数组下标命名段文件 mNN，
    # 与 clips_snap 的 name 前缀（nNN 等）可能不同；按下标建立 前缀→mNN 映射，
    # 测点名先查 starts，查不到再经映射回 order 基名。
    clip_to_order = {c["name"].split("_")[0]: f"m{i:02d}" for i, c in enumerate(clips)}
    if a.tests:
        tests = [t.strip() for t in a.tests.split(",") if t.strip()]
    else:
        tests = [seg_names[i] for i in
                 np.linspace(0, len(seg_names) - 1, min(9, len(seg_names))).round().astype(int)]
        tests = list(dict.fromkeys(tests))

    print(f"== B类累积判级（50Hz 包络相关，v10 交付判级依据）==")
    print(f"成片 {len(names)} 段，总长 {acc:.2f}s；测点: {', '.join(tests)}")
    final_env = envelope(raw_audio(a.final, 0, acc))

    rows = []
    for nm in tests:
        c = next((x for x in clips if x["name"].split("_")[0] == nm), None)
        onm = nm if nm in starts else clip_to_order.get(nm)
        if c is None or onm is None or onm not in starts:
            print(f"  {nm:>6}  SKIP（clips_snap/order 中找不到）"); continue
        st_key = onm
        s, e, dur = c["s"], c["e"], c["e"] - c["s"]
        cands, w = [], 0.5
        while w + TPL <= dur - 0.5:
            tpl = raw_audio(a.src, s + w, TPL)
            # 段内容自 snap 点 s 起占据成片 [starts[st_key], +V/fps]，
            # 源时间 s+w 对应成片位置 starts[st_key]+w（无 snap 修正项！）
            theo = starts[st_key] + w
            meas, cc = env_xcorr_off(tpl, final_env, theo)
            if meas is not None:
                cands.append((cc, meas - theo, w))
            w += STEP
        if not cands:
            print(f"  {nm:>6}  NO_CANDIDATE（段太短）"); continue
        bc, boff, bw = max(cands, key=lambda t: t[0])
        rel = bc >= C_MIN
        rows.append((nm, starts[st_key], boff, bc, rel))
        tag = "OK" if rel else "UNRELIABLE(c<%.2f)" % C_MIN
        print(f"  {nm:>6}  start={starts[st_key]:7.1f}s  win@{bw:5.1f}s  "
              f"c={bc:.3f}  off={boff*1000:+7.1f}ms  -> {tag}")

    rel = [r for r in rows if r[4]]
    print(f"  高置信测点 = {len(rel)}/{len(rows)}")
    if len(rel) < 2:
        print("== B类判定: 高置信测点不足，无法判级（补测点或查源） ==")
        return
    offs = np.array([r[2] for r in rel])
    st = np.array([r[1] for r in rel])
    # Pearson 仅在偏移幅度 ptp≥20ms（包络分辨率）时有意义：off 全≈0 时
    # 相关系数是浮点噪声（哪吒实测 9/9 off=±0.0ms 却 Pearson=-0.621 误判 FAIL）。
    ptp = offs.max() - offs.min()
    corr = np.corrcoef(st, offs)[0, 1] if st.std() > 0 and offs.std() > 0 and ptp >= 0.02 else 0.0
    last = rows[-1][2]
    print(f"  三件套: Pearson={corr:+.3f}(|.|<{CORR_MAX}无单调增长) | "
          f"末段off={last*1000:+.1f}ms(<=60) | 最大|off|={abs(offs).max()*1000:.1f}ms(<=60)")
    ok = abs(corr) < CORR_MAX and abs(last) <= OFF_MAX and all(abs(offs) <= OFF_MAX)
    print(f"== B类判定: {'PASS（无累积漂移）' if ok else 'FAIL'} ==")
    if not ok and abs(corr) >= CORR_MAX:
        print("  提示: 先按假匹配先验复核——偏移若震荡无单调趋势，多为假锁峰而非真漂移。")


if __name__ == "__main__":
    main()
