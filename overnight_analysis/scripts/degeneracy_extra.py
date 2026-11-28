#!/usr/bin/env python3
"""
Phase 6/7 보조:
 (a) 로깅 on(diag) vs off(both) 비교: 드롭률, 처리 시간, 루프 지표 — '켜도 추정 결과가 바뀌면 안 된다' 확인
 (b) 복도(직선 ≥15 m, corridor_compare와 같은 정의, 그 런 자신의 궤적 기준) vs 그 외에서 LIO λt/n, cond_t, 각도
 (c) 시간 창별 요약 (mainlab 갈라짐 창 55~66 s, 150~160 s 포함)
출력: results/degeneracy/extra.md
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import RES_DIR, col_f, horizontal_axes, load_tum, loop_metrics, path_file, read_csv, run_dirs
from corridor_compare import straight_mask

L = ["## Phase 6/7 보조 분석\n"]
# (a)
L += ["### (a) 로깅 on/off 비교 (both vs both_diag, 각 5회)\n",
      "| 시퀀스 | 조건 | 총 드롭률 (카메라·런 평균) | LIO ms 평균 | 사이클 ms 평균 | 겹침 p90 [m] (런별) | z 최대 이탈 [m] (런별) |", "|---|---|---|---|---|---|---|"]
for seq in ["mainlab", "2ndfloor"]:
    for cond in ["both", "both_diag"]:
        dr, lio, cyc, ov, zm = [], [], [], [], []
        for d in run_dirs(seq, cond):
            _, c = read_csv(d / f"{d.name}_img_stats.csv"); dr.append(np.mean([float(x) for x in c["total_drop_ratio"]]))
            _, tc = read_csv(d / f"{d.name}_timing.csv"); ty = np.array(tc["type"]); pm = col_f(tc, "proc_ms"); st = col_f(tc, "sensor_time")
            lio.append(pm[ty == "LIO"].mean())
            cy = {}
            for a, b in zip(st, pm): cy[round(a, 6)] = cy.get(round(a, 6), 0) + b
            cyc.append(np.mean(list(cy.values())))
            t, x = load_tum(path_file(d)); lm = loop_metrics(t, x, horizontal_axes(x)) or {}
            ov.append(lm.get("overlap_p90", np.nan)); zm.append(np.abs(x[:, 2] - x[0, 2]).max())
        L.append(f"| {seq} | {cond} | {100 * np.mean(dr):.1f}% ({', '.join(f'{100 * v:.1f}' for v in dr)}) | {np.mean(lio):.2f} | {np.mean(cyc):.2f} | "
                 f"{', '.join('nan' if not np.isfinite(v) else f'{v:.2f}' for v in ov)} | {', '.join(f'{v:.1f}' for v in zm)} |")
# (b)
L += ["", "### (b) 복도(직선 ≥15 m) vs 그 외 — LIO 정보량 (각 런 자신의 궤적으로 복도 판정, 5회 중앙값)\n",
      "| 시퀀스 | 복도 시간비율 | λt/n 중앙값 복도/그 외 | cond_t 중앙값 복도/그 외 | 퇴화(<0.5×중앙값, 1 s) 비율 복도/그 외 | 최소 병진 고유벡터–진행방향 각도 중앙값 복도/그 외 [°] | |v_t,z| 중앙값 복도/그 외 |",
      "|---|---|---|---|---|---|---|"]
for seq in ["mainlab", "2ndfloor"]:
    rows = []
    for d in run_dirs(seq, "both_diag"):
        if d.name == "2ndfloor_both_diag_5":
            continue  # 발산 런(140 s 이후 H 붕괴) 제외
        _, E = read_csv(d / f"{d.name}_lio_eig.csv")
        t = col_f(E, "t"); n = np.maximum(col_f(E, "n_eff"), 1); pp = col_f(E, "et0") / n; ct = col_f(E, "cond_t")
        vt = np.stack([col_f(E, k) for k in ["vt0", "vt1", "vt2"]], 1)
        tp, xyz = load_tum(path_file(d))
        tg = np.arange(tp[0], tp[-1], 0.1); P = np.stack([np.interp(tg, tp, xyz[:, k]) for k in range(3)], 1)
        cm = straight_mask(tg, P)
        inC = cm[np.clip(np.searchsorted(tg, t), 0, len(tg) - 1)]
        k = 10
        a = P[np.clip(np.searchsorted(tg, t) + k, 0, len(tg) - 1)] - P[np.clip(np.searchsorted(tg, t) - k, 0, len(tg) - 1)]; a[:, 2] = 0
        sp = np.linalg.norm(a, axis=1); tan = a / np.maximum(sp, 1e-9)[:, None]; mv = sp > 0.2
        ang = np.degrees(np.arccos(np.clip(np.abs((vt * tan).sum(1)), 0, 1)))
        b = np.floor((t - t[0])).astype(int); ppb = np.array([np.median(pp[b == i]) if (b == i).any() else np.nan for i in range(b.max() + 1)])
        deg = (ppb < 0.5 * np.nanmedian(ppb))[b]
        rows.append([inC.mean(), np.median(pp[inC]), np.median(pp[~inC]), np.median(ct[inC]), np.median(ct[~inC]), deg[inC].mean(), deg[~inC].mean(),
                     np.median(ang[inC & mv]), np.median(ang[~inC & mv]), np.median(np.abs(vt[inC, 2])), np.median(np.abs(vt[~inC, 2]))])
    r = np.median(np.array(rows), 0)
    L.append(f"| {seq} (n={len(rows)}) | {r[0]:.2f} | {r[1]:.1f} / {r[2]:.1f} | {r[3]:.1f} / {r[4]:.1f} | {r[5]:.2f} / {r[6]:.2f} | {r[7]:.1f} / {r[8]:.1f} | {r[9]:.2f} / {r[10]:.2f} |")
(RES_DIR / "degeneracy" / "extra.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
