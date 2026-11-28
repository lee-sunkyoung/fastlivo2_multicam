#!/usr/bin/env python3
"""
Phase 3/4 분석: 한 시퀀스(mainlab|2ndfloor)의 조건별 런 그룹에 대해
  - 궤적 정량 지표(루프 자기 일관성(겹침 오차, 끝점→1회차 경로), 평지 z 이탈, 시작~끝 차이, 5회 편차: 3D / along-track / cross-track / z)
  - img_stats / 처리시간 요약
  - 드롭 프레임 비교(런 간 일치율·Jaccard, k-of-N 분포 vs 이항분포, 시간축 히스토그램, 드롭 원인 단서)
그림: results/<seq>/*.png, 수치: results/<seq>/metrics.json, 표: results/<seq>/auto_tables.md

사용: python3 scripts/analyze_seq.py mainlab [--conds both left right fastlio]
"""
import argparse
import json
import sys
from itertools import combinations
from math import comb
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import (RES_DIR, bag_image_stamps, col_f, frame_index, endpoint_drift, loop_metrics, group_deviation, horizontal_axes, jaccard,
                          load_tum, path_file, read_csv, run_dirs, ts_key)

COLORS = {"both": "tab:blue", "left": "tab:orange", "right": "tab:green", "fastlio": "tab:red",
          "both_drop20": "tab:purple", "both_drop50": "tab:brown", "both_diag": "tab:cyan"}
# selected csv의 cam 번호 -> 물리 카메라(0=left, 1=right)
PHYS = {"both": {0: 0, 1: 1}, "left": {0: 0}, "right": {0: 1}, "both_drop20": {0: 0, 1: 1}, "both_drop50": {0: 0, 1: 1},
        "both_diag": {0: 0, 1: 1}}
CAM_NAME = {0: "left", 1: "right"}
DIV_Z, DIV_D = 5.0, 150.0  # 발산 판정: 평지에서 |z| 이탈 > 5 m 또는 출발점에서 > 150 m


def fmt(x, n=3):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{n}f}"


def traj_metrics(seq, conds, outdir):
    groups = {}
    for c in conds:
        ds = run_dirs(seq, c)
        runs = []
        for d in ds:
            pf = path_file(d)
            if pf.exists() and pf.stat().st_size > 0:
                runs.append((d.name, *load_tum(pf)))
        if runs:
            groups[c] = runs
    if not groups:
        return {}, None
    # 전역 복도 축: 모든 런의 지배 heading (조건 간 같은 축으로 비교)
    allxyz = np.vstack([x for g in groups.values() for _, _, x in g])
    axes = horizontal_axes(allxyz)
    M = {"axes": {"along": axes[0].tolist(), "cross": axes[1].tolist()}, "groups": {}}
    for c, runs in groups.items():
        drifts = [endpoint_drift(t, x, axes) for _, t, x in runs]
        loops = [loop_metrics(t, x, axes) or {} for _, t, x in runs]
        g = {"runs": [n for n, _, _ in runs],
             "drift": [d["drift"] for d in drifts], "drift_xy": [d["drift_xy"] for d in drifts],
             "drift_along": [d["along"] for d in drifts], "drift_cross": [d["cross"] for d in drifts],
             "drift_z": [d["dz"] for d in drifts],
             "loop": loops,
             "duration": [float(t[-1] - t[0]) for _, t, _ in runs],
             "length": [float(np.linalg.norm(np.diff(x, axis=0), axis=1).sum()) for _, _, x in runs]}
        maxd = [float(np.linalg.norm(x[:, :2] - x[0, :2], axis=1).max()) for _, _, x in runs]
        zab = [float(np.abs(x[:, 2] - x[0, 2]).max()) for _, _, x in runs]
        g["max_dist"], g["z_absmax"] = maxd, zab
        g["diverged"] = [bool(z > DIV_Z or m > DIV_D) for z, m in zip(zab, maxd)]
        ok_runs = [r for r, dv in zip(runs, g["diverged"]) if not dv]
        if len(ok_runs) >= 2 and len(ok_runs) < len(runs):
            _, _, _, dev_ok, _ = group_deviation([(t, x) for _, t, x in ok_runs])
            g["dev_mean_nondiverged"] = {k: float(np.mean([d[k] for d in dev_ok])) for k in dev_ok[0]}
        if len(runs) >= 2:
            tg, P, mean, dev, spread = group_deviation([(t, x) for _, t, x in runs])
            g["dev"] = dev
            g["dev_mean"] = {k: float(np.mean([d[k] for d in dev])) for k in dev[0]}
            g["end_spread"] = float(np.sqrt(((P[:, -1] - P[:, -1].mean(0)) ** 2).sum(1).mean()))
            g["_tg"], g["_mean"], g["_spread"], g["_P"] = tg, mean, spread, P
        M["groups"][c] = g
    return M, groups


