#!/usr/bin/env python3
"""공용 분석 함수 (numpy/csv만 사용). sequences/<seq_name>/ 아래 런 결과를 읽는다."""
import csv
import glob
import json
import os
import re
import struct
from pathlib import Path

import numpy as np

WS = Path.home() / "dlr_ws"
SEQ_DIR = WS / "sequences"
RES_DIR = WS / "results"
BAGS = {
    "mainlab": Path.home() / "dlr_ros2_bag" / "ros2_bag_livo_2_cams_main_lab_2_loops",
    "2ndfloor": Path.home() / "dlr_ros2_bag" / "ros2_bag_livo_2_cams_2nd_floor",
}
IMG_TOPICS = ["/camera/rgbd_front_left/color/image_raw", "/camera/rgbd_front_right/color/image_raw"]


# ------------------------------------------------------------------ discovery
def run_dirs(seq, cond):
    """완료된 런 폴더 목록 (_incomplete, test 제외), 회차 순."""
    out = []
    for d in glob.glob(str(SEQ_DIR / f"{seq}_{cond}_*")):
        name = os.path.basename(d)
        m = re.fullmatch(rf"{re.escape(seq)}_{re.escape(cond)}_(\d+)", name)
        if not m:
            continue
        info = Path(d) / "run_info.json"
        if not info.exists() or json.loads(info.read_text()).get("status") != "complete":
            continue  # 진행 중이거나 불완전한 런 제외
        out.append((int(m.group(1)), Path(d)))
    return [p for _, p in sorted(out)]


# ------------------------------------------------------------------ io
def load_tum(path):
    d = np.loadtxt(path, comments="#")
    d = d[np.argsort(d[:, 0])]
    _, idx = np.unique(d[:, 0], return_index=True)
    d = d[idx]
    return d[:, 0], d[:, 1:4]


def path_file(run_dir: Path):
    return run_dir / f"{run_dir.name}.txt"


def read_csv(path):
    with open(path, newline="") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].startswith("#")]
    if not rows:
        return [], {}
    hdr = rows[0]
    cols = {h: [] for h in hdr}
    for r in rows[1:]:
        for h, v in zip(hdr, r):
            cols[h].append(v)
    return hdr, cols


def col_f(cols, key):
    return np.array([float(x) if x not in ("", "inf", "nan") else (np.inf if x == "inf" else np.nan) for x in cols[key]])


# ------------------------------------------------------------------ trajectory metrics
def common_grid(runs, dt=0.1):
    t0 = max(t[0] for t, _ in runs)
    t1 = min(t[-1] for t, _ in runs)
    return np.arange(t0, t1, dt)


def interp_xyz(t, xyz, tg):
    return np.stack([np.interp(tg, t, xyz[:, k]) for k in range(3)], axis=1)


def horizontal_axes(xyz):
    """복도(건물) 축: 이동 방향(수평 heading)의 지배 방향을 90° 주기로 구함(직교 복도 가정).
    두 직교 방향 중 총 이동 거리가 더 긴 쪽을 'along'(주 복도 축), 다른 쪽을 'cross'로 반환."""
    d = np.diff(xyz[:, :2], axis=0)
    w = np.linalg.norm(d, axis=1)
    ok = w > 1e-3
    th = np.arctan2(d[ok, 1], d[ok, 0]); w = w[ok]
    th0 = np.angle((w * np.exp(4j * th)).sum()) / 4.0
    a = np.array([np.cos(th0), np.sin(th0), 0.0]); b = np.array([-np.sin(th0), np.cos(th0), 0.0])
    la = (w * np.abs(np.cos(th - th0))).sum(); lb = (w * np.abs(np.sin(th - th0))).sum()
    return (a, b) if la >= lb else (b, -a)


