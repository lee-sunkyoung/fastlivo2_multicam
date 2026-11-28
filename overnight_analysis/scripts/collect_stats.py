#!/usr/bin/env python3
"""
Phase 2/4: 런별 img_stats(노드가 종료 시 쓴 csv; 없으면 run.log 파싱본)와 프레임당 처리 시간(timing csv)을
한 표로 모은다. FAST-LIO 런은 제외.
출력: results/<seq>/run_stats.csv  (행 = 런 × 카메라)
사용: python3 scripts/collect_stats.py mainlab
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import RES_DIR, SEQ_DIR, col_f, read_csv

PHYS = {"left": {0: "left"}, "right": {0: "right"}}


def main():
    seq = sys.argv[1]
    out = RES_DIR / seq
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in sorted(SEQ_DIR.glob(f"{seq}_*")):
        if "fastlio" in d.name or "incomplete" in d.name or "test" in d.name or not d.is_dir():
            continue
        cond = d.name[len(seq) + 1:].rsplit("_", 1)[0]
        st = d / f"{d.name}_img_stats.csv"
        src = "node_csv"
        if not st.exists():
            st = d / "img_stats_from_log.csv"; src = "run_log"
        if not st.exists():
            continue
        _, c = read_csv(st)
        tim = {}
        tf = d / f"{d.name}_timing.csv"
        if tf.exists():
            _, tc = read_csv(tf)
            typ = np.array(tc["type"]); pm = col_f(tc, "proc_ms"); stt = col_f(tc, "sensor_time")
            for k in ["LIO", "VIO"]:
                v = pm[typ == k]
                tim[f"{k.lower()}_ms_mean"], tim[f"{k.lower()}_ms_p50"], tim[f"{k.lower()}_ms_p95"], tim[f"{k.lower()}_ms_max"] = \
                    v.mean(), np.percentile(v, 50), np.percentile(v, 95), v.max()
            a2s = col_f(tc, "arrival_to_start_ms")[typ == "VIO"]
            tim["arrival_to_vio_ms_mean"], tim["arrival_to_vio_ms_p95"] = np.nanmean(a2s), np.nanpercentile(a2s, 95)
            cyc = {}
            for t, v in zip(stt, pm):
                cyc[round(t, 6)] = cyc.get(round(t, 6), 0.0) + v
            cv = np.array(list(cyc.values()))
            tim["cycle_ms_mean"], tim["cycle_ms_p95"], tim["n_cycles"] = cv.mean(), np.percentile(cv, 95), len(cv)
        for i in range(len(c["cam"])):
            cam = int(c["cam"][i])
            name = PHYS.get(cond, {0: "left", 1: "right"}).get(cam, f"cam{cam}")
            r = {"run": d.name, "cond": cond, "cam": cam, "camera": name, "stats_src": src}
            for k in ["recv", "used", "skipped_old", "stale", "overflow", "forced", "dup", "loop", "jump", "before_lidar", "cv", "eligible",
                      "total_drop_ratio", "forced_drop_ratio_param"]:
                if k in c:
                    r[k] = c[k][i]
            r.update({k: f"{v:.3f}" if isinstance(v, float) else v for k, v in tim.items()})
            rows.append(r)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(out / "run_stats.csv", "w") as f:
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(k, "")) for k in keys) + "\n")
    print(f"{len(rows)} rows -> {out / 'run_stats.csv'}")


if __name__ == "__main__":
    main()
