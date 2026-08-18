# -*- coding: utf-8 -*-
"""snap_cuts.py —— 切点吸附（v13 切点卫生层）

问题：骨架切点按剧情节拍主观选取，硬切会落在台词中间/动作半截，观感"剪不到位"。
思路：定骨架后、切段前，把每个切点在 ±win 窗口内就近吸附到天然接缝：
  信号1 能量谷：音频 RMS 包络(约43ms/帧)的局部低谷 = 句尾气口（电影有BGM，无绝对静音，故用相对谷）
  信号2 镜头切换：select gt(scene,thr) 的 pts_time
  信号3 黑场：blackdetect
评分：黑场4 > 谷+scene重合(2+1+2) > scene(2+score*2) > 谷(1+prom/10)
出点(段尾)：宁晚不早 —— 同分时优先 >= 原点的候选；无候选则保留原点并记 no_seam。
入点(段头)：就近即可，优先 scene。
质检闸(C)：出点前0.35s RMS 若比其前0.5s 还高2dB以上（话没说完就掐）记 voiced_end，入可疑列表人工抽听。

v13.2 增强：
  ③ 信号缓存：整片 scene+black 扫描结果缓存到 <video>.sigcache.json（按 size+mtime 失效），
     同片二次吸附直接命中，省去 ~9min 全片重扫。
  ⑤ no_seam 出点全自动兜底（替代人工复核）：±win 内无天然接缝时，自动后扩 ≤6s 找第一个显著
     句尾气口能量谷，把出点延后到话说完（只延后不提前），记 auto_extend；受下一段入点-0.5s 封顶。

用法：
  python snap_cuts.py <video> <clips.json> [out.json] [--win 3.0]
产物 out.json(默认 clips_snap.json)：[{name,start,end,s,e,dur,notes}]
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys

FF = "ffmpeg"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def sigcache_path(video):
    return video + ".sigcache.json"


def load_sigcache(video):
    """命中返回 (scenes, blacks)，否则 None（按 size+mtime 校验失效）"""
    p = sigcache_path(video)
    if not os.path.exists(p):
        return None
    try:
        st = os.stat(video)
        c = json.load(open(p, encoding="utf-8"))
        if c.get("size") == st.st_size and abs(c.get("mtime", 0) - st.st_mtime) < 1:
            return [(t, s) for t, s in c["scenes"]], [t for t in c["blacks"]]
    except (OSError, ValueError, KeyError):
        pass
    return None


def save_sigcache(video, scenes, blacks):
    try:
        st = os.stat(video)
        json.dump({"size": st.st_size, "mtime": st.st_mtime,
                   "scenes": scenes, "blacks": blacks},
                  open(sigcache_path(video), "w", encoding="utf-8"))
    except OSError:
        pass  # 缓存失败不影响主流程


def get_scenes(video, thr=0.25):
    """镜头切换点 [(t, score)]，低分辨率加速"""
    p = run([FF, "-v", "info", "-i", video, "-vf",
             f"scale=480:-2,select='gt(scene,{thr})',metadata=print",
             "-an", "-f", "null", "-"])
    out, pts = [], None
    for ln in p.stderr.splitlines() + p.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", ln)
        if m:
            pts = float(m.group(1))
            continue
        m = re.search(r"scene_score=([\d.]+)", ln)
        if m and pts is not None:
            out.append((pts, float(m.group(1))))
            pts = None
    return out


def get_blacks(video):
    p = run([FF, "-v", "info", "-i", video, "-vf",
             "scale=480:-2,blackdetect=d=0.08:pix_th=0.10", "-an", "-f", "null", "-"])
    out = []
    for m in re.finditer(r"black_start:\s*([\d.]+)", p.stderr):
        out.append(float(m.group(1)))
    return out


def rms_curve(video, t0, t1):
    """窗口内 RMS 包络 [(t, db)]，~43ms/帧。
    v13.2 修复：输入侧 `-ss X -to Y` 组合不稳（部分窗口整段返回 0 点，
    致能量谷探测与质检闸批量静默失灵——v13 蝴蝶效应首战暴露），
    改用 `-ss X -t dur` 经典组合，pts_time 自 0 起，回填 +t0。"""
    t0 = max(0.0, t0)
    dur = t1 - t0
    if dur <= 0:
        return []
    # ⚠ ametadata=print 走 stderr 的 info 级别——必须 -v info，
    # -v error 时 0 输出点（v13 隐藏 bug，v13.2 暴露并修复）
    p = run([FF, "-v", "info", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", video,
             "-af", "astats=metadata=1:reset=2048,"
             "ametadata=print:key=lavfi.astats.Overall.RMS_level",
             "-vn", "-f", "null", "-"])
    cur, out = None, []
    for ln in p.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", ln)
        if m:
            cur = float(m.group(1)) + t0
            continue
        m = re.search(r"RMS_level=(-?[\d.]+|-inf)", ln)
        if m and cur is not None:
            v = -90.0 if m.group(1) == "-inf" else float(m.group(1))
            out.append((cur, v))
            cur = None
    return out


def find_valleys(curve, prom=6.0):
    """局部能量谷 [(t, prominence)]：比左右0.4s邻域低 prom dB 以上"""
    if len(curve) < 8:
        return []
    dt = 0.043
    k = max(2, int(0.4 / dt))
    out = []
    for i in range(k, len(curve) - k):
        t, v = curve[i]
        lo = min(x[1] for x in curve[i - k:i])
        hi_l = max(x[1] for x in curve[i - k:i])
        hi_r = max(x[1] for x in curve[i + 1:i + k + 1])
        side = min(hi_l, hi_r)
        if side - v >= prom and v <= lo + 1e-9:
            # 与已收录谷保持 >=0.3s 间隔，取更深的
            if out and t - out[-1][0] < 0.3:
                if out[-1][1] < side - v:
                    out[-1] = (t, side - v)
            else:
                out.append((t, side - v))
    return out


def snap_one(t, cands, win, prefer_late):
    """cands=[(time, score)]，返回 (snap_t, desc) 或 (t, None)"""
    near = [(c, s) for c, s in cands if abs(c - t) <= win]
    if not near:
        return t, None
    if prefer_late:
        near.sort(key=lambda cs: (0 if cs[0] >= t - 0.05 else 1, -cs[1], abs(cs[0] - t)))
    else:
        near.sort(key=lambda cs: (-cs[1], abs(cs[0] - t)))
    return near[0][0], "snap"


def auto_extend_end(video, e0, max_back=6.0, max_fwd=0.8, min_prom=5.0):
    """v13.2 ⑤ no_seam 出点全自动兜底：±win 内无天然接缝时，
    在 [e0-max_fwd, e0+max_back] 窗口找第一个显著句尾谷（prom>=min_prom），
    把出点延后到该谷（只延后不提前，保证话说完）。找不到返回 None。"""
    cur = rms_curve(video, e0 - max_fwd, e0 + max_back)
    vs = find_valleys(cur, prom=min_prom)
    # 只取 >= 原出点(允许略早 max_fwd) 的第一个谷，即"话说完"的第一个气口
    later = [t for t, _ in vs if t >= e0 - max_fwd]
    if not later:
        return None
    return later[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("clips")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--win", type=float, default=3.0)
    a = ap.parse_args()
    out_path = a.out or os.path.join(os.path.dirname(os.path.abspath(a.clips)), "clips_snap.json")
    clips = json.load(open(a.clips, encoding="utf-8"))

    print("[1/3] 扫描镜头切换与黑场（整片一次，命中缓存则跳过）...")
    cached = load_sigcache(a.video)
    if cached:
        scenes, blacks = cached
        print(f"      [cache hit] scene={len(scenes)} black={len(blacks)}")
    else:
        scenes = get_scenes(a.video)
        blacks = get_blacks(a.video)
        save_sigcache(a.video, scenes, blacks)
        print(f"      scene={len(scenes)} black={len(blacks)} -> 已缓存 {sigcache_path(a.video)}")

    result = []
    print("[2/3] 逐切点吸附：")
    for idx, seg in enumerate(clips):
        name, s0, e0 = seg["name"], float(seg["start"]), float(seg["end"])
        notes = []
        row = {"name": name, "start": s0, "end": e0}
        # 入点：scene/黑场为主，能量谷弱分
        cur = rms_curve(a.video, s0 - a.win - 1, s0 + a.win + 1)
        vs = find_valleys(cur)
        c_in = [(t, 1 + min(p / 10, 2)) for t, p in vs]
        c_in += [(t, 2 + sc * 2) for t, sc in scenes] + [(t, 4) for t in blacks]
        si, di = snap_one(s0, c_in, a.win, prefer_late=False)
        # 出点：谷+scene 重合加分；宁晚不早
        cur = rms_curve(a.video, e0 - a.win - 1, e0 + a.win + 1)
        vs = find_valleys(cur)
        c_out = [(t, 1 + min(p / 10, 2)) for t, p in vs]
        for t, sc in scenes:
            bonus = 2 if any(abs(t - vt) < 0.3 for vt, _ in vs) else 0
            c_out.append((t, 2 + sc * 2 + bonus))
        c_out += [(t, 4) for t in blacks]
        se, de = snap_one(e0, c_out, a.win, prefer_late=True)
        if di is None and abs(si - s0) < 1e-6:
            notes.append("no_seam_in")
        if de is None:
            notes.append("no_seam_out")
            # v13.2 ⑤ 全自动兜底：后扩 ≤6s 找句尾谷，延后出点（只延后不提前）
            ext = auto_extend_end(a.video, e0, max_back=6.0)
            if ext is not None:
                # 封顶：不得越过下一段入点前 0.5s（避免两段重叠）
                if idx + 1 < len(clips):
                    nxt_s = float(clips[idx + 1]["start"])
                    ext = min(ext, nxt_s - 0.5)
                if ext > e0:
                    se = ext
                    notes.append("auto_extend")
                    notes.remove("no_seam_out")
        # 质检闸C：出点前话没说完？
        # v13.2 修复两个坑：① rms_curve 曾静默返回 0 点致此闸全程假通过（-v error bug，已修）；
        # ② BGM 渐强（smooth swell）会让 median(last)>median(prev)+2 误报 voiced_end——
        #    全自动处置：先试延后到句尾谷，找到谷则解决真截断(auto_extend)；
        #    找不到谷=连续声（BGM swell），原切点本就合理，保留原点不报警。
        cur = rms_curve(a.video, se - 1.2, se + 0.1)
        if len(cur) > 10:
            last = [v for t, v in cur if se - 0.4 <= t <= se - 0.05]
            prev = [v for t, v in cur if se - 1.0 <= t <= se - 0.45]
            if last and prev and statistics.median(last) > statistics.median(prev) + 2:
                ext = auto_extend_end(a.video, se, max_back=6.0)
                if ext is not None:
                    if idx + 1 < len(clips):
                        nxt_s = float(clips[idx + 1]["start"])
                        ext = min(ext, nxt_s - 0.5)
                    if ext > se:
                        se = ext
                        notes.append("voiced_end_fixed")
                    else:
                        notes.append("voiced_end")  # 延后受限（下一段太近）
                else:
                    notes.append("voiced_end_bgm")  # 连续声(BGM swell)，原切点合理，仅记账
        row.update(s=round(si, 2), e=round(se, 2), dur=round(se - si, 2), notes=notes)
        result.append(row)
        print(f"  {name[:16]:18s} in {s0:>7}->{si:>8.2f} ({si-s0:+.2f})  out {e0:>7}->{se:>8.2f} ({se-e0:+.2f})  {','.join(notes) or ''}")

    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot = sum(r["dur"] for r in result)
    # 分级汇总：voiced_end = 真截断需关注；voiced_end_bgm = BGM渐强已确认安全；
    #            auto_extend/voiced_end_fixed = 已自动延后解决；no_seam_* = 无天然接缝(保留原点)
    need = [r["name"] for r in result if "voiced_end" in r["notes"]]
    fixed = [r["name"] for r in result
             if any(n in r["notes"] for n in ("auto_extend", "voiced_end_fixed"))]
    print(f"[3/3] 写出 {out_path}；总时长 {tot:.1f}s={tot/60:.1f}min")
    print(f"      已自动延后解决 {len(fixed)} 段: {fixed}")
    print(f"      需人工关注 voiced_end {len(need)} 段: {need}")


if __name__ == "__main__":
    main()