def endpoint_drift(t, xyz, axes=None, tail_s=1.0, head_s=1.0):
    """루프의 시작~끝 위치 차이. 시작/끝 각각 처음/마지막 1 s 평균으로 노이즈 완화.
    (출발 위치로 되돌아오는 루프라는 가정. 시작점 = 원점 근처)"""
    p0 = xyz[t <= t[0] + head_s].mean(0)
    p1 = xyz[t >= t[-1] - tail_s].mean(0)
    d = p1 - p0
    out = {"drift": float(np.linalg.norm(d)), "drift_xy": float(np.linalg.norm(d[:2])), "dz": float(d[2]), "vec": d}
    if axes is not None:
        a, b = axes
        out["along"] = float(d @ a)
        out["cross"] = float(d @ b)
    return out


def loop_metrics(t, xyz, axes, leave_m=5.0):
    """bag이 출발점에서 끝나지 않으므로(2회차 도중 종료) 시간에 의존하지 않는 자기 일관성 지표.
    - 1회차/2회차 분할: 출발점에서 leave_m 이상 멀어진 뒤 다시 출발점에 가장 가까워지는 시점(그 런 자신의 추정 기준; 분할용으로만 사용)
    - revisit: 그 최근접 거리(드리프트의 하한)
    - overlap: 2회차 각 점에서 1회차 경로까지 최근접 수평 거리 (median, p90) — 같은 길을 다시 달린다는 가정
    - end_to_loop1: 마지막 위치에서 1회차 경로까지 최근접 수평 거리 (끝 위치는 1회차에 지나간 복도 위)
    - extent_diff_along/cross: 1회차와 2회차의 PCA 축 방향 범위(max-min) 차이 (복도 축 방향 길이 축소/늘어남)"""
    xy = xyz[:, :2]
    r = np.linalg.norm(xy - xy[0], axis=1)
    far = np.where(r > leave_m)[0]
    if far.size == 0:
        return None
    # 가장 멀리 간 지점 이후 처음으로 출발점에 가장 가까워지는 국소 최소
    i_far = far[0]
    after = np.arange(len(r)) > np.argmax(r[: int(len(r) * 0.75)])
    cand = np.where(after & (np.arange(len(r)) > i_far))[0]
    if cand.size == 0:
        return None
    # 출발점 2*leave_m 이내로 들어온 첫 구간에서의 최소
    near = cand[r[cand] < 2 * leave_m]
    if near.size == 0:
        return {"revisit": None}
    seg_end = near[0]
    while seg_end + 1 < len(r) and r[seg_end + 1] < 2 * leave_m:
        seg_end += 1
    seg = np.arange(near[0], seg_end + 1)
    k = seg[np.argmin(r[seg])]
    L1, L2 = xy[: k + 1], xy[k:]
    def nn(P, Q):
        d = np.sqrt(((P[:, None, :] - Q[None, ::2, :]) ** 2).sum(-1)).min(1)
        return d
    d2 = nn(L2[::2], L1)
    a, b = axes
    ext = lambda P, v: float((P @ v[:2]).max() - (P @ v[:2]).min())
    return {"t_split": float(t[k] - t[0]), "revisit": float(r[k]), "overlap_med": float(np.median(d2)), "overlap_p90": float(np.percentile(d2, 90)),
            "end_to_loop1": float(nn(xy[-1:], L1)[0]),
            "extent_along_l1": ext(L1, a), "extent_along_l2": ext(L2, a), "extent_cross_l1": ext(L1, b), "extent_cross_l2": ext(L2, b),
            "frac_loop2": float((t[-1] - t[k]) / (t[-1] - t[0])),
            "z_rms": float(np.sqrt(((xyz[:, 2] - xyz[0, 2]) ** 2).mean())), "z_absmax": float(np.abs(xyz[:, 2] - xyz[0, 2]).max())}


