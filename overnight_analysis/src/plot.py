import glob
import sys as _sys
import numpy as np
import matplotlib
if "--save" in _sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.widgets import CheckButtons

# ===== 설정 =====
# 사용: python3 plot.py [mainlab|2ndfloor] [--save]   (--save: 창 없이 모든 페이지를 results/<seq>/plot_pageN.png로 저장)
import os, sys, re
SEQ = next((a for a in sys.argv[1:] if not a.startswith("--")), "mainlab")
SAVE_ONLY = "--save" in sys.argv
SEQ_DIR = os.path.expanduser("~/dlr_ws/sequences")
RES_DIR = os.path.expanduser(f"~/dlr_ws/results/{SEQ}")
# sequences/<seq>_<cond>_<N>/<seq>_<cond>_<N>.txt  (_incomplete / test 런 제외)
def _runs(cond):
    out = []
    for d in sorted(glob.glob(f"{SEQ_DIR}/{SEQ}_{cond}_*")):
        name = os.path.basename(d)
        if re.fullmatch(rf"{SEQ}_{cond}_\d+", name) and os.path.exists(f"{d}/{name}.txt"):
            out.append(f"{d}/{name}.txt")
    return sorted(out, key=lambda f: int(re.search(r"_(\d+)\.txt$", f).group(1)))
GROUPS = {
    "Both cameras": "both",
    "Left only":    "left",
    "Right only":   "right",
    "FAST-LIO2":    "fastlio",
}
# 비교 페이지(평균)용 대표 색
COLORS = {
    "Both cameras": "tab:blue",
    "Left only":    "tab:orange",
    "Right only":   "tab:green",
    "FAST-LIO2":    "tab:red",
}
# 그룹 내부 run 색: 같은 계열 colormap에서 명도를 다르게 뽑음
CMAPS = {
    "Both cameras": "Blues",
    "Left only":    "Oranges",
    "Right only":   "Greens",
    "FAST-LIO2":    "Reds",
}
RUN_ALPHA = 0.85
N = 500
# ================


def load_xyz(path):
    d = np.loadtxt(path, comments="#")
    return d[:, 0], d[:, 1:4]


def resample(t, xyz, n=N):
    u = (t - t[0]) / (t[-1] - t[0])
    ui = np.linspace(0, 1, n)
    return np.stack([np.interp(ui, u, xyz[:, k]) for k in range(3)], axis=1)


def run_colors(name, n):
    cmap = plt.get_cmap(CMAPS[name])
    # 너무 옅은 쪽(0~0.3)은 흰 배경에서 안 보이니 제외
    return [cmap(v) for v in np.linspace(0.35, 1.0, n)]


def set_equal(ax, pts):
    mn, mx = pts.min(axis=0), pts.max(axis=0)
    c, r = (mn + mx) / 2, (mx - mn).max() / 2 * 1.05
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))


def style(ax, title):
    ax.set_xlabel("X [m]"); ax.set_ylabel("Y [m]"); ax.set_zlabel("Z [m]")
    ax.set_title(title, fontsize=14)


# ----- 데이터 로드 -----
runs, means = {}, {}
for name, cond in list(GROUPS.items()):
    files = _runs(cond)
    print(f"{name}: {len(files)}개 파일")
    for f in files:
        print("   ", f)
    if not files:
        print(f"  -> {SEQ}_{cond}_N 런이 없어 이 그룹은 건너뜁니다.")
        del GROUPS[name]
        continue
    runs[name] = [resample(*load_xyz(f)) for f in files]
    means[name] = np.mean(runs[name], axis=0)

all_pts = np.vstack([r for g in runs.values() for r in g])
names = list(GROUPS)
n_pages = len(names) + 1

# 체크박스 on/off 상태 (페이지 넘겨도 유지)
#   그룹 페이지: [run1, ..., runN, mean]
#   비교 페이지: [group1, ..., group4]
state = {name: [True] * (len(runs[name]) + 1) for name in names}
state["__cmp__"] = [True] * len(names)

ax3d = None
check = None      # CheckButtons 참조 유지 (GC 방지)


