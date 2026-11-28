#!/usr/bin/env python3
"""
Phase 4: 복도 구간 vs 그 외 구간에서 드롭률·처리시간·런 간 산포 증가 비교 (both 조건).
복도 구간 정의(기하학적): 기준 궤적(5회 중앙값)에서 수평 heading이 거의 일정(±15°)하게 15 m 이상 이어지는 직선 이동 구간.
출력: results/corridor_compare.json, results/corridor_compare.md, results/<seq>/corridor_mask.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import RES_DIR, bag_image_stamps, col_f, common_grid, frame_index, interp_xyz, load_tum, path_file, read_csv, run_dirs

MIN_LEN, MAX_DEV = 15.0, np.radians(15)


def straight_mask(tg, xyz):
    d = np.diff(xyz[:, :2], axis=0)
    step = np.linalg.norm(d, axis=1)
    # heading: ±1 s(±10 샘플) 변위로 평활 (0.1 s 스텝의 잡음 제거)
    k = 10
    a = xyz[np.clip(np.arange(len(d)) + k, 0, len(xyz) - 1), :2] - xyz[np.clip(np.arange(len(d)) - k + 1, 0, len(xyz) - 1), :2]
    hd = np.arctan2(a[:, 1], a[:, 0])
    n = len(step)
    mask = np.zeros(len(tg), bool)
    i = 0
    while i < n:
        if step[i] < 1e-3:
            i += 1; continue
        j, L = i, 0.0
        ref = hd[i]
        cs = [np.cos(hd[i])], [np.sin(hd[i])]
        while j < n:
            if step[j] >= 1e-3:
                a = np.angle(np.exp(1j * (hd[j] - ref)))
                if abs(a) > MAX_DEV:
                    break
                cs[0].append(np.cos(hd[j])); cs[1].append(np.sin(hd[j]))
                ref = np.arctan2(np.mean(cs[1]), np.mean(cs[0]))
            L += step[j]; j += 1
        if L >= MIN_LEN:
            mask[i:j + 1] = True
            i = j
        else:
            i += 1
    return mask


def main():
    out = {}
    L = ["## 복도(긴 직선) 구간 vs 그 외 — both 조건, 5회\n",
         f"복도 정의: 5회 중앙값 궤적에서 heading이 ±15° 이내로 {MIN_LEN:.0f} m 이상 이어지는 직선 구간 (기하학적 정의; LiDAR 퇴화 여부와는 별개 — Phase 7 참고)\n",
         "| 시퀀스 | 복도 시간 비율 | 드롭률 복도 / 그 외 (카메라 평균, 런 평균) | 사이클 ms 복도 / 그 외 | 런 간 산포 증가율 [m/s] 복도 / 그 외 | 드롭률 차 런별 (복도−그 외, %p) |",
         "|---|---|---|---|---|---|"]
    for seq in ["mainlab", "2ndfloor"]:
        ds = run_dirs(seq, "both")
        if len(ds) < 2:
            continue
        divf = RES_DIR / seq / "divergence.json"
        div = json.loads(divf.read_text()) if divf.exists() else {}
        ds_sp = [d for d in ds if not div.get(d.name, {}).get("diverged", False)]  # 산포는 발산 런 제외
        runs = [load_tum(path_file(d)) for d in ds_sp]
        tg = common_grid(runs, 0.1)
        P = np.stack([interp_xyz(t, x, tg) for t, x in runs])
        ref = np.median(P, 0)
        cm = straight_mask(tg, ref)
        spread = np.sqrt(((P - P.mean(0)) ** 2).sum(2).mean(0))
        dsp = np.gradient(spread, tg)
        stamps = bag_image_stamps(seq)
        in_c = lambda tt: cm[np.clip(np.searchsorted(tg, tt), 0, len(tg) - 1)] & (tt >= tg[0]) & (tt <= tg[-1])
        in_w = lambda tt: (tt >= tg[0]) & (tt <= tg[-1])
        dr_c, dr_o, cy_c, cy_o = [], [], [], []
        for d in ds:
            _, cols = read_csv(d / f"{d.name}.csv")
            cam = np.array([int(x) for x in cols["cam"]]); t = col_f(cols, "capture_time")
            rc, ro = [], []
            for k in [0, 1]:
                bs = stamps[k]
                idx, _ = frame_index(bs, t[cam == k])
                used = np.zeros(len(bs), bool); used[idx] = True
                w = in_w(bs); c = in_c(bs)
                rc.append(1 - used[w & c].mean()); ro.append(1 - used[w & ~c].mean())
            dr_c.append(np.mean(rc)); dr_o.append(np.mean(ro))
            _, tc = read_csv(d / f"{d.name}_timing.csv")
            st = col_f(tc, "sensor_time"); pm = col_f(tc, "proc_ms")
            cyc = {}
            for a, b in zip(st, pm):
                cyc[round(a, 6)] = cyc.get(round(a, 6), 0) + b
            ct = np.array(list(cyc)); cv = np.array(list(cyc.values()))
            m = in_w(ct); c = in_c(ct)
            cy_c.append(cv[m & c].mean()); cy_o.append(cv[m & ~c].mean())
        g = {"corridor_time_frac": float(cm.mean()), "drop_corr": dr_c, "drop_other": dr_o, "cycle_corr": cy_c, "cycle_other": cy_o,
             "spread_rate_corr": float(np.mean(dsp[cm])), "spread_rate_other": float(np.mean(dsp[~cm])),
             "spread_gain_in_corr_m": float(np.sum(dsp[cm]) * 0.1), "spread_gain_other_m": float(np.sum(dsp[~cm]) * 0.1),
             "spread_runs": [d.name for d in ds_sp]}
        out[seq] = g
        L.append(f"| {seq} | {g['corridor_time_frac']:.2f} | {100 * np.mean(dr_c):.1f}% / {100 * np.mean(dr_o):.1f}% | {np.mean(cy_c):.1f} / {np.mean(cy_o):.1f} | "
                 f"{g['spread_rate_corr']:.4f} / {g['spread_rate_other']:.4f} | " + ", ".join(f"{100 * (a - b):+.1f}" for a, b in zip(dr_c, dr_o)) + " |")
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.plot(ref[:, 0], ref[:, 1], color="lightgray", lw=3, label="other")
        rr = ref.copy(); rr[~cm] = np.nan
        ax.plot(rr[:, 0], rr[:, 1], color="tab:red", lw=2, label=f"corridor (straight ≥{MIN_LEN:.0f} m)")
        ax.set_aspect("equal"); ax.grid(alpha=.3); ax.legend(); ax.set_title(f"{seq}: corridor mask on median both trajectory")
        p = RES_DIR / seq / "corridor_mask.png"; p.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout(); fig.savefig(p, dpi=120); plt.close(fig)
        L.append("")
        L.append(f"- {seq}: 산포 증가 총량 복도 {g['spread_gain_in_corr_m']:.2f} m / 그 외 {g['spread_gain_other_m']:.2f} m (산포·복도 마스크는 비발산 런 {len(ds_sp)}개로 계산; 드롭률은 {len(ds)}개 모두), 그림 `{p}`")
        L.append("")
    (RES_DIR / "corridor_compare.json").write_text(json.dumps(out, indent=1))
    (RES_DIR / "corridor_compare.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