def tangent_frames(mean_xyz, win=10):
    """평균 궤적의 수평 진행 방향(along-track) 단위벡터와 수평 수직(cross-track) 단위벡터."""
    n = len(mean_xyz)
    tan = np.zeros((n, 3))
    for i in range(n):
        a, b = max(0, i - win), min(n - 1, i + win)
        v = mean_xyz[b] - mean_xyz[a]
        v[2] = 0.0
        nv = np.linalg.norm(v)
        tan[i] = v / nv if nv > 1e-6 else np.nan
    # 정지 구간(NaN)은 가장 가까운 유효값으로 채움
    valid = ~np.isnan(tan[:, 0])
    if valid.any():
        idx = np.where(valid)[0]
        for i in np.where(~valid)[0]:
            tan[i] = tan[idx[np.argmin(np.abs(idx - i))]]
    cross = np.stack([-tan[:, 1], tan[:, 0], np.zeros(n)], axis=1)
    return tan, cross


def group_deviation(runs, dt=0.1):
    """runs: [(t, xyz)]. 공통 시간 격자에서 평균 궤적 대비 run별 RMS (3D, along, cross, z)."""
    tg = common_grid(runs, dt)
    P = np.stack([interp_xyz(t, x, tg) for t, x in runs])  # (R, N, 3)
    mean = P.mean(0)
    tan, crs = tangent_frames(mean)
    dev = P - mean[None]
    res = []
    for r in range(len(runs)):
        e = dev[r]
        res.append({
            "rms3d": float(np.sqrt((e ** 2).sum(1).mean())),
            "rms_along": float(np.sqrt(((e * tan).sum(1) ** 2).mean())),
            "rms_cross": float(np.sqrt(((e * crs).sum(1) ** 2).mean())),
            "rms_z": float(np.sqrt((e[:, 2] ** 2).mean())),
        })
    spread_t = np.sqrt((dev ** 2).sum(2).mean(0))  # 시간별 run 간 산포 (RMS over runs)
    return tg, P, mean, res, spread_t


# ------------------------------------------------------------------ bag image timestamps
def bag_image_stamps(seq, cache=True):
    """bag 안 각 카메라 이미지의 header.stamp(s). CDR 헤더의 앞 8바이트만 파싱(이미지 역직렬화 없음). 결과는 캐시."""
    cache_f = RES_DIR / "cache" / f"{seq}_image_stamps.npz"
    if cache and cache_f.exists():
        z = np.load(cache_f)
        return [z["cam0"], z["cam1"]]
    import rosbag2_py
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(BAGS[seq])), rosbag2_py.ConverterOptions("", ""))
    reader.set_filter(rosbag2_py.StorageFilter(topics=IMG_TOPICS))
    st = {tp: [] for tp in IMG_TOPICS}
    while reader.has_next():
        tp, data, _ = reader.read_next()
        sec, nsec = struct.unpack_from("<iI", data, 4)  # 4-byte CDR encapsulation header, then Header.stamp
        st[tp].append(sec + nsec * 1e-9)
    out = [np.array(sorted(st[tp])) for tp in IMG_TOPICS]
    cache_f.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_f, cam0=out[0], cam1=out[1])
    return out


def ts_key(t):
    """타임스탬프를 정수 µs 키로 (csv 6자리 반올림과 맞춤)."""
    return np.round(np.asarray(t) * 1e6).astype(np.int64)


def frame_index(bag_stamps, t, tol=0.002):
    """선택/드롭 csv의 타임스탬프를 bag 프레임 인덱스로 (가장 가까운 프레임, |차이|<tol). csv는 소수 6자리라 µs 키 직접 비교는 반올림 오차로 어긋남."""
    bs = np.asarray(bag_stamps); t = np.asarray(t, dtype=float)
    i = np.clip(np.searchsorted(bs, t), 1, len(bs) - 1)
    left, right = bs[i - 1], bs[i]
    j = np.where(np.abs(t - left) <= np.abs(t - right), i - 1, i)
    ok = np.abs(bs[j] - t) < tol
    return j[ok], int((~ok).sum())


def jaccard(a: set, b: set):
    u = len(a | b)
    return len(a & b) / u if u else 1.0
