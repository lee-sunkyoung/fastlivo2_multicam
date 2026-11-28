#!/usr/bin/env python3
"""
FAST-LIVO2 / FAST-LIO2 순차 배치 실행기.

사용 예 (반드시 ROS 환경을 source 한 셸에서; scripts/run_batch.sh 가 대신 해 줌):
  python3 scripts/run_batch.py --seq mainlab --cond both left right fastlio --runs 1-5
  python3 scripts/run_batch.py --seq mainlab --cond both --runs 1 --tag test   # seq_name: mainlab_both_test1

한 런의 절차
  런별 yaml 생성(seq_name, 카메라 조건, 로깅/forced drop) → launch (출력은 run.log로)
  → '[img_stats]' 첫 줄이 나올 때까지 대기 → bag 1배속 재생(출력은 bag_play.log로)
  → 재생 종료 후 로그가 잠잠해질 때까지(최대 30 s) 대기 → launch에 SIGINT → 종료/저장 대기
  → Log/ 의 결과를 sequences/<seq_name>/ 로 이동 → PROGRESS.md 갱신.

이미 완료된 seq_name(sequences/<seq_name>/ 에 path·csv·pcd 존재)은 자동으로 건너뛴다.
결과가 일부만 있는 폴더는 <seq_name>_incomplete[N] 로 옮긴 뒤 다시 실행한다.
런은 한 번에 하나씩만 돈다(동시 실행 금지).
"""
import argparse
import copy
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

WS = Path.home() / "dlr_ws"
LIVO_PKG = WS / "src" / "FASTLIVO2_ROS2"
LOG = LIVO_PKG / "Log"
SEQ_DIR = WS / "sequences"
PROGRESS = WS / "PROGRESS.md"
BAGS = {
    "mainlab": Path.home() / "dlr_ros2_bag" / "ros2_bag_livo_2_cams_main_lab_2_loops",
    "2ndfloor": Path.home() / "dlr_ros2_bag" / "ros2_bag_livo_2_cams_2nd_floor",
}
LVIG_YAML = LIVO_PKG / "config" / "mid360_LVIG.yaml"
CAM_YAML = LIVO_PKG / "config" / "multi_cam.yaml"
TUM_RECORDER = WS / "scripts" / "path_to_tum.py"

PROC_PATTERNS = ["fastlivo_mapping", "fastlio_mapping", "parameter_blackboard", "ros2 bag play",
                 "path_to_tum.py", "mapping_justin.launch", "fast_lio mapping.launch"]


def now_s():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{now_s()}] {msg}", flush=True)


def bag_duration(bag: Path) -> float:
    meta = yaml.safe_load((bag / "metadata.yaml").read_text())
    return meta["rosbag2_bagfile_information"]["duration"]["nanoseconds"] * 1e-9


def leftover_procs():
    out = subprocess.run(["ps", "-eo", "pid,cmd"], capture_output=True, text=True).stdout.splitlines()[1:]
    me = os.getpid()
    res = []
    for line in out:
        pid, _, cmd = line.strip().partition(" ")
        if int(pid) == me or "run_batch" in cmd or "grep" in cmd:
            continue
        if any(p in cmd for p in PROC_PATTERNS):
            res.append((int(pid), cmd))
    return res


def kill_leftovers():
    procs = leftover_procs()
    for pid, cmd in procs:
        log(f"  leftover process found, SIGINT: {pid} {cmd[:100]}")
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    if procs:
        time.sleep(8)
        for pid, cmd in leftover_procs():
            log(f"  still alive, SIGKILL: {pid} {cmd[:100]}")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(2)
    return procs


# ---------------------------------------------------------------- completion check
def required_files(seq_name, is_fastlio):
    if is_fastlio:
        return [f"{seq_name}.txt"]
    return [f"{seq_name}.txt", f"{seq_name}.csv", "all_raw_points.pcd"]


def is_complete(seq_name, is_fastlio):
    d = SEQ_DIR / seq_name
    if not d.is_dir():
        return False
    return all((d / f).is_file() and (d / f).stat().st_size > 0 for f in required_files(seq_name, is_fastlio))


def mark_incomplete(seq_name):
    d = SEQ_DIR / seq_name
    k = 0
    while True:
        dst = SEQ_DIR / (f"{seq_name}_incomplete" + (str(k) if k else ""))
        if not dst.exists():
            break
        k += 1
    shutil.move(str(d), str(dst))
    log(f"  incomplete result moved: {d.name} -> {dst.name}")
    return dst