def plot_traj(seq, M, groups, outdir):
    conds = list(groups)
    fig, axs = plt.subplots(1, len(conds) + 1, figsize=(5 * (len(conds) + 1), 5), squeeze=False)
    allxyz = np.vstack([x for g in groups.values() for _, _, x in g])
    lo, hi = allxyz[:, :2].min(0), allxyz[:, :2].max(0)
    pad = 0.05 * (hi - lo).max()
    for ax, c in zip(axs[0], conds):
        cmap = plt.get_cmap({"both": "Blues", "left": "Oranges", "right": "Greens", "fastlio": "Reds"}.get(c, "Greys"))
        for k, (n, t, x) in enumerate(groups[c]):
            ax.plot(x[:, 0], x[:, 1], color=cmap(0.4 + 0.6 * k / max(1, len(groups[c]) - 1)), lw=1, label=n.split("_")[-1])
        if "_mean" in M["groups"][c]:
            m = M["groups"][c]["_mean"]
            ax.plot(m[:, 0], m[:, 1], "k-", lw=1.5, label="mean")
        ax.plot(0, 0, "o", color="lime", mec="k", ms=7)
        ax.set_title(f"{seq} {c} (n={len(groups[c])})")
        ax.set_aspect("equal"); ax.set_xlim(lo[0] - pad, hi[0] + pad); ax.set_ylim(lo[1] - pad, hi[1] + pad)
        ax.grid(alpha=.3); ax.legend(fontsize=7)
    ax = axs[0][-1]
    for c in conds:
        if "_mean" in M["groups"][c]:
            m = M["groups"][c]["_mean"]
            ax.plot(m[:, 0], m[:, 1], color=COLORS.get(c), lw=1.5, label=c)
    ax.set_title("mean trajectories"); ax.set_aspect("equal"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout()
    p = outdir / "traj_xy.png"
    fig.savefig(p, dpi=130); plt.close(fig)

    # drift / deviation bars
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    for i, c in enumerate(conds):
        g = M["groups"][c]
        for j, (key, ax) in enumerate(zip(["drift", "drift_xy"], axs[:2])):
            v = np.array(g[key])
            ax.bar(i, v.mean(), color=COLORS.get(c), alpha=.5)
            ax.scatter(np.full(len(v), i) + np.linspace(-.15, .15, len(v)), v, color="k", s=12, zorder=3)
        if "dev" in g:
            v = np.array([d["rms3d"] for d in g["dev"]])
            axs[2].bar(i, v.mean(), color=COLORS.get(c), alpha=.5)
            axs[2].scatter(np.full(len(v), i) + np.linspace(-.15, .15, len(v)), v, color="k", s=12, zorder=3)
    for ax, t in zip(axs, ["endpoint drift 3D [m]", "endpoint drift horizontal [m]", "RMS dev. from group mean [m]"]):
        ax.set_xticks(range(len(conds))); ax.set_xticklabels(conds); ax.set_title(f"{seq}: {t}"); ax.grid(alpha=.3, axis="y")
    fig.tight_layout()
    p2 = outdir / "drift_dev_bars.png"
    fig.savefig(p2, dpi=130); plt.close(fig)

    # run-to-run spread over time
    fig, ax = plt.subplots(figsize=(11, 3.8))
    for c in conds:
        g = M["groups"][c]
        if "_spread" in g:
            ax.plot(g["_tg"] - g["_tg"][0], g["_spread"], color=COLORS.get(c), label=c, lw=1)
    ax.set_xlabel("time since start [s]"); ax.set_ylabel("RMS spread across runs [m]"); ax.set_title(f"{seq}: run-to-run spread over time")
    ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); p3 = outdir / "spread_time.png"; fig.savefig(p3, dpi=130); plt.close(fig)
    return [p, p2, p3]


