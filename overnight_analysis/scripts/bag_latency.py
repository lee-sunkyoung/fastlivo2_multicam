#!/usr/bin/env python3
"""
보조 확인: bag 녹화 시 토픽별 수신 지연 = mcap log_time(녹화 수신 시각) − header.stamp.
both 모드 드롭이 두 bag 모두 재생 ≈140 s부터 급증하는 원인 가설(녹화 시 이미지/LiDAR 지연 변화) 검증용.
bag은 읽기만 한다. 실행 중 배치 런의 타이밍에 영향 주지 않도록 모든 런이 끝난 뒤에 실행.
출력: results/bag_latency/<seq>_latency.png, <seq>_latency.md, cache npz
"""
import struct, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_lib import BAGS, RES_DIR

TOPICS = ["/camera/rgbd_front_left/color/image_raw", "/camera/rgbd_front_right/color/image_raw", "/livox/lidar", "/livox/imu"]


def scan(seq):
    cf = RES_DIR / "cache" / f"{seq}_latency.npz"
    if cf.exists():
        z = np.load(cf); return {tp: (z[f"s{i}"], z[f"l{i}"]) for i, tp in enumerate(TOPICS)}
    import rosbag2_py
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(BAGS[seq])), rosbag2_py.ConverterOptions("", ""))
    r.set_filter(rosbag2_py.StorageFilter(topics=TOPICS))
    d = {tp: ([], []) for tp in TOPICS}
    while r.has_next():
        tp, data, lt = r.read_next()
        sec, nsec = struct.unpack_from("<iI", data, 4)
        d[tp][0].append(sec + nsec * 1e-9); d[tp][1].append(lt * 1e-9)
    out = {tp: (np.array(a), np.array(b)) for tp, (a, b) in d.items()}
    cf.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cf, **{f"s{i}": out[tp][0] for i, tp in enumerate(TOPICS)}, **{f"l{i}": out[tp][1] for i, tp in enumerate(TOPICS)})
    return out


def main():
    out = RES_DIR / "bag_latency"; out.mkdir(parents=True, exist_ok=True)
    for seq in sys.argv[1:] or ["mainlab", "2ndfloor"]:
        D = scan(seq)
        T0 = min(D[tp][1][0] for tp in TOPICS if len(D[tp][1]))
        fig, axs = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
        L = [f"## {seq}: 녹화 수신 지연 (log_time − header.stamp), 20 s 구간 중앙값 [ms] / 메시지 수\n",
             "| 시작 [s] | " + " | ".join(tp.split("/")[-2] if "image" in tp else tp.split("/")[-1] for tp in TOPICS) + " | 이미지−LiDAR 지연차 (left) |",
             "|---|" + "---|" * (len(TOPICS) + 1)]
        for tp in TOPICS:
            s, l = D[tp]
            o = np.argsort(l); s, l = s[o], l[o]
            axs[0].plot(l - T0, (l - s) * 1e3, ".", ms=1, label=tp)
            axs[1].plot(l[1:] - T0, np.diff(l) * 1e3, ".", ms=1, label=tp)
            axs[2].plot(s[1:] - T0, np.diff(s) * 1e3, ".", ms=1, label=tp)
        for s0 in range(0, 300, 20):
            row = []
            med = {}
            for tp in TOPICS:
                s, l = D[tp]; m = (l - T0 >= s0) & (l - T0 < s0 + 20)
                med[tp] = np.median((l[m] - s[m]) * 1e3) if m.any() else np.nan
                row.append(f"{med[tp]:.1f} / {m.sum()}")
            if all(not np.isfinite(v) for v in med.values()):
                continue
            L.append(f"| {s0} | " + " | ".join(row) + f" | {med[TOPICS[0]] - med[TOPICS[2]]:.1f} |")
        axs[0].set_ylabel("log_time − stamp [ms]"); axs[0].set_ylim(-50, 400); axs[0].legend(fontsize=7, markerscale=8)
        axs[1].set_ylabel("Δ log_time [ms]"); axs[1].set_ylim(0, 300)
        axs[2].set_ylabel("Δ header.stamp [ms]"); axs[2].set_ylim(0, 300); axs[2].set_xlabel("bag time [s]")
        for ax in axs: ax.grid(alpha=.3)
        axs[0].set_title(f"{seq}: recording latency and inter-arrival per topic")
        fig.tight_layout(); fig.savefig(out / f"{seq}_latency.png", dpi=110); plt.close(fig)
        (out / f"{seq}_latency.md").write_text("\n".join(L) + "\n")
        print("\n".join(L))


if __name__ == "__main__":
    main()
