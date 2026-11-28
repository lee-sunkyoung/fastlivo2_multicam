#!/usr/bin/env python3
"""
Phase 4 보조: 2ndfloor는 다수 런이 발산하므로 (1) 런별 발산 시작 시각/위치, (2) 발산 전 구간만으로 본 궤적 그림,
(3) 발산 시각 전후 드롭률, (4) 공통 시간창 [0, 최초 발산) 안에서의 5회 산포를 계산한다.
발산 기준: 출발점 대비 |z|>5 m 또는 수평 거리>150 m (analyze_seq와 동일), 혹은 0.1 s 간 이동>3 m(점프).
출력: results/2ndfloor/divergence.md, divergence.json, traj_xy_nondiv.png, z_time.png
"""
import json, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import RES_DIR, bag_image_stamps, col_f, frame_index, load_tum, path_file, read_csv, run_dirs

SEQ = sys.argv[1] if len(sys.argv) > 1 else "2ndfloor"
CONDS = ["both", "left", "right", "fastlio"]
PHYS = {"left": [0], "right": [0], "both": [0, 1]}


def onset(t, x):
    rel = x - x[0]
    bad = (np.abs(rel[:, 2]) > 5) | (np.linalg.norm(rel[:, :2], axis=1) > 150)
    tg = np.arange(t[0], t[-1], 0.1)
    P = np.stack([np.interp(tg, t, x[:, k]) for k in range(3)], 1)
    jump = np.where(np.linalg.norm(np.diff(P, axis=0), axis=1) > 3.0)[0]
    cands = []
    if bad.any():
        cands.append(("bound", t[np.argmax(bad)]))
    if jump.size:
        cands.append(("jump>3m/0.1s", tg[jump[0]]))
    if not cands:
        return None, None
    k, tt = min(cands, key=lambda c: c[1])
    return k, float(tt)


def main():
    out = RES_DIR / SEQ
    stamps = bag_image_stamps(SEQ)
    t_bag0 = min(s[0] for s in stamps)
    res = {}
    L = [f"## {SEQ}: 런별 발산 시점 분석\n",
         "발산 판정: 출발점 대비 |z|>5 m 또는 수평 >150 m, 또는 0.1 s에 3 m 이상 점프 중 가장 이른 시각. 시각은 bag 첫 이미지 기준 [s].\n",
         "| 런 | 발산 | 판정 | 발산 시각 [s] | 발산 위치 (x, y, z) | 드롭률 발산 전 | 드롭률 발산 직전 20 s | 전체 드롭률 | 첫 |z|>1 m [s] | 첫 |z|>2 m [s] |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    fig, axs = plt.subplots(1, 4, figsize=(20, 5.5))
    fz, az = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    for ci, cond in enumerate(CONDS):
        ax = axs[ci]
        for d in run_dirs(SEQ, cond):
            t, x = load_tum(path_file(d))
            kind, to = onset(t, x)
            ts = t - t_bag0
            r = {"diverged": to is not None, "kind": kind, "t_onset": None if to is None else to - t_bag0}
            m = t < (to if to is not None else np.inf)
            pos = x[np.argmin(np.abs(t - to))] if to is not None else None
            r["pos_onset"] = None if pos is None else pos.tolist()
            dr_pre = dr_win = dr_all = np.nan
            if cond != "fastlio":
                _, cols = read_csv(d / f"{d.name}.csv")
                cam = np.array([int(v) for v in cols["cam"]]); ct = col_f(cols, "capture_time")
                pre, win, al = [], [], []
                for k in PHYS[cond]:
                    phys = k if cond == "both" else (0 if cond == "left" else 1)
                    bs = stamps[phys]
                    idx, _ = frame_index(bs, ct[cam == k])
                    used = np.zeros(len(bs), bool); used[idx] = True
                    w = (bs >= t[0]) & (bs <= t[-1])
                    al.append(1 - used[w].mean())
                    if to is not None:
                        pre.append(1 - used[w & (bs < to)].mean())
                        ww = w & (bs < to) & (bs >= to - 20)
                        win.append(1 - used[ww].mean() if ww.any() else np.nan)
                dr_all = np.mean(al)
                if pre:
                    dr_pre, dr_win = np.mean(pre), np.mean(win)
            zr = np.abs(x[:, 2] - x[0, 2])
            for th in (1.0, 2.0):
                r[f"t_z{th:.0f}"] = float(t[np.argmax(zr > th)] - t_bag0) if (zr > th).any() else None
            r.update({"drop_pre": dr_pre, "drop_win20": dr_win, "drop_all": dr_all})
            res[d.name] = r
            f = lambda v: "-" if not np.isfinite(v) else f"{100 * v:.1f}%"
            L.append(f"| {d.name} | {'예' if to is not None else '아니오'} | {kind or '-'} | {'-' if to is None else f'{to - t_bag0:.1f}'} | "
                     f"{'-' if pos is None else '(%.1f, %.1f, %.1f)' % tuple(pos)} | {f(dr_pre)} | {f(dr_win)} | {f(dr_all)} | "
                     f"{'-' if r['t_z1'] is None else f'{r[chr(116)+chr(95)+chr(122)+chr(49)]:.1f}'} | {'-' if r['t_z2'] is None else f'{r[chr(116)+chr(95)+chr(122)+chr(50)]:.1f}'} |")
            ax.plot(x[m, 0], x[m, 1], lw=1, label=f"{d.name.rsplit('_', 1)[1]}" + ("" if to is None else f" (until {to - t_bag0:.0f}s)"))
            if pos is not None:
                ax.plot(*pos[:2], "rx")
            zz = x[:, 2] - x[0, 2]
            az[ci].plot(ts, np.clip(zz, -10, 10), lw=1, label=d.name.rsplit("_", 1)[1])
        ax.plot(0, 0, "go"); ax.set_aspect("equal"); ax.grid(alpha=.3); ax.legend(fontsize=7); ax.set_title(f"{SEQ} {cond}: before divergence (x = onset)")
        az[ci].set_ylabel(f"{cond} z [m] (clip ±10)"); az[ci].grid(alpha=.3); az[ci].legend(fontsize=7, ncol=5)
    az[-1].set_xlabel("time since first bag image [s]")
    fig.tight_layout(); fig.savefig(out / "traj_xy_nondiv.png", dpi=110); plt.close(fig)
    fz.tight_layout(); fz.savefig(out / "z_time.png", dpi=110); plt.close(fz)
    L += ["", f"그림: `{out / 'traj_xy_nondiv.png'}`, `{out / 'z_time.png'}`"]
    (out / "divergence.json").write_text(json.dumps(res, indent=1, default=float))
    (out / "divergence.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