# ------------------------------------------------------------------ img stats / timing
def stats_metrics(seq, conds):
    S = {}
    for c in conds:
        if c == "fastlio":
            continue
        rows = []
        for d in run_dirs(seq, c):
            f = d / f"{d.name}_img_stats.csv"
            if not f.exists():
                continue
            _, cols = read_csv(f)
            r = {"run": d.name, "cams": []}
            for i in range(len(cols["cam"])):
                cam = int(cols["cam"][i])
                r["cams"].append({k: float(cols[k][i]) for k in cols if k != "cam"} | {"cam": cam, "phys": PHYS[c][cam]})
            tf = d / f"{d.name}_timing.csv"
            if tf.exists():
                _, tc = read_csv(tf)
                typ = np.array(tc["type"]); pm = col_f(tc, "proc_ms")
                r["lio_ms_mean"], r["lio_ms_p95"] = float(pm[typ == "LIO"].mean()), float(np.percentile(pm[typ == "LIO"], 95))
                r["vio_ms_mean"], r["vio_ms_p95"] = float(pm[typ == "VIO"].mean()), float(np.percentile(pm[typ == "VIO"], 95))
                a2s = col_f(tc, "arrival_to_start_ms")[typ == "VIO"]
                r["arrival_to_vio_ms_mean"], r["arrival_to_vio_ms_p95"] = float(np.nanmean(a2s)), float(np.nanpercentile(a2s, 95))
                # 한 프레임 처리 사이클(LIO+VIO) 시간
                st = col_f(tc, "sensor_time")
                cyc = {}
                for ty, t, v in zip(typ, st, pm):
                    cyc[round(t, 6)] = cyc.get(round(t, 6), 0.0) + v
                cv = np.array(list(cyc.values()))
                r["cycle_ms_mean"], r["cycle_ms_p95"] = float(cv.mean()), float(np.percentile(cv, 95))
            rows.append(r)
        S[c] = rows
    return S


