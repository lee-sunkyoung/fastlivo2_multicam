#!/usr/bin/env python3
"""
Phase 5: mainlab both(인위적 드롭 0) → both_drop20 → both_drop50 비교.
가로축 = 실제 총 드롭률(자연 + 인위적, 카메라 평균, img_stats csv).
세로축 = mainlab 주 지표(루프 자기 일관성: 1→2회차 겹침 오차 p90, 끝점→1회차 경로 거리, z 최대 이탈), 5회 편차, 기준(both) 평균 궤적까지 거리.
끝점 drift(시작~끝)는 bag이 2회차 도중 끝나 drift가 아니므로 참고용으로만 metrics.json에 남긴다.
출력: results/drop_ablation/{ablation.png, metrics.json, auto_tables.md}
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr, kendalltau

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import (RES_DIR, common_grid, endpoint_drift, group_deviation, horizontal_axes, interp_xyz, load_tum, loop_metrics,
                          path_file, read_csv, run_dirs)

SEQ = "mainlab"
CONDS = [("both", 0.0), ("both_drop20", 0.2), ("both_drop50", 0.5)]
COL = {"both": "tab:blue", "both_drop20": "tab:purple", "both_drop50": "tab:brown"}


def main():
    out = RES_DIR / "drop_ablation"
    out.mkdir(parents=True, exist_ok=True)
    groups = {}
    for c, ratio in CONDS:
        rs = []
        for d in run_dirs(SEQ, c):
            st = d / f"{d.name}_img_stats.csv"
            if not st.exists() or not path_file(d).exists():
                continue
            _, cols = read_csv(st)
            tdr = np.mean([float(x) for x in cols["total_drop_ratio"]])
            forced = sum(int(x) for x in cols["forced"])
            elig = sum(int(x) for x in cols["eligible"])
            old = sum(int(x) for x in cols["skipped_old"]); stale = sum(int(x) for x in cols["stale"]); ovf = sum(int(x) for x in cols["overflow"])
            t, x = load_tum(path_file(d))
            rs.append({"name": d.name, "total_drop": tdr, "forced_frac": forced / elig, "natural_frac": (old + stale + ovf) / elig,
                       "old_frac": old / elig, "stale_frac": stale / elig, "ovf_frac": ovf / elig, "t": t, "x": x})
        if rs:
            groups[c] = {"ratio": ratio, "runs": rs}
    if not groups:
        print("no data"); return
    allx = np.vstack([r["x"] for g in groups.values() for r in g["runs"]])
    axes = horizontal_axes(allx)
    base_mean = None
    if "both" in groups and len(groups["both"]["runs"]) >= 2:
        tgb, _, base_mean, _, _ = group_deviation([(r["t"], r["x"]) for r in groups["both"]["runs"]])
    M = {}
    for c, g in groups.items():
        for r in g["runs"]:
            dr = endpoint_drift(r["t"], r["x"], axes)
            r["drift"], r["drift_xy"], r["along"], r["cross"], r["dz"] = dr["drift"], dr["drift_xy"], dr["along"], dr["cross"], dr["dz"]
            lm = loop_metrics(r["t"], r["x"], axes) or {}
            for k in ["overlap_med", "overlap_p90", "end_to_loop1", "z_absmax", "revisit"]:
                if lm.get(k) is not None:
                    r[k] = lm[k]
            r["diverged"] = bool(np.abs(r["x"][:, 2] - r["x"][0, 2]).max() > 5 or np.linalg.norm(r["x"][:, :2] - r["x"][0, :2], axis=1).max() > 150)
            if base_mean is not None:
                xb = interp_xyz(r["t"], r["x"], tgb)
                r["rms_to_base_mean"] = float(np.sqrt(((xb - base_mean) ** 2).sum(1).mean()))
        dev = None
        if len(g["runs"]) >= 2:
            _, _, _, dev, _ = group_deviation([(r["t"], r["x"]) for r in g["runs"]])
            for r, d in zip(g["runs"], dev):
                r["rms_dev"] = d["rms3d"]; r["rms_along"] = d["rms_along"]; r["rms_cross"] = d["rms_cross"]
        M[c] = {"forced_drop_ratio_param": g["ratio"],
                "runs": [{k: v for k, v in r.items() if k not in ("t", "x")} for r in g["runs"]]}
        M[c]["n_diverged"] = int(sum(r["diverged"] for r in g["runs"]))
        for k in ["total_drop", "forced_frac", "natural_frac", "old_frac", "stale_frac", "ovf_frac", "drift", "drift_xy", "overlap_p90", "overlap_med",
                  "end_to_loop1", "z_absmax", "rms_dev", "rms_to_base_mean"]:
            v = [r[k] for r in g["runs"] if k in r]
            if v:
                M[c][k + "_mean"] = float(np.mean(v)); M[c][k + "_std"] = float(np.std(v))
    # trend tests over all runs
    allr = [r for g in groups.values() for r in g["runs"]]
    x = np.array([r["total_drop"] for r in allr])
    trend = {}
    for k in ["drift", "drift_xy", "overlap_p90", "overlap_med", "end_to_loop1", "z_absmax", "rms_dev", "rms_to_base_mean"]:
        y = np.array([r.get(k, np.nan) for r in allr])
        ok = np.isfinite(y)
        if ok.sum() >= 4:
            rho, p = spearmanr(x[ok], y[ok]); tau, pt = kendalltau(x[ok], y[ok])
            gm = [M[c].get(k + "_mean") for c, _ in CONDS if c in M]
            mono = all(gm[i] is not None and gm[i + 1] is not None and gm[i + 1] > gm[i] for i in range(len(gm) - 1))
            trend[k] = {"spearman_rho": float(rho), "spearman_p": float(p), "kendall_tau": float(tau), "kendall_p": float(pt),
                        "group_means_in_order": gm, "group_means_monotonic_increasing": bool(mono)}
    M["_trend"] = trend

    fig, axs = plt.subplots(1, 4, figsize=(19, 4.3))
    for c, g in groups.items():
        xs = [r["total_drop"] * 100 for r in g["runs"]]
        for ax, k, lab in zip(axs, ["overlap_p90", "end_to_loop1", "rms_dev", "rms_to_base_mean"],
                              ["loop-2 vs loop-1 overlap error p90 [m]", "endpoint to loop-1 path [m]", "RMS dev. from own group mean [m]",
                               "RMS dist. to baseline(both) mean traj. [m]"]):
            ys = [r.get(k, np.nan) for r in g["runs"]]
            ax.scatter(xs, ys, color=COL[c], s=22, label=c, alpha=.8)
            if np.isfinite(ys).any():
                ax.errorbar(np.mean(xs), np.nanmean(ys), xerr=np.std(xs), yerr=np.nanstd(ys), color=COL[c], fmt="D", ms=8, mec="k", capsize=4)
            ax.set_xlabel("actual total drop rate [%] (natural + forced)"); ax.set_title(lab); ax.grid(alpha=.3)
    axs[0].legend()
    fig.suptitle("mainlab, both cameras: artificial drop ablation (diamonds = group mean ± std)")
    fig.tight_layout(); p = out / "ablation.png"; fig.savefig(p, dpi=130); plt.close(fig)

    # drop composition bar
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, (c, _) in enumerate(CONDS):
        if c not in M:
            continue
        b = 0
        for k, col in [("old_frac", "tab:orange"), ("stale_frac", "tab:olive"), ("ovf_frac", "tab:gray"), ("forced_frac", "tab:red")]:
            v = M[c].get(k + "_mean", 0) * 100
            ax.bar(i, v, bottom=b, color=col, label=k.replace("_frac", "") if i == 0 else None); b += v
    ax.set_xticks(range(len(CONDS))); ax.set_xticklabels([c for c, _ in CONDS]); ax.set_ylabel("% of eligible frames")
    ax.set_title("drop composition (mean over runs and cameras)"); ax.legend(); ax.grid(alpha=.3, axis="y")
    fig.tight_layout(); p2 = out / "drop_composition.png"; fig.savefig(p2, dpi=130); plt.close(fig)

    (out / "metrics.json").write_text(json.dumps(M, indent=1))
    L = ["## 자동 생성 표 — drop ablation (mainlab, both)\n",
         "| 조건 | forced 파라미터 | n | 발산 | 실제 총 드롭률 | 자연 드롭(old/stale/ovf) | 인위 드롭 | 겹침 오차 p90 [m] | 겹침 오차 median [m] | 끝점→1회차 [m] | z 최대 이탈 [m] | 5회 편차 RMS [m] | 기준(both) 평균 궤적까지 RMS [m] | (참고) 시작~끝 3D [m] |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda c, k, s=1, n=3: (f"{M[c][k + '_mean'] * s:.{n}f} ± {M[c][k + '_std'] * s:.{n}f}" if k + "_mean" in M[c] else "—")
    for c, _ in CONDS:
        if c in M:
            L.append(f"| {c} | {M[c]['forced_drop_ratio_param']} | {len(M[c]['runs'])} | {M[c]['n_diverged']} | {f(c, 'total_drop', 100, 1)} % | {f(c, 'natural_frac', 100, 1)} % | "
                     f"{f(c, 'forced_frac', 100, 1)} % | {f(c, 'overlap_p90')} | {f(c, 'overlap_med')} | {f(c, 'end_to_loop1')} | {f(c, 'z_absmax')} | {f(c, 'rms_dev')} | {f(c, 'rms_to_base_mean')} | {f(c, 'drift')} |")
    L.append("\n런별 (총 드롭률 %, 겹침 p90 m, 기준 평균까지 RMS m): " + "; ".join(
        f"{r['name']}: ({r['total_drop'] * 100:.1f}, {r.get('overlap_p90', float('nan')):.2f}, {r.get('rms_to_base_mean', float('nan')):.2f})" for g in groups.values() for r in g["runs"]))
    L.append("\n추세 검정 (모든 런, x=실제 총 드롭률):\n")
    for k, v in trend.items():
        L.append(f"- {k}: Spearman ρ={v['spearman_rho']:.2f} (p={v['spearman_p']:.3f}), Kendall τ={v['kendall_tau']:.2f} (p={v['kendall_p']:.3f}); "
                 f"그룹 평균 순서 {[round(x, 3) if x is not None else None for x in v['group_means_in_order']]} → 단조 증가: {v['group_means_monotonic_increasing']}")
    L.append(f"\n그림: `{p}`, `{p2}`")
    (out / "auto_tables.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
