#!/usr/bin/env python3
"""
Phase 7: T1(LIO HᵀR⁻¹H 고유값) + T2(카메라별 VIO 정보의 LIO 최소 병진 고유벡터 투영) 분석.
입력: sequences/<seq>_both_diag_N/<name>_lio_eig.csv, _vis_info.csv, path
출력: results/degeneracy/<seq>_*.png, metrics.json, auto_tables.md

정의
- 최소 병진 고유값 λt = eig_min(H_tt) (H의 병진 3×3 블록; 단위 1/m², 정보량)
- LIVO는 이미지마다 스캔을 잘라 LIO 업데이트를 하므로 업데이트당 점 수(n_eff)가 수백~수천으로 들쭉날쭉하고 λt가 그에 비례(log 상관 0.72).
  → 점당 정보 λt/n_eff를 1 s 구간 중앙값으로 평활한 값(λt_pp)을 퇴화 판단에 쓴다 (점 수와 무관, 시퀀스 간 비교 가능).
- 퇴화 구간: λt_pp < DEG_FRAC × median(λt_pp of that run) 인 1 s 구간 (상대 기준). 시퀀스 간 비교는 λt_pp 절대값과 cond_t로.
- 복도 축 = 궤적의 국소 수평 진행 방향(±1 s 위치 차). 각도 = acos(|v_t · tangent|) (고유벡터 부호 무의미)
- 보완량 = v_tᵀ H_vis,tt v_t (그 카메라 업데이트의 정보행렬 HᵀR⁻¹H, R = img_point_cov·I, 같은 시점 LIO v_t에 투영)
  LIO λt와 같은 단위(1/m²)라 비율 = 보완량 / λt 로 "카메라가 약한 방향 정보를 몇 배 더하나"를 본다.
  업데이트 단위 비율은 잘린 스캔 크기에 따라 흔들리므로 1 s 구간 합 비율 Σ(cam 보완량)/Σ(LIO λt)를 주 지표로 쓴다
  (같은 구간 안에서 v_t가 거의 일정하다는 근사).
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import RES_DIR, col_f, load_tum, path_file, read_csv, run_dirs

DEG_FRAC = 0.5
BIN = 1.0


def segments(mask):
    segs, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            segs.append((start, i - 1)); start = None
    if start is not None:
        segs.append((start, len(mask) - 1))
    return segs


def tangent_at(tp, xyz, tq, half=1.0):
    a = np.stack([np.interp(tq - half, tp, xyz[:, k]) for k in range(3)], 1)
    b = np.stack([np.interp(tq + half, tp, xyz[:, k]) for k in range(3)], 1)
    v = b - a; v[:, 2] = 0
    n = np.linalg.norm(v, axis=1, keepdims=True)
    speed = n[:, 0] / (2 * half)
    with np.errstate(invalid="ignore", divide="ignore"):
        return v / n, speed


def analyze_run(d):
    _, E = read_csv(d / f"{d.name}_lio_eig.csv")
    _, V = read_csv(d / f"{d.name}_vis_info.csv")
    t = col_f(E, "t"); pos = np.stack([col_f(E, k) for k in ["px", "py", "pz"]], 1)
    et0 = col_f(E, "et0"); vt = np.stack([col_f(E, k) for k in ["vt0", "vt1", "vt2"]], 1)
    e6 = col_f(E, "e0"); sch = col_f(E, "schur_t_min"); vs = np.stack([col_f(E, k) for k in ["vs0", "vs1", "vs2"]], 1)
    tp, xyz = load_tum(path_file(d))
    tan, speed = tangent_at(tp, xyz, t)
    moving = speed > 0.1
    ang = np.degrees(np.arccos(np.clip(np.abs((vt * tan).sum(1)), 0, 1)))
    ang_s = np.degrees(np.arccos(np.clip(np.abs((vs * tan).sum(1)), 0, 1)))
    vert = np.abs(vt[:, 2])
    n_eff = col_f(E, "n_eff")
    pp = et0 / np.maximum(n_eff, 1)
    b = np.floor((t - t[0]) / BIN).astype(int); nb = b.max() + 1
    pp_bin = np.array([np.median(pp[b == i]) if (b == i).any() else np.nan for i in range(nb)])
    ct = col_f(E, "cond_t")
    ct_bin = np.array([np.median(ct[b == i]) if (b == i).any() else np.nan for i in range(nb)])
    med = np.nanmedian(pp_bin)
    deg_bin = pp_bin < DEG_FRAC * med
    deg = deg_bin[b]
    vt_t = col_f(V, "t"); cam = col_f(V, "cam").astype(int)
    # n_points==0 행은 무효: 첫 diag 빌드(d29d524)는 vio.cpp에서 total_points==0 조기 return이 per-frame 리셋보다 앞서 이전 프레임 값을 다시 기록함
    valid = (col_f(V, "valid") > 0) & (col_f(V, "n_points") > 0)
    proj = col_f(V, "proj_vis_on_lio_vt"); lmin = col_f(V, "lio_min_trans_eig")
    ratio = proj / lmin
    # map each VIO row to degenerate flag of the LIO update with same timestamp
    idx = np.clip(np.searchsorted(t, vt_t - 1e-7), 0, len(t) - 1)
    vdeg = deg[idx] & (np.abs(t[idx] - vt_t) < 1e-4)
    vb = np.floor((vt_t - t[0]) / BIN).astype(int)
    sum_et = np.array([et0[b == i].sum() for i in range(nb)])
    cam_ratio_bin = {}
    for c in [0, 1]:
        sp = np.array([proj[(vb == i) & (cam == c) & valid].sum() for i in range(nb)])
        cam_ratio_bin[c] = sp / np.where(sum_et > 0, sum_et, np.nan)
    R = {"name": d.name, "n_lio": int(len(t)), "pp_median": float(med), "pp_p05": float(np.nanpercentile(pp_bin, 5)),
         "cond_t_median": float(np.nanmedian(ct_bin)), "cond_t_p95": float(np.nanpercentile(ct_bin, 95)),
         "deg_frac_time": float(np.nanmean(deg_bin)), "n_deg_segments": len(segments(deg_bin)), "deg_threshold": float(DEG_FRAC * med)}
    npts = col_f(V, "n_points")
    vdeg_bin = deg_bin[np.clip(vb, 0, nb - 1)]
    R["zero_pts_frac_deg"] = float(np.mean(npts[vdeg_bin] == 0)) if vdeg_bin.any() else None
    R["zero_pts_frac_nondeg"] = float(np.mean(npts[~vdeg_bin] == 0))
    for c in [0, 1]:
        r_ = cam_ratio_bin[c]
        R[f"cam{c}_binratio_median_deg"] = float(np.nanmedian(r_[deg_bin])) if deg_bin.any() else None
        R[f"cam{c}_binratio_median_nondeg"] = float(np.nanmedian(r_[~deg_bin]))
    for lab, m in [("deg", deg & moving), ("nondeg", ~deg & moving)]:
        R[f"angle_vt_to_axis_median_{lab}"] = float(np.nanmedian(ang[m])) if m.any() else None
        R[f"angle_schur_to_axis_median_{lab}"] = float(np.nanmedian(ang_s[m])) if m.any() else None
        R[f"vt_vertical_abs_median_{lab}"] = float(np.median(vert[m])) if m.any() else None
        R[f"frac_vt_within30deg_axis_{lab}"] = float(np.mean(ang[m] < 30)) if m.any() else None
    for c in [0, 1]:
        for lab, m in [("deg", vdeg), ("nondeg", ~vdeg)]:
            mm = m & (cam == c) & valid
            R[f"cam{c}_ratio_median_{lab}"] = float(np.median(ratio[mm])) if mm.any() else None
            R[f"cam{c}_proj_median_{lab}"] = float(np.median(proj[mm])) if mm.any() else None
            R[f"cam{c}_n_{lab}"] = int(mm.sum())
    # alternation: within each degenerate segment, which camera gives more (median ratio), and per-segment winner
    seg_rows = []
    for a, e in segments(deg_bin):
        t0, t1 = t[0] + a * BIN, t[0] + (e + 1) * BIN
        m = slice(a, e + 1)
        r0 = cam_ratio_bin[0][m]; r1 = cam_ratio_bin[1][m]
        seg_rows.append({"t0": float(t0 - t[0]), "t1": float(t1 - t[0]), "dur": float(t1 - t0),
                         "pos": pos[np.argmin(np.abs(t - (t0 + t1) / 2))].tolist(),
                         "cam0_med_ratio": float(np.nanmedian(r0)) if np.isfinite(r0).any() else None,
                         "cam1_med_ratio": float(np.nanmedian(r1)) if np.isfinite(r1).any() else None})
    R["segments"] = seg_rows
    good = [s for s in seg_rows if s["cam0_med_ratio"] is not None and s["cam1_med_ratio"] is not None]
    R["segments_ge0.5s"] = len(good)
    R["segments_cam0_wins"] = int(sum(s["cam0_med_ratio"] > s["cam1_med_ratio"] for s in good))
    R["segments_both_ratio_lt_0.1"] = int(sum(max(s["cam0_med_ratio"], s["cam1_med_ratio"]) < 0.1 for s in good))
    R["segments_both_ratio_gt_1"] = int(sum(min(s["cam0_med_ratio"], s["cam1_med_ratio"]) > 1 for s in good))
    arr = dict(pp_bin=pp_bin, ct_bin=ct_bin, deg_bin=deg_bin, cam_ratio_bin=cam_ratio_bin, tb=t[0] + (np.arange(nb) + 0.5) * BIN, t=t, pos=pos, et0=et0, e6=e6, sch=sch, ang=ang, deg=deg, moving=moving, vt_t=vt_t, cam=cam, ratio=ratio, proj=proj,
               valid=valid, xyz=xyz)
    return R, arr


def shade(ax, A, T0):
    for s_, e_ in segments(A["deg_bin"]):
        ax.axvspan(A["t"][0] + s_ * BIN - T0, A["t"][0] + (e_ + 1) * BIN - T0, color="red", alpha=.12, lw=0)


def plots(seq, runs, out):
    figs = []
    R0, A = runs[0]
    T0 = A["t"][0]
    # 1) per-point λt and cond_t over time, all runs
    fig, axs = plt.subplots(2, 1, figsize=(13, 6.5), sharex=True)
    for R, a in runs:
        axs[0].semilogy(a["tb"] - T0, a["pp_bin"], lw=.8, label=R["name"].split("_")[-1])
        axs[1].semilogy(a["tb"] - T0, a["ct_bin"], lw=.8)
    for ax in axs:
        shade(ax, A, T0); ax.grid(alpha=.3)
    axs[0].set_ylabel("λ_min(H_tt)/n_eff, 1 s median"); axs[0].legend(fontsize=7, ncol=5)
    axs[1].set_ylabel("cond(H_tt), 1 s median"); axs[1].set_xlabel("time since first LIO update [s]")
    axs[0].set_title(f"{seq}: LIO weakest translational information per point (shade = degenerate in run {R0['name'].split('_')[-1]})")
    fig.tight_layout(); p = out / f"{seq}_lambda_t_time.png"; fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    # 2) trajectory colored by per-point λt
    fig, ax = plt.subplots(figsize=(8, 7))
    b = np.floor((A["t"] - A["t"][0]) / BIN).astype(int)
    cval = np.log10(np.clip(A["pp_bin"][b], 1e-3, None))
    sc = ax.scatter(A["pos"][:, 0], A["pos"][:, 1], c=cval, s=3, cmap="viridis")
    dg = A["deg"]
    ax.scatter(A["pos"][dg, 0], A["pos"][dg, 1], s=10, facecolors="none", edgecolors="r", lw=.5, label=f"degenerate (<{DEG_FRAC}×median)")
    plt.colorbar(sc, label="log10 λ_min(H_tt)/n_eff (1 s median)"); ax.set_aspect("equal"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title(f"{R0['name']}: trajectory colored by LIO weakest-direction info")
    fig.tight_layout(); p = out / f"{seq}_traj_lambda_t.png"; fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    # 3) angle to corridor axis
    fig, axs = plt.subplots(1, 2, figsize=(14, 3.8), gridspec_kw={"width_ratios": [3, 1]})
    m = A["moving"]
    axs[0].plot(A["t"][m] - T0, A["ang"][m], ".", ms=1.5, color="gray", label="all")
    axs[0].plot(A["t"][m & dg] - T0, A["ang"][m & dg], ".", ms=3, color="r", label="degenerate")
    axs[0].set_ylabel("angle(v_t, travel dir) [deg]"); axs[0].set_xlabel("time [s]"); axs[0].legend(fontsize=8); axs[0].grid(alpha=.3)
    axs[0].set_title(f"{R0['name']}: angle between min-eigvec of H_tt and travel direction (0° = along corridor)")
    allang_d = np.concatenate([a["ang"][a["moving"] & a["deg"]] for _, a in runs])
    allang_n = np.concatenate([a["ang"][a["moving"] & ~a["deg"]] for _, a in runs])
    axs[1].hist([allang_n, allang_d], bins=np.arange(0, 91, 5), density=True, label=["non-degenerate", "degenerate"], color=["gray", "r"])
    axs[1].set_xlabel("angle [deg]"); axs[1].legend(fontsize=8); axs[1].set_title("all runs")
    fig.tight_layout(); p = out / f"{seq}_angle_axis.png"; fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    # 4) cam0/cam1 complement over time (1 s window sums)
    fig, axs = plt.subplots(2, 1, figsize=(13, 6.5), sharex=True)
    for c, col in [(0, "tab:orange"), (1, "tab:green")]:
        axs[0].semilogy(A["tb"] - T0, A["cam_ratio_bin"][c], lw=.8, color=col, label=f"cam{c} ({'left' if c == 0 else 'right'})")
        allr = np.concatenate([a["cam_ratio_bin"][c] for _, a in runs])
    axs[0].axhline(1, color="k", lw=.5, ls="--")
    axs[0].set_ylabel("Σ cam info on v_t / Σ LIO λ_min (1 s)"); axs[0].legend(fontsize=8)
    axs[0].set_title(f"{R0['name']}: camera information along LIO weakest translation (shade = degenerate)")
    axs[1].semilogy(A["tb"] - T0, A["pp_bin"], "k-", lw=.8); axs[1].set_ylabel("LIO λ_min/n_eff"); axs[1].set_xlabel("time [s]")
    for ax in axs:
        shade(ax, A, T0); ax.grid(alpha=.3)
    fig.tight_layout(); p = out / f"{seq}_cam_complement.png"; fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def main():
    out = RES_DIR / "degeneracy"
    out.mkdir(parents=True, exist_ok=True)
    allM, L = {}, ["## 자동 생성 표 — degeneracy (T1/T2)\n",
                   f"퇴화 정의: 1 s 구간 중앙값 λt/n_eff < {DEG_FRAC} × (그 런의 중앙값). 각도/수직성분은 이동 중(속도>0.1 m/s) 샘플만. 카메라 비율 = 1 s 구간 Σ(v_tᵀH_vis v_t)/Σ(LIO λt).\n"]
    for seq in ["mainlab", "2ndfloor"]:
        ds = [d for d in run_dirs(seq, "both_diag") if (d / f"{d.name}_lio_eig.csv").exists()]
        if not ds:
            continue
        runs = [analyze_run(d) for d in ds]
        figs = plots(seq, runs, out)
        allM[seq] = [r for r, _ in runs]
        L.append(f"### {seq} (n={len(runs)})\n")
        L.append("| 런 | λt/n 중앙값 | λt/n p5 | cond_t 중앙값/p95 | 퇴화 시간비율 | 퇴화 구간 수 | 각도 중앙값 퇴화/비퇴화 [°] | v_t 30° 이내 비율 퇴화/비퇴화 | |v_t,z| 중앙값 퇴화/비퇴화 | cam0 1 s 비율 중앙값 퇴화/비퇴화 | cam1 1 s 비율 중앙값 퇴화/비퇴화 | 구간 cam0 우세/전체 | 둘 다 <0.1 | 둘 다 >1 | 시각점 0개 VIO 비율 퇴화/비퇴화 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        f = lambda x, n=2: "—" if x is None else f"{x:.{n}f}"
        for R, _ in runs:
            L.append(f"| {R['name']} | {R['pp_median']:.1f} | {R['pp_p05']:.1f} | {R['cond_t_median']:.1f}/{R['cond_t_p95']:.1f} | {R['deg_frac_time']:.3f} | {R['n_deg_segments']} | "
                     f"{f(R['angle_vt_to_axis_median_deg'], 1)} / {f(R['angle_vt_to_axis_median_nondeg'], 1)} | "
                     f"{f(R['frac_vt_within30deg_axis_deg'])} / {f(R['frac_vt_within30deg_axis_nondeg'])} | "
                     f"{f(R['vt_vertical_abs_median_deg'])} / {f(R['vt_vertical_abs_median_nondeg'])} | "
                     f"{f(R['cam0_binratio_median_deg'], 3)} / {f(R['cam0_binratio_median_nondeg'], 3)} | {f(R['cam1_binratio_median_deg'], 3)} / {f(R['cam1_binratio_median_nondeg'], 3)} | "
                     f"{R['segments_cam0_wins']}/{R['segments_ge0.5s']} | {R['segments_both_ratio_lt_0.1']} | {R['segments_both_ratio_gt_1']} | {f(R['zero_pts_frac_deg'])} / {f(R['zero_pts_frac_nondeg'])} |")
        L.append("")
        L.append("퇴화 구간 (첫 런, 시작~끝 s, 위치, cam0/cam1 1 s 비율 중앙값): " + "; ".join(
            f"{g['t0']:.0f}~{g['t1']:.0f} s ({g['pos'][0]:.1f}, {g['pos'][1]:.1f}) {f(g['cam0_med_ratio'], 3)}/{f(g['cam1_med_ratio'], 3)}" for g in runs[0][0]["segments"]))
        L.append("\n그림: " + ", ".join(f"`{p}`" for p in figs) + "\n")
    (out / "metrics.json").write_text(json.dumps(allM, indent=1))
    (out / "auto_tables.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