# ------------------------------------------------------------------ drop comparison
def drop_metrics(seq, conds, outdir, bin_s=5.0):
    stamps = bag_image_stamps(seq)
    D = {}
    figs = []
    for c in conds:
        if c == "fastlio":
            continue
        ds = run_dirs(seq, c)
        if not ds:
            continue
        sel = []  # per run: {phys: set(keys)}
        reasons, lags = [], []
        windows = []
        for d in ds:
            _, cols = read_csv(d / f"{d.name}.csv")
            cam = np.array([int(x) for x in cols["cam"]]); t = col_f(cols, "capture_time")
            s = {}
            for k in PHYS[c]:
                idx, nmiss = frame_index(stamps[PHYS[c][k]], t[cam == k])
                s[PHYS[c][k]] = set(idx.tolist())
                if nmiss:
                    print(f"  [warn] {d.name} cam{k}: {nmiss} selected stamps not matched to bag frames")
            sel.append(s)
            windows.append((t.min(), t.max()))
            df = d / f"{d.name}_drops.csv"
            rr = {}
            lg = {"old_lag": [], "old_age": [], "sel_age": []}
            if df.exists():
                _, dc = read_csv(df)
                for r in dc["reason"]:
                    rr[r] = rr.get(r, 0) + 1
                rs = np.array(dc["reason"])
                lg["old_lag"] = col_f(dc, "data_lag_s")[rs == "old"].tolist()
                lg["old_age"] = col_f(dc, "wall_age_ms")[rs == "old"].tolist()
                lg["old_t"] = col_f(dc, "capture_time")[rs == "old"].tolist()
            if "wall_age_ms" in cols:
                lg["sel_age"] = col_f(cols, "wall_age_ms").tolist()
            reasons.append(rr); lags.append(lg)
        w0 = max(w[0] for w in windows); w1 = min(w[1] for w in windows)
        T0 = min(w[0] for w in windows)
        g = {"runs": [d.name for d in ds], "window": [w0, w1], "reasons": reasons, "per_cam": {}}
        fig, axs = plt.subplots(len(PHYS[c]), 2, figsize=(14, 3.6 * len(PHYS[c])), squeeze=False)
        for row, phys in enumerate(sorted(set(PHYS[c].values()))):
            bs = stamps[phys]
            eligible = set(np.where((bs >= w0 - 1e-4) & (bs <= w1 + 1e-4))[0].tolist())
            drops = [eligible - s[phys] for s in sel]
            n = len(ds)
            inter = set.intersection(*drops) if drops else set()
            union = set.union(*drops) if drops else set()
            pair = [jaccard(a, b) for a, b in combinations(drops, 2)]
            cnt = {}
            for dset in drops:
                for k in dset:
                    cnt[k] = cnt.get(k, 0) + 1
            kdist = [len(eligible) - len(cnt)] + [sum(1 for v in cnt.values() if v == k) for k in range(1, n + 1)]
            p = np.mean([len(x) / len(eligible) for x in drops])
            binom = [len(eligible) * comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)]
            g["per_cam"][CAM_NAME[phys]] = {
                "eligible": len(eligible), "drop_rate": [len(x) / len(eligible) for x in drops],
                "n_drop": [len(x) for x in drops], "all_runs": len(inter), "any_run": len(union),
                "consistency_inter_over_union": len(inter) / len(union) if union else 1.0,
                "pairwise_jaccard_mean": float(np.mean(pair)) if pair else None,
                "pairwise_jaccard_min": float(np.min(pair)) if pair else None,
                "pairwise_jaccard_max": float(np.max(pair)) if pair else None,
                "k_of_n_observed": kdist, "k_of_n_binomial_independent": binom,
            }
            # time histogram
            ax = axs[row][0]
            bins = np.arange(w0 - T0, w1 - T0 + bin_s, bin_s)
            for i, dset in enumerate(drops):
                tt = stamps[phys][np.array(sorted(dset), dtype=int)] - T0 if dset else np.array([])
                h, _ = np.histogram(tt, bins=bins)
                ax.step(bins[:-1], h, where="post", lw=1, alpha=.8, label=f"run{g['runs'][i].split('_')[-1]}")
            ax.set_title(f"{seq} {c} [{CAM_NAME[phys]} cam]: drops per {bin_s:.0f}s"); ax.set_xlabel("bag time [s]")
            ax.grid(alpha=.3); ax.legend(fontsize=7)
            ax = axs[row][1]
            ax.bar(np.arange(n + 1) - .2, kdist, width=.4, label="observed")
            ax.bar(np.arange(n + 1) + .2, binom, width=.4, label="independent (binomial)")
            ax.set_yscale("log"); ax.set_xlabel(f"#runs (of {n}) in which a frame was dropped"); ax.set_ylabel("#frames")
            ax.set_title(f"{CAM_NAME[phys]}: same frames dropped across runs?"); ax.legend(fontsize=8); ax.grid(alpha=.3)
        fig.tight_layout()
        p = outdir / f"drops_{c}.png"
        fig.savefig(p, dpi=120); plt.close(fig); figs.append(p)
        # cause clues: lag of dropped(old) frames vs wall age of selected frames
        ol = np.concatenate([np.array(l["old_lag"]) for l in lags]) if lags else np.array([])
        oa = np.concatenate([np.array(l["old_age"]) for l in lags]) if lags else np.array([])
        sa = np.concatenate([np.array(l["sel_age"]) for l in lags]) if lags else np.array([])
        g["old_data_lag_s"] = {"median": float(np.median(ol)) if ol.size else None, "p95": float(np.percentile(ol, 95)) if ol.size else None}
        g["old_wall_age_ms"] = {"median": float(np.median(oa)) if oa.size else None, "p95": float(np.percentile(oa, 95)) if oa.size else None}
        g["selected_wall_age_ms"] = {"median": float(np.median(sa)) if sa.size else None, "p95": float(np.percentile(sa, 95)) if sa.size else None,
                                     "max": float(np.max(sa)) if sa.size else None}
        D[c] = g
    return D, figs