# ----- 페이지 그리기 -----
def draw(page):
    global ax3d, check
    fig.clf()
    ax3d = fig.add_axes([0.20, 0.06, 0.78, 0.88], projection="3d")

    entries = []      # 체크박스 항목마다 켜고 끌 artist 리스트
    labels, label_colors = [], []

    if page < len(names):
        name = names[page]
        key = name
        cols = run_colors(name, len(runs[name]))
        for k, (r, c) in enumerate(zip(runs[name], cols)):
            ln, = ax3d.plot(r[:, 0], r[:, 1], r[:, 2], color=c, alpha=RUN_ALPHA,
                            linewidth=1.4, label=f"run {k+1}")
            entries.append([ln])
            labels.append(f"run {k+1}")
            label_colors.append(c)
        m = means[name]
        ln, = ax3d.plot(m[:, 0], m[:, 1], m[:, 2], color="black", linewidth=3, label="mean")
        s0 = ax3d.scatter(*m[0], c="lime", s=80, marker="o", edgecolors="k")
        s1 = ax3d.scatter(*m[-1], c="red", s=80, marker="X", edgecolors="k")
        entries.append([ln, s0, s1])
        labels.append("mean")
        label_colors.append("black")
        style(ax3d, f"{name} (n={len(runs[name])})   [{page+1}/{n_pages}]")
    else:
        key = "__cmp__"
        for name in names:
            m = means[name]
            ln, = ax3d.plot(m[:, 0], m[:, 1], m[:, 2], color=COLORS[name], linewidth=3, label=name)
            s1 = ax3d.scatter(*m[-1], color=COLORS[name], s=80, marker="X", edgecolors="k")
            entries.append([ln, s1])
            labels.append(name)
            label_colors.append(COLORS[name])
        style(ax3d, f"Mean trajectory comparison   [{page+1}/{n_pages}]")

    set_equal(ax3d, all_pts)
    ax3d.legend(loc="upper right")

    # 저장된 상태대로 표시/숨김 적용
    for arts, on in zip(entries, state[key]):
        for a in arts:
            a.set_visible(on)

    # ----- 체크박스 -----
    h = 0.045 * len(labels) + 0.03
    ax_chk = fig.add_axes([0.01, 0.55 - h / 2, 0.16, h])
    ax_chk.set_title("Show", fontsize=11)
    check = CheckButtons(ax_chk, labels, state[key])
    for txt, c in zip(check.labels, label_colors):
        txt.set_color(c)
        txt.set_fontweight("bold")

    def on_check(_label):
        st = check.get_status()
        state[key][:] = st
        for arts, on in zip(entries, st):
            for a in arts:
                a.set_visible(on)
        fig.canvas.draw_idle()

    check.on_clicked(on_check)

    fig.text(0.5, 0.01, "← / → : 이전/다음    s : 현재 페이지 저장    a : 전체 켜기/끄기    q : 종료",
             ha="center", fontsize=10, color="gray")
    fig.canvas.draw_idle()


page = 0


def current_key():
    return names[page] if page < len(names) else "__cmp__"


def on_key(event):
    global page
    if event.key in ("right", "n", " "):
        page = (page + 1) % n_pages
    elif event.key in ("left", "p"):
        page = (page - 1) % n_pages
    elif event.key == "s":
        os.makedirs(RES_DIR, exist_ok=True)
        fn = f"{RES_DIR}/plot_page{page+1}.png"
        fig.savefig(fn, dpi=200)
        print("저장:", fn)
        return
    elif event.key == "a":
        st = state[current_key()]
        st[:] = [not all(st)] * len(st)   # 하나라도 꺼져 있으면 전부 켜기, 아니면 전부 끄기
    else:
        return
    draw(page)


def on_scroll(event):
    if ax3d is None or event.inaxes is not ax3d:
        return
    s = 0.85 if event.button == "up" else 1 / 0.85
    for get, setl in [(ax3d.get_xlim, ax3d.set_xlim),
                      (ax3d.get_ylim, ax3d.set_ylim),
                      (ax3d.get_zlim, ax3d.set_zlim)]:
        lo, hi = get()
        c = (lo + hi) / 2
        setl(c - (c - lo) * s, c + (hi - c) * s)
    fig.canvas.draw_idle()


fig = plt.figure(figsize=(12, 9))
if SAVE_ONLY:
    os.makedirs(RES_DIR, exist_ok=True)
    for pg in range(n_pages):
        page = pg
        draw(pg)
        fig.savefig(f"{RES_DIR}/plot_page{pg+1}.png", dpi=150)
        print("저장:", f"{RES_DIR}/plot_page{pg+1}.png")
    raise SystemExit(0)
fig.canvas.mpl_connect("key_press_event", on_key)
fig.canvas.mpl_connect("scroll_event", on_scroll)
draw(page)
plt.show()