# ---------------------------------------------------------------- yaml generation
def make_params(seq_name, cond, run_idx, out_dir: Path):
    lvig = yaml.safe_load(LVIG_YAML.read_text())
    cam = yaml.safe_load(CAM_YAML.read_text())
    p = lvig["/**"]["ros__parameters"]
    c = cam["/**"]["ros__parameters"]
    p["evo"]["seq_name"] = seq_name
    p.setdefault("diag_log", {})
    p["diag_log"]["drop_timing_en"] = True
    p["common"]["forced_drop_ratio"] = 0.0
    p["common"]["forced_drop_seed"] = 0
    cond = re.sub(r"_off\d+", "", cond)  # _offNN: 재생 시작 위치만 바꿈 (yaml 동일)
    cond = cond[:-len("_nomp")] if cond.endswith("_nomp") else cond  # _nomp: 같은 조건 + OpenMP 1스레드 (env로 처리, yaml 동일)
    p["diag_log"]["degeneracy_en"] = cond.endswith("_diag")
    if cond.endswith("_diag") and not cond.startswith("both"):
        cond = cond[:-len("_diag")]  # left_diag / right_diag: 카메라 설정은 left/right와 동일
    m = re.match(r"both_drop(\d+)$", cond)
    if m:
        p["common"]["forced_drop_ratio"] = int(m.group(1)) / 100.0
        p["common"]["forced_drop_seed"] = int(run_idx)
    if cond.startswith("both"):
        p["common"]["camera_count"] = 2
    elif cond == "left":
        p["common"]["camera_count"] = 1          # camera_1 block = left front camera
    elif cond == "right":
        p["common"]["camera_count"] = 1          # put the right camera into the camera_1 slot
        p["camera_1"] = copy.deepcopy(p["camera_2"])
        p["camera_1"]["calib_ns"] = "camera_1"
        c["camera_1"] = copy.deepcopy(c["camera_2"])
    else:
        raise ValueError(cond)
    lp, cp = out_dir / "params_lvig.yaml", out_dir / "params_cam.yaml"
    lp.write_text(yaml.safe_dump(lvig, sort_keys=False))
    cp.write_text(yaml.safe_dump(cam, sort_keys=False))
    return lp, cp


# ---------------------------------------------------------------- helpers
def wait_for_text(path: Path, pattern: str, timeout: float, proc=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc is not None and proc.poll() is not None:
            return False
        if path.exists() and pattern in path.read_text(errors="ignore"):
            return True
        time.sleep(0.5)
    return False


def wait_quiet(path: Path, quiet_s=3.0, max_s=30.0):
    t0 = time.time()
    last = path.stat().st_size if path.exists() else 0
    last_change = time.time()
    while time.time() - t0 < max_s:
        time.sleep(0.5)
        sz = path.stat().st_size if path.exists() else 0
        if sz != last:
            last, last_change = sz, time.time()
        elif time.time() - last_change >= quiet_s:
            return time.time() - t0
    return time.time() - t0


def stop_launch(proc, timeout=180):
    """SIGINT to ros2 launch (it forwards to its nodes), wait for clean exit; escalate if needed."""
    if proc.poll() is not None:
        return "already_exited", proc.returncode
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
        return "sigint", proc.returncode
    except subprocess.TimeoutExpired:
        pass
    log("  launch did not exit after SIGINT, sending second SIGINT")
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=30)
        return "sigint2", proc.returncode
    except subprocess.TimeoutExpired:
        pass
    log("  escalating to SIGTERM/SIGKILL on process group")
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
        return "sigterm", proc.returncode
    except Exception:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        return "sigkill", proc.returncode


def parse_img_stats(run_log: Path):
    """Last '[img_stats] camN recv=...' line per camera -> list of dicts."""
    pat = re.compile(r"\[img_stats\] cam(\d+) recv=(\d+) used=(\d+)\(([\d.]+)%\) \| skipped\(old\)=(\d+)\(([\d.]+)%\) "
                     r"stale=(\d+) overflow=(\d+) dup=(\d+) loop=(\d+) jump=(\d+) before_lidar=(\d+) cv=(\d+)")
    pat2 = re.compile(r"\[img_stats\] cam(\d+) forced=(\d+) total_drop=([\d.]+)%")
    last, last2 = {}, {}
    for line in run_log.read_text(errors="ignore").splitlines():
        m = pat.search(line)
        if m:
            last[int(m.group(1))] = m.groups()
        m2 = pat2.search(line)
        if m2:
            last2[int(m2.group(1))] = m2.groups()
    keys = ["cam", "recv", "used", "used_pct", "skipped_old", "skipped_old_pct", "stale", "overflow", "dup", "loop", "jump",
            "before_lidar", "cv"]
    rows = []
    for cam in sorted(last):
        r = dict(zip(keys, last[cam]))
        if cam in last2:
            r["forced"], r["total_drop_pct"] = last2[cam][1], last2[cam][2]
        rows.append(r)
    return rows