def timing_drop_figure(seq, cond, outdir, bin_s=2.0):
    """첫 런: 처리 사이클 시간과 드롭(old) 발생의 시간 관계."""
    ds = run_dirs(seq, cond)
    if not ds:
        return None, None
    d = ds[0]
    tf, df = d / f"{d.name}_timing.csv", d / f"{d.name}_drops.csv"
    if not (tf.exists() and df.exists()):
        return None, None
    _, tc = read_csv(tf); _, dc = read_csv(df)
    typ = np.array(tc["type"]); st = col_f(tc, "sensor_time"); pm = col_f(tc, "proc_ms")
    T0 = st.min()
    cyc = {}
    for t, v in zip(st, pm):
        cyc[round(t, 6)] = cyc.get(round(t, 6), 0.0) + v
    ct = np.array(sorted(cyc)); cv = np.array([cyc[k] for k in ct])
    rs = np.array(dc["reason"]); dt_ = col_f(dc, "capture_time")[rs == "old"]
    bins = np.arange(0, ct.max() - T0 + bin_s, bin_s)
    hd, _ = np.histogram(dt_ - T0, bins=bins)
    idx = np.digitize(ct - T0, bins) - 1
    mc = np.array([cv[idx == i].mean() if np.any(idx == i) else np.nan for i in range(len(bins) - 1)])
    ok = np.isfinite(mc)
    r = float(np.corrcoef(mc[ok], hd[ok])[0, 1]) if ok.sum() > 3 else None
    fig, ax = plt.subplots(figsize=(12, 3.8))
    ax.plot(ct - T0, cv, lw=.5, color="gray", label="LIO+VIO cycle [ms]")
    ax.plot(bins[:-1] + bin_s / 2, mc, color="k", lw=1.2, label=f"cycle mean per {bin_s:.0f}s")
    ax.set_ylabel("ms"); ax.set_xlabel("bag time [s]")
    ax2 = ax.twinx(); ax2.step(bins[:-1], hd, where="post", color="tab:red", label="skipped(old) per bin")
    ax2.set_ylabel("#old drops", color="tab:red")
    ax.set_title(f"{d.name}: processing time vs old drops (bin corr r={fmt(r, 2)})")
    ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=.3)
    fig.tight_layout(); p = outdir / f"timing_vs_drops_{cond}.png"; fig.savefig(p, dpi=120); plt.close(fig)
    return p, r


