# overnight_analysis — 다중 카메라 프레임 드롭 영향 + 퇴화 진단 (2026-11-28)

이 브랜치(`overnight-drop-analysis`)의 코드 변경(d29d524, 5dc7634)으로 실행한 실험의 분석 스크립트·결과·런 데이터 스냅샷.
원래 위치는 `~/dlr_ws`(별도 로컬 git 저장소, 커밋 beb14c6)이며, 그 저장소의 커밋된 파일을 그대로 옮겼다.

## 먼저 볼 것

- `results/SUMMARY.md` — 5개 질문에 대한 결론, 확신 정도, 다음 실험
- `results/mainlab_analysis.md`, `results/2ndfloor_analysis.md`, `results/mainlab_vs_2ndfloor.md`, `results/drop_ablation.md`, `results/degeneracy_analysis.md`
- `src/probsolv.md` — 단계별 계획 / 실제로 한 것 / 달라진 점과 원인 / 선택 이유, 에러·우회 기록 (`probsolv.md`는 이것을 가리키는 심볼릭 링크)
- `PROGRESS.md` — 진행 기록과 런 목록, `OVERNIGHT_TASK.md` — 원래 작업 지시

## 구성

| 경로 | 내용 |
|---|---|
| `scripts/` | 배치 실행(`run_batch.py`, `run_all.sh`, `run_extra*.sh`)과 분석 스크립트(`analyze_*.py`, `collect_stats.py`, `corridor_compare.py`, `bag_latency.py` 등) |
| `results/` | 보고서(md), 그림(png), 수치(json/csv), bag 타임스탬프 캐시(`cache/*.npz`) |
| `sequences/<seq>_<cond>_<N>/` | 런별 결과: 궤적(`.txt`, TUM), 선택 프레임(`.csv`), `_drops.csv`, `_timing.csv`, `_img_stats.csv`, diag 런은 `_lio_eig.csv`·`_vis_info.csv`, 실행 yaml, `run_info.json` |
| `src/plot.py` | 궤적 비교 그림 |

포함하지 않은 것: 점군(`*.pcd`), 런별 노드 콘솔 로그(`run.log`, 합계 약 2 GB), 원본 bag.

## 주의

- 스크립트는 작업 공간 경로 `~/dlr_ws`(sequences, results, bag 위치 `~/dlr_ros2_bag`)를 기준으로 작성돼 있다. 이 폴더에서 다시 돌리려면 `scripts/analysis_lib.py`의 `WS`, `BAGS`를 바꿔야 한다.
- 로깅은 yaml로 켜고 끈다: `diag_log.drop_timing_en`, `diag_log.degeneracy_en`(기본 false), 인위 드롭 `common.forced_drop_ratio`(기본 0.0)·`common.forced_drop_seed`.