def update_progress(line):
    txt = PROGRESS.read_text() if PROGRESS.exists() else "# PROGRESS\n\n## 완료된 런\n"
    txt = txt.replace("(아직 없음 — run_batch가 런 종료마다 아래에 한 줄씩 추가)\n", "")
    if not txt.endswith("\n"):
        txt += "\n"
    txt += line + "\n"
    PROGRESS.write_text(txt)


# ---------------------------------------------------------------- one run
def run_one(seq, cond, run_label, run_idx, args):
    is_fastlio = cond == "fastlio"
    seq_name = f"{seq}_{cond}_{run_label}"
    out = SEQ_DIR / seq_name
    if is_complete(seq_name, is_fastlio):
        log(f"SKIP {seq_name} (already complete)")
        return "skipped"
    if out.exists():
        mark_incomplete(seq_name)
    out.mkdir(parents=True)

    procs = kill_leftovers()
    if procs:
        (out / "leftover_procs.txt").write_text("\n".join(f"{p} {c}" for p, c in procs))

    # leftovers of an earlier failed attempt with the same name must not be mistaken for this run's output
    stale = [LOG / "result" / f"{seq_name}.txt"] + list(LOG.glob(f"{seq_name}.csv")) + list(LOG.glob(f"{seq_name}_*.csv")) \
        + list((LOG / "PCD").glob("all_*.pcd"))
    for f in stale:
        if f.exists():
            (out / "prev_leftover").mkdir(exist_ok=True)
            shutil.move(str(f), str(out / "prev_leftover" / f.name))

    bag = BAGS[seq]
    dur = bag_duration(bag)
    info = {"seq_name": seq_name, "seq": seq, "cond": cond, "run": run_label, "bag": str(bag), "bag_duration_s": dur,
            "start": now_s(), "status": "running"}
    run_log, bag_log = out / "run.log", out / "bag_play.log"
    log(f"RUN  {seq_name}  (bag {dur:.0f}s)")

    rec = None
    if is_fastlio:
        cmd = ["ros2", "launch", "fast_lio", "mapping.launch.py", "rviz:=false"]
        info["launch_cmd"] = " ".join(cmd)
        launch = subprocess.Popen(cmd, stdout=open(run_log, "w"), stderr=subprocess.STDOUT, start_new_session=True)
        ready_pat = "Node init finished"  # fallback: just wait a fixed time if not found
        ok = wait_for_text(run_log, ready_pat, 20, launch)
        if not ok:
            time.sleep(5)
        tum_path = out / f"{seq_name}.txt"
        rec = subprocess.Popen([sys.executable, str(TUM_RECORDER), str(tum_path)], stdout=open(out / "tum_recorder.log", "w"),
                               stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(3)
    else:
        lp, cp = make_params(seq_name, cond, run_idx, out)
        cmd = ["ros2", "launch", "fast_livo", "mapping_justin.launch.py", "use_rviz:=false",
               f"avia_params_file:={lp}", f"camera_params_file:={cp}"]
        env = os.environ.copy()
        if cond.endswith("_nomp"):
            env["OMP_THREAD_LIMIT"] = "1"  # omp_set_num_threads(MP_PROC_NUM)보다 우선하는 상한 → 병렬 reduction 비결정성 제거 시험
            env["OMP_NUM_THREADS"] = "1"
            info["env"] = {"OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"}
        info["launch_cmd"] = " ".join(cmd)
        launch = subprocess.Popen(cmd, stdout=open(run_log, "w"), stderr=subprocess.STDOUT, start_new_session=True, env=env)
        ok = wait_for_text(run_log, "[img_stats]", 90, launch)
        if not ok:
            info["status"] = "failed_start"
            info["note"] = "node did not reach run loop ([img_stats]) within 90 s or exited"
            stop_launch(launch, 30)
            (out / "run_info.json").write_text(json.dumps(info, indent=1))
            log(f"FAIL {seq_name}: start failed")
            update_progress(f"- [ ] {seq_name} — FAILED start ({now_s()})")
            return "failed"
        time.sleep(3)  # let subscriptions settle

    t_play = time.time()
    play_cmd = ["ros2", "bag", "play", str(bag), "--rate", "1.0"]
    m_off = re.search(r"_off(\d+)", cond)  # _offNN: bag을 NN s 지점부터 재생 (드롭 급증이 bag 시각/재생 경과 시각 중 어디에 묶이는지 시험)
    if m_off:
        play_cmd += ["--start-offset", m_off.group(1)]
    info["play_cmd"] = " ".join(play_cmd)
    bp = subprocess.Popen(play_cmd, stdout=open(bag_log, "w"),
                          stderr=subprocess.STDOUT, start_new_session=True)
    try:
        bp.wait(timeout=dur + 120)
    except subprocess.TimeoutExpired:
        log("  bag play timeout, SIGINT")
        bp.send_signal(signal.SIGINT)
        bp.wait(timeout=30)
    info["bag_play_wall_s"] = round(time.time() - t_play, 1)
    info["bag_play_rc"] = bp.returncode
    info["node_alive_after_bag"] = launch.poll() is None

    info["post_bag_wait_s"] = round(wait_quiet(run_log, 3.0, 30.0), 1)
    if rec is not None:
        rec.send_signal(signal.SIGINT)
        try:
            rec.wait(timeout=20)
        except subprocess.TimeoutExpired:
            rec.kill()
    how, rc = stop_launch(launch)
    info["stop"], info["launch_rc"] = how, rc
    time.sleep(1)

    # move results
    moved = []
    if is_fastlio:
        moved.append(f"{seq_name}.txt")
    else:
        for src in [LOG / "result" / f"{seq_name}.txt", LOG / f"{seq_name}.csv", *LOG.glob(f"{seq_name}_*.csv"),
                    *(LOG / "PCD").glob("all_*.pcd")]:
            if src.exists():
                shutil.move(str(src), str(out / src.name))
                moved.append(src.name)
        rows = parse_img_stats(run_log)
        if rows:
            keys = list(rows[0].keys())
            with open(out / "img_stats_from_log.csv", "w") as f:
                f.write(",".join(keys) + "\n")
                for r in rows:
                    f.write(",".join(str(r.get(k, "")) for k in keys) + "\n")
        _txt = run_log.read_text(errors="ignore")
        info["clean_finish_marker"] = ("Downsampled point cloud data saved" in _txt) or ("[diag] run finished" in _txt)
        info["exit_segfault"] = "exit code -11" in _txt
    info["moved"] = moved
    info["end"] = now_s()
    complete = is_complete(seq_name, is_fastlio)
    info["status"] = "complete" if complete else "incomplete"
    (out / "run_info.json").write_text(json.dumps(info, indent=1))

    stats_txt = ""
    if not is_fastlio:
        rows = parse_img_stats(run_log)
        stats_txt = "; ".join(f"cam{r['cam']} used {r['used']}/{r['recv']} old {r['skipped_old']} ovf {r['overflow']}"
                              + (f" forced {r['forced']}" if 'forced' in r else "") for r in rows)
    mark = "x" if complete else " "
    update_progress(f"- [{mark}] {seq_name} — {info['status']} ({info['end']}) stop={how} {stats_txt}")
    log(f"DONE {seq_name}: {info['status']} stop={how} moved={moved}")
    return info["status"]


def parse_runs(s):
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", required=True, choices=list(BAGS))
    ap.add_argument("--cond", nargs="+", required=True)
    ap.add_argument("--runs", default="1-5")
    ap.add_argument("--tag", default="", help="label prefix, e.g. 'test' -> <seq>_<cond>_test1")
    ap.add_argument("--order", choices=["cond_major", "run_major"], default="run_major",
                    help="run_major: both1,left1,right1,fastlio1,both2,... (spreads slow drifts in machine state across conditions)")
    args = ap.parse_args()
    runs = parse_runs(args.runs)
    plan = [(c, r) for r in runs for c in args.cond] if args.order == "run_major" else [(c, r) for c in args.cond for r in runs]
    log(f"plan: {[f'{args.seq}_{c}_{args.tag}{r}' for c, r in plan]}")
    res = {}
    for cond, r in plan:
        label = f"{args.tag}{r}"
        try:
            res[f"{args.seq}_{cond}_{label}"] = run_one(args.seq, cond, label, r, args)
        except Exception as e:  # never stop the whole batch
            log(f"ERROR in {args.seq}_{cond}_{label}: {e!r}")
            update_progress(f"- [ ] {args.seq}_{cond}_{label} — ERROR {e!r} ({now_s()})")
            res[f"{args.seq}_{cond}_{label}"] = "error"
            kill_leftovers()
    log(f"batch finished: {res}")


if __name__ == "__main__":
    main()