def strip_private(o):
    if isinstance(o, dict):
        return {k: strip_private(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip_private(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def write_tables(seq, M, S, D, figs, corr, outdir):
    L = [f"## 자동 생성 표 — {seq}\n"]
    L.append("### 루프 자기 일관성 지표 (bag이 출발점에서 끝나지 않으므로 이것이 주 drift 지표; 단위 m, 평균 ± 표준편차)\n")
    L.append("| 조건 | n | 1→2회차 경로 겹침 오차 median | 겹침 오차 p90 | 끝점→1회차 경로 거리 | 출발점 재방문 최근접 거리 | z RMS (평지) | z 최대 이탈 | 1회차 분할 시각 [s] | 2회차 비율 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for c, g in M.get("groups", {}).items():
        lp = [l for l in g.get("loop", []) if l.get("overlap_med") is not None]
        if not lp:
            continue
        ms2 = lambda k: f"{np.mean([l[k] for l in lp]):.3f} ± {np.std([l[k] for l in lp]):.3f}"
        L.append(f"| {c} | {len(lp)} | {ms2('overlap_med')} | {ms2('overlap_p90')} | {ms2('end_to_loop1')} | {ms2('revisit')} | {ms2('z_rms')} | {ms2('z_absmax')} | {ms2('t_split')} | {ms2('frac_loop2')} |")
    L.append(f"\n발산 판정(|z|>{DIV_Z:.0f} m 또는 출발점에서 >{DIV_D:.0f} m): " + "; ".join(
        f"{c}: {sum(g['diverged'])}/{len(g['diverged'])} (z최대 " + ", ".join(f"{v:.1f}" for v in g["z_absmax"]) + "; 최대거리 " + ", ".join(f"{v:.0f}" for v in g["max_dist"]) + ")"
        for c, g in M.get("groups", {}).items()))
    for c, g in M.get("groups", {}).items():
        if "dev_mean_nondiverged" in g:
            dv = g["dev_mean_nondiverged"]
            L.append(f"- {c}: 발산 런 제외 5회 편차 RMS 3D {dv['rms3d']:.3f} m (along {dv['rms_along']:.3f}, cross {dv['rms_cross']:.3f}, z {dv['rms_z']:.3f})")
    L.append("\n런별 겹침 오차 p90: " + "; ".join(f"{c}: " + ", ".join(f"{l.get('overlap_p90', float('nan')):.2f}" for l in g.get("loop", [])) for c, g in M.get("groups", {}).items()) + "\n")
    L.append("### 궤적 지표 — 시작~끝 위치 차이 및 5회 편차 (단위 m, 평균 ± 표준편차)\n")
    L.append("주의: '시작~끝 차이'는 bag이 2회차 도중에 끝나서 drift가 아니라 '끝 위치 추정의 차이'다. 조건 간 비교용으로만 남긴다.\n")
    L.append("| 조건 | n | 시작~끝 3D | 시작~끝 수평 | along(복도축) | cross | z | 5회 편차 RMS 3D | along-track | cross-track | z | 끝점 산포 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c, g in M.get("groups", {}).items():
        ms = lambda v: f"{np.mean(v):.3f} ± {np.std(v):.3f}"
        dv = g.get("dev_mean", {})
        L.append(f"| {c} | {len(g['runs'])} | {ms(g['drift'])} | {ms(g['drift_xy'])} | {ms(np.abs(g['drift_along']))} | "
                 f"{ms(np.abs(g['drift_cross']))} | {ms(np.abs(g['drift_z']))} | {fmt(dv.get('rms3d'))} | {fmt(dv.get('rms_along'))} | "
                 f"{fmt(dv.get('rms_cross'))} | {fmt(dv.get('rms_z'))} | {fmt(g.get('end_spread'))} |")
    L.append("\n(along/cross: 절댓값 평균. along축 = 이동 heading의 지배 방향(직교 복도 가정) 중 총 이동이 긴 쪽 = 주 복도 축, axes: " + str(np.round(M["axes"]["along"], 3).tolist()) + ")\n")
    L.append("런별 시작~끝 3D: " + "; ".join(f"{c}: " + ", ".join(f"{v:.3f}" for v in g["drift"]) for c, g in M.get("groups", {}).items()) + "\n")
    if S:
        L.append("### img_stats / 처리 시간 (런 평균)\n")
        L.append("| 조건 | 카메라 | recv | used | skipped(old) | overflow | stale | forced | 총 드롭률 | LIO ms (평균/p95) | VIO ms (평균/p95) | 사이클 ms (평균/p95) | 도착→VIO ms (평균/p95) |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c, rows in S.items():
            if not rows:
                continue
            cams = sorted({cm["phys"] for r in rows for cm in r["cams"]})
            for ph in cams:
                vals = [cm for r in rows for cm in r["cams"] if cm["phys"] == ph]
                a = lambda k: np.mean([v[k] for v in vals])
                t = lambda k: np.mean([r[k] for r in rows if k in r]) if any(k in r for r in rows) else float("nan")
                L.append(f"| {c} | {CAM_NAME[ph]} | {a('recv'):.0f} | {a('used'):.0f} | {a('skipped_old'):.1f} | {a('overflow'):.1f} | {a('stale'):.1f} | "
                         f"{a('forced'):.1f} | {100 * a('total_drop_ratio'):.2f}% (런별 " + ", ".join(f"{100 * v['total_drop_ratio']:.1f}" for v in vals) + ") | "
                         f"{t('lio_ms_mean'):.1f}/{t('lio_ms_p95'):.1f} | {t('vio_ms_mean'):.1f}/{t('vio_ms_p95'):.1f} | "
                         f"{t('cycle_ms_mean'):.1f}/{t('cycle_ms_p95'):.1f} | {t('arrival_to_vio_ms_mean'):.1f}/{t('arrival_to_vio_ms_p95'):.1f} |")
    if D:
        L.append("\n### 드롭 프레임 런 간 비교 (bag 이미지 타임스탬프 기준, 공통 시간창 안)\n")
        L.append("| 조건 | 카메라 | 대상 프레임 | 런별 드롭 수 | 5회 모두 드롭 | 1회 이상 드롭 | ∩/∪ | 쌍별 Jaccard 평균 (최소~최대) | k-of-N 관측 | k-of-N 독립 가정 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for c, g in D.items():
            for cam, v in g["per_cam"].items():
                L.append(f"| {c} | {cam} | {v['eligible']} | {', '.join(map(str, v['n_drop']))} | {v['all_runs']} | {v['any_run']} | "
                         f"{v['consistency_inter_over_union']:.3f} | {fmt(v['pairwise_jaccard_mean'])} ({fmt(v['pairwise_jaccard_min'])}~{fmt(v['pairwise_jaccard_max'])}) | "
                         f"{v['k_of_n_observed']} | {[round(x, 1) for x in v['k_of_n_binomial_independent']]} |")
        L.append("\n드롭 원인 단서:\n")
        for c, g in D.items():
            rs = {}
            for r in g["reasons"]:
                for k, v in r.items():
                    rs[k] = rs.get(k, 0) + v
            L.append(f"- {c}: 드롭 이벤트 합계(5회) {rs}; old 드롭 프레임의 데이터 지연(horizon−capture) 중앙값 {fmt(g['old_data_lag_s']['median'])} s, "
                     f"p95 {fmt(g['old_data_lag_s']['p95'])} s; old 드롭 시 수신 후 경과 중앙값 {fmt(g['old_wall_age_ms']['median'], 1)} ms; "
                     f"선택된 프레임의 수신→선택 지연 중앙값 {fmt(g['selected_wall_age_ms']['median'], 1)} ms, p95 {fmt(g['selected_wall_age_ms']['p95'], 1)} ms, "
                     f"최대 {fmt(g['selected_wall_age_ms']['max'], 1)} ms")
        for c, r in corr.items():
            L.append(f"- {c} 첫 런: 2 s 구간별 (LIO+VIO 사이클 평균 시간) vs (old 드롭 수) 상관계수 r = {fmt(r, 2)}")
    L.append("\n### 그림\n")
    for f in figs:
        L.append(f"- `{f}`")
    (outdir / "auto_tables.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq")
    ap.add_argument("--conds", nargs="+", default=["both", "left", "right", "fastlio"])
    a = ap.parse_args()
    outdir = RES_DIR / a.seq
    outdir.mkdir(parents=True, exist_ok=True)
    M, groups = traj_metrics(a.seq, a.conds, outdir)
    figs = plot_traj(a.seq, M, groups, outdir) if groups else []
    S = stats_metrics(a.seq, a.conds)
    D, f2 = drop_metrics(a.seq, a.conds, outdir)
    figs += f2
    corr = {}
    for c in a.conds:
        if c != "fastlio":
            p, r = timing_drop_figure(a.seq, c, outdir)
            if p:
                figs.append(p); corr[c] = r
    (outdir / "metrics.json").write_text(json.dumps(strip_private({"traj": M, "stats": S, "drops": D, "timing_drop_corr": corr}), indent=1))
    write_tables(a.seq, M, S, D, figs, corr, outdir)
    print((outdir / "auto_tables.md").read_text())


if __name__ == "__main__":
    main()
