# probsolv.md — 밤샘 작업 문제 해결 기록

> 위치: OVERNIGHT_TASK.md 갱신본의 "초기 실행시 probsolv.md가 없다면 ~/dlr_ws/src/ 에 생성" 지시에 따라
> `~/dlr_ws/src/probsolv.md`에 만들었다. 작업 원칙의 `~/dlr_ws/probsolv.md` 경로로도 열 수 있게 심볼릭 링크를 걸었다.

---

## Phase 0. 환경 조사 (2026-11-28 03:4x)

### 계획
코드·yaml·launch·이전 결과(~/pcd_save)를 보고 실행 방법, 저장 위치, 조건별 설정 방법을 파악한다.

### 실제로 한 것 / 파악한 내용
- **빌드/설치**: `install/fast_livo/share/fast_livo/config/*.yaml`은 src의 yaml에 대한 심볼릭 링크(symlink-install).
  → yaml을 수정하면 재빌드 없이 바로 반영된다. C++ 수정은 `colcon build --packages-select fast_livo`가 필요.
- **Log 위치**: `ROOT_DIR = src/FASTLIVO2_ROS2/` (CMake 정의). 즉 Log는 `~/dlr_ws/src/FASTLIVO2_ROS2/Log/`.
  - path: `Log/result/<evo.seq_name>.txt` (handleLIO에서 LIO 업데이트마다 TUM 형식으로 기록, VIO 업데이트 전 상태)
  - 선택 기록 csv: `Log/selected_YYYYMMDD_HHMMSS.csv` (cam, capture_time, last_lio_update_time)
  - pcd: `Log/PCD/all_raw_points.pcd`, `all_downsampled_points.pcd` (종료 시 savePCD, 매번 덮어씀)
- **중요: "드롭 csv"의 실제 내용** — `selected_*.csv`는 드롭된 프레임이 아니라 **VIO에 사용(선택)된 프레임**의 기록이다.
  드롭된 프레임 = (bag 안의 해당 카메라 전체 이미지 타임스탬프) − (선택된 타임스탬프). Phase 3에서 이렇게 계산한다.
- **드롭 유형(코드상)**: img_cbk에서 before_lidar/duplicate/loopback/timejump, 큐 길이 초과 시 overflow(camera_queue_max=3),
  sync_packages에서 horizon 안의 가장 최신 프레임만 고르고 그보다 오래된 큐 프레임은 `dropped_old`(=로그의 skipped(old)),
  last_lio_update_time보다 오래된 건 stale. `[img_stats]` 로그가 10초마다 + 종료 시 출력된다.
- **처리 시간 로그**: LIO는 printf 표(“Current Total Time”), VIO는 `[Image latency] ... VIO process: X ms`가 이미 있다.
  → 화면용 printf라 파싱이 불안정하므로 Phase 2에서 yaml on/off 가능한 프레임 타이밍 csv를 추가할 예정.
- **bag**: 두 bag의 토픽 목록이 완전히 같다(`/livox/lidar`(CustomMsg), `/livox/imu`,
  `/camera/rgbd_front_{left,right}/color/image_raw`). 길이: main_lab_2_loops 223.3 s, 2nd_floor 295.1 s.
  → 2ndfloor도 토픽 리매핑 불필요.
- **양쪽/왼쪽/오른쪽 설정 방법(추정)**: git 이력·bash_history에 left/right 전환 기록이 없다.
  코드상 가능한 방법은 `common.camera_count`와 `camera_N` 블록뿐이다.
  - both: 현재 yaml 그대로 (camera_count: 2, single_vio_manager_mode: false)
  - left: camera_count: 1 → camera_1(왼쪽) 블록만 사용
  - right: camera_count: 1 + camera_1 블록을 오른쪽 토픽/외부 파라미터(Rcl/Pcl)로, multi_cam.yaml의 camera_1 내부 파라미터를 오른쪽 값으로 교체
  - 선택 이유: 코드에 "오른쪽만" 옵션이 없고, single_vio_manager_mode=true는 cam0(왼쪽)만 선택 가능하게 할 뿐이라 오른쪽 단독 실행이 불가능.
    블록 교체는 알고리즘 코드를 건드리지 않는 유일한 방법이다.
- **FAST-LIO2 실행 방법**: `ros2 launch fast_lio mapping.launch.py` (기본 config_file=mid360.yaml, src/FAST_LIO_ROS2)
  + `~/tum.py`(/path 구독 → TUM 파일 저장)로 path를 기록한 것으로 판단.
  근거: FAST_LIO_ROS2 코드에는 TUM 출력이 없고, ~/pcd_save/fastlio2/*.txt가 tum.py 형식(소수 9자리)과 같으며 tum.py의 수정 시각(11/10 12:59)이 fastlio2_1.txt(13:04) 직전.
- **git**: ~/dlr_ws 자체는 git 저장소가 아니다. src/FASTLIVO2_ROS2(브랜치 marvin, 작업트리 깨끗), FAST_LIO_ROS2, vikit은 각자 저장소.

### 이번 세션에서 정한 운영 방식과 이유
- **git commit**: (1) 코드 변경은 `src/FASTLIVO2_ROS2` 저장소에 새 브랜치 `overnight-drop-analysis`(marvin에서 분기)를 만들어 커밋 —
  사용자의 marvin 브랜치를 직접 바꾸지 않기 위해. (2) 스크립트·결과·기록은 `~/dlr_ws`에 git init 후 커밋
  (build/install/log, 중첩 저장소, *.pcd는 .gitignore). Phase마다 양쪽에 Phase 번호를 넣어 커밋.
- **런별 yaml**: 원본 yaml을 런마다 sed로 고치지 않고, 런마다 `sequences/<seq>/params_*.yaml`을 생성해서 launch 인자
  (avia_params_file, camera_params_file)로 넘긴다. 원본 yaml이 중간 실패로 오염되는 일을 막고, 각 런이 쓴 설정이 결과와 함께 남는다.
- **rviz**: `use_rviz:=false`로 실행. 무인 실행 중 GPU/CPU 부하 변동이 드롭률에 영향을 주는 것을 줄이고, 디스플레이 문제로 런이 막히는 것을 막기 위해.
  (이전 ~/pcd_save 실험은 rviz를 켠 상태였을 가능성이 높으므로, 드롭률 절대값은 이전 실험과 직접 비교하지 않는다.)
- 기존 `Log/` 내용(사용자의 이전 결과: result/both_1.txt, left_4.txt, marvin_main2loop.txt, PCD, selected_*.csv)은
  첫 런 전에 `~/dlr_ws/backup_Log_before_overnight/`로 복사해 둔다(PCD는 매 런 덮어써지므로).

---

## 중단 기록 1 (2026-11-28 03:47경)

### 무슨 일이 있었나
- Phase 0 조사 도중(bag 토픽 비교 직전) 사용자가 실수로 세션을 중단했고, OVERNIGHT_TASK.md를 갱신한 뒤 재개를 요청했다.
- 갱신된 부분: 작업 원칙(launch/bag 출력은 파일로 리다이렉트, 폴링 출력 금지 → 스크립트 내부 대기),
  "이어서 하기" 절(PROGRESS.md, 완료 런 건너뛰기, 불완전 런은 _incomplete로 이동 후 재실행, 배치 스크립트 자동 건너뛰기),
  probsolv.md 생성 위치(~/dlr_ws/src/), Phase 5 문구.

### 재개 시 확인한 것
- 남은 프로세스: `ps`로 ros2/fastlivo/fastlio/rviz/parameter_blackboard/tum.py/run_batch 검색 → **없음**. 정리할 것 없음.
- 중단된 런: **없음**. 중단 시점에는 아직 코드 수정도, 런 실행도 하지 않았다 (sequences/ 비어 있음).
  Log/result의 both_1.txt(11/16), left_4.txt(11/16), marvin_main2loop.txt(11/28 03:07)와 PCD(11/28 03:25)는
  모두 이번 세션 시작(03:40) 전 사용자 본인의 실행 결과로 이번 작업과 무관 → 건드리지 않음(백업만).
- 따라서 _incomplete로 표시할 대상 없음. Phase 0 조사 결과는 위에 정리했고 Phase 1부터 진행한다.

---

## Phase 1. 저장 방식 수정 (+ 이후 Phase에 필요한 C++ 계측을 한 번에 추가)

### 계획
selected csv 이름을 seq_name으로 바꾸고, 배치 실행 스크립트를 만든 뒤 1런 테스트.

### 실제로 한 것
- **C++ 변경을 Phase 1~7분을 한꺼번에 넣고 한 번만 빌드**했다 (브랜치 `overnight-drop-analysis`).
  이유: "실행 중 빌드 금지"라서, Phase 6/7 계측을 나중에 넣으면 런 배치 사이에 빌드를 끼워야 하고 바이너리가 배치 중간에 바뀔 위험이 있다.
  계측은 모두 yaml 파라미터로 꺼져 있고(기본 off), 켜도 추정에 쓰이는 값은 읽기만 한다.
  - selected csv: `Log/<seq_name>.csv` (기존 3열 뒤에 `wall_age_ms`(수신→선택 벽시계 지연), `horizon_time` 열 추가 — 기존 열 순서는 그대로)
  - `diag_log.drop_timing_en` (기본 false): `Log/<seq>_drops.csv`(드롭 이벤트: reason=old/overflow/stale/forced, 수신 후 경과 ms,
    horizon 대비 데이터 지연 s), `Log/<seq>_timing.csv`(LIO/VIO 프레임별 처리 시간 ms, VIO는 이미지 도착→VIO 시작 지연),
    종료 시 `Log/<seq>_img_stats.csv`(카메라별 recv/used/old/stale/overflow/forced/…/총 드롭률)
  - `common.forced_drop_ratio` (기본 0.0), `common.forced_drop_seed` (기본 0): Phase 5용. 0이면 분기 자체를 타지 않는다.
  - `diag_log.degeneracy_en` (기본 false): Phase 6/7용 `_lio_eig.csv`, `_vis_info.csv`
  - `[img_stats]` 로그에 `forced=`, `total_drop=` 줄 추가.
- **기본 동작 불변 근거**: 새 코드는 (a) 파라미터가 켜졌을 때만 실행되는 파일 쓰기, (b) `forced_drop_ratio > 0.0 &&`로 막힌 분기,
  (c) LIO/VIO 업데이트 안에서 H_T_H 6×6 블록을 별도 멤버에 **복사만** 하는 줄(추정 값에 다시 쓰이지 않음)뿐이다.
  run-to-run 비결정성(타이밍 의존 드롭) 때문에 비트 단위 동일성 테스트는 불가능하므로 코드 검토로 확인했다.
- **배치 스크립트**: `scripts/run_batch.py` (+ ROS 환경 source용 `run_batch.sh`, FAST-LIO path 기록용 `path_to_tum.py`).
  - 런별 yaml을 `sequences/<seq>/params_lvig.yaml`, `params_cam.yaml`로 생성해 launch 인자로 넘김 (원본 yaml 불변).
  - 준비 판정: run.log에 `[img_stats]`(run 루프 진입 시 첫 출력)가 나오면 +3 s 후 bag 재생.
  - 재생 종료 후 run.log 크기가 3 s 동안 안 변할 때까지(최대 30 s) 대기 → launch에 SIGINT → 최대 180 s 대기(이후 2차 SIGINT → SIGTERM → SIGKILL).
  - 결과(path, csv들, pcd 2개) 이동 + `img_stats_from_log.csv`(로그의 마지막 img_stats 파싱) + `run_info.json`(상태/종료 방식/시간).
  - 완료 판정: path·selected csv·all_raw_points.pcd가 모두 있고 비어 있지 않음 (FAST-LIO는 path만). 완료된 seq_name은 자동 건너뜀,
    일부만 있으면 `<seq>_incomplete[N]`로 옮기고 재실행. 런 시작 전 남은 ros2 프로세스가 있으면 정리하고 기록.
  - 실행 순서 기본값은 run_major(both1,left1,right1,fastlio1,both2,…): 시간에 따라 기계 상태(온도, 캐시 등)가 변해도 한 조건에 몰리지 않게.
  - 모든 launch/bag 출력은 런 폴더의 run.log/bag_play.log로 리다이렉트.
- FAST-LIO의 /path는 10 프레임마다 발행(laserMapping.cpp `jjj % 10`) → path가 약 2 Hz. 이전 ~/pcd_save/fastlio2와 같은 방식이라 그대로 둠.

### 계획과 달라진 점 / 에러
- 첫 테스트가 바로 실패: `run_batch.sh`의 `set -u` 때문에 `/opt/ros/jazzy/setup.bash: AMENT_TRACE_SETUP_FILES: unbound variable`.
  → `set -u` 제거 후 재실행.
- pandas가 설치돼 있지 않음 → 분석 스크립트는 numpy/csv/matplotlib만 사용 (시스템 패키지를 새로 설치하지 않기 위해).

### 1런 테스트 결과 (mainlab_both_test1, 03:55~03:59)
- 파일 4종(path `mainlab_both_test1.txt`, selected csv, pcd 2개, run.log) + drops/timing/img_stats csv 모두 정상 이동. 상태 complete, SIGINT로 정상 종료 루트.
- **예상과 다른 점 1 — 종료 시 segfault**: 노드가 SIGINT 후 `savePCD`까지 끝낸 다음 `exit code -11`로 죽는다.
  모든 csv는 savePCD 전에 flush하므로 데이터 손실은 없음. 내 `[diag] run finished` 출력 전에 죽는 것으로 보아
  rclcpp shutdown 이후 정적 객체(예: publish_odometry의 static TransformBroadcaster) 소멸 시점 문제로 추정 — 알고리즘과 무관하고
  결과 파일에 영향이 없어 고치지 않음(코드 동작 변경 최소화). 완료 표시는 "Downsampled point cloud data saved" 문자열로 판정하도록 수정,
  run_info.json에 `exit_segfault` 기록.
- 드롭 회계 확인: recv = used + skipped(old) + stale + overflow (5399 = 4242+687+401+69) → 노드 안 드롭은 csv로 빠짐없이 추적됨.
- **bag 이미지 수 착각 정정**: metadata의 6692는 camera_info 개수였다. 실제 color/image_raw는 mainlab 왼 5407 / 오 5406 (약 180 s 구간),
  2ndfloor 8847 / 8846. 노드 recv는 5399/5395 → DDS 전송 손실은 시작/끝 몇 프레임 수준(무시 가능).
- 테스트 런의 드롭률: both에서 카메라당 총 드롭 21.4% (old 12.7%, stale 7.5%, overflow 1.3%).
- bag 이미지 타임스탬프는 CDR 헤더 8바이트만 파싱해서 `results/cache/<seq>_image_stamps.npz`에 캐시 (두 bag 57 s, 런 없는 때 실행).
- 테스트 런 폴더 `mainlab_both_test1`은 분석에서 제외(이름 패턴이 `_<숫자>`가 아님).

---

## 실행 계획 (04:01~)
- `scripts/run_all.sh`로 60런을 한 체인으로 순차 실행: mainlab(both/left/right/fastlio ×5) → 2ndfloor(같음) → mainlab both_drop20/50 ×5 → both_diag ×5 (mainlab, 2ndfloor).
  - 이유: 런 사이에 사람(나)의 응답 지연이 끼지 않아 전체 시간이 줄고, 중단돼도 재실행 시 완료 런을 건너뛴다.
  - Phase 6(T1) 코드는 이미 빌드에 포함 → 별도 빌드 없이 Phase 7 diag 런에서 T1·T2를 함께 기록.
  - 분석(Phase 3 등)은 다음 bag 런이 도는 동안 `nice -n 19`로 가볍게 돌린다(빌드 같은 무거운 작업은 하지 않음).
    분석 프로세스가 드롭률에 줄 수 있는 영향은 각 런의 처리시간 csv로 사후 확인한다.

---

## Phase 3 준비 — 지표 정의 변경 (04:20경, Phase 2 런 도중 첫 결과로 확인)

### 계획
"끝점 drift = 루프의 시작~끝 위치 차이"

### 실제로 발견한 것 / 계획과 달라진 점
- mainlab_2_loops bag은 **출발점에서 끝나지 않는다.** 모든 궤적(LIVO2와 FAST-LIO 모두)이 약 180 s(이미지·LiDAR 둘 다 이 시점에 끝남;
  metadata 223 s는 다른 토픽 포함)에서 끝나고, 1회차는 약 101~113 s에 출발점 근처를 다시 지나며, bag은 **2회차 약 40% 지점(위쪽 복도)**에서 끝난다.
  → "시작~끝 차이"는 drift가 아니라 "끝 위치 추정의 차이"다(물리적으로 출발점에서 ~20 m 떨어진 곳에서 끝남).
- 시간을 고정해서 비교하는 방법(예: t=107 s 위치 − 시작)은 진행 방향 오차가 1.2 m/s × 몇 초만큼 섞여 쓸 수 없다고 판단.
- **대체 지표(시간 대응이 필요 없는 자기 일관성)**:
  1. 1→2회차 경로 겹침 오차: 2회차의 각 점에서 1회차 경로까지 최근접 수평 거리(median, p90). 같은 길을 두 번 달렸다는 가정(두 카메라 결과에서 두 루프가 거의 겹쳐 보여 타당).
  2. 끝점→1회차 경로 거리: 끝 위치는 1회차에 지나간 복도 위여야 한다.
  3. 출발점 재방문 최근접 거리(드리프트의 하한; 경로가 우연히 출발점을 지나면 작게 나옴 — left_1이 그 예).
  4. 평지 z 이탈(z RMS, |z| 최대): 같은 층을 주행하므로 z≈0이어야 한다(가정: 층 이동 없음).
  5. 시작~끝 차이는 표에 남기되 "drift 아님"으로 명시.
- 복도 축: 처음엔 xy PCA를 썼으나 직사각형 경로에서 축이 대각선으로 기울어짐([-0.42, 0.91]) →
  이동 heading의 지배 방향(90° 주기, 직교 복도 가정) 중 총 이동이 긴 쪽을 주 복도 축으로 변경.
  5회 편차는 시간 격자에서 평균 궤적 대비 along-track(국소 진행 방향)/cross-track/z로 분해.
- 드롭 프레임 비교에서 csv(소수 6자리)와 bag 스탬프의 µs 키 직접 비교가 반올림 오차로 어긋나 드롭 수가 과대(left에서 829개) 계산됨 →
  가장 가까운 bag 프레임(±2 ms)에 매칭하도록 수정. 수정 후 노드 자체 회계(used/recv)와 정확히 일치.
- 첫 런 관찰(n=1이라 결론 아님): mainlab에서 FAST-LIO·left·right는 긴 세로 복도(x≈−20) 길이를 줄여 추정하고 두 루프가 어긋나는 반면,
  both는 두 루프가 거의 겹친다. 드롭은 both에서만 카메라당 ~21%, 단일 카메라는 ~0%.

---

## Phase 2 (04:01~05:15)
- 계획대로 20런 모두 complete. 모든 런이 SIGINT 정상 경로로 종료(노드는 저장 후 segfault, 결과 영향 없음 — Phase 1 참고).
- 실행 순서는 run_major. mainlab_both_2(04:16~04:20)는 내가 nice -n 19로 분석 스크립트를 돌린 시간과 겹쳤으나 드롭률 21.3/21.3%로 다른 런(19.4~22.1%)과 차이 없음.
- 처리 시간 로그는 기존 printf 표 대신 Phase 1에서 추가한 `_timing.csv`(yaml on/off) 사용. `results/mainlab/run_stats.csv`로 정리.

## Phase 3 (05:15~)
### 계획과 달라진 점
- 끝점 drift 지표 대체(앞 절 참조).
- compare_selected.py는 "두 csv의 첫 차이" 출력 도구라서 수정 대신 그 기능을 `analyze_seq.py`의 drop_metrics로 확장
  (5회 비교: ∩/∪, 쌍별 Jaccard, k-of-N vs 이항분포, 시간 히스토그램, 드롭 이유·지연). 원래 2-파일 비교 기능은 그대로 둠.
  → 이유: "선택된 프레임" csv에서 드롭 집합을 얻으려면 bag의 전체 이미지 타임스탬프가 필요해서 단일 파일 비교 도구 구조로는 맞지 않음.
### 예상과 다른 결과
- 가설(드롭→성능 저하)과 반대 방향의 데이터: 드롭이 많은 both가 가장 좋고, 드롭 없는 단일 카메라 런이 크게 갈라진다.
- 런 간 갈라짐이 계단식이며 특정 위치(긴 복도 북쪽 끝)에서 일어남. FAST-LIO2는 결정적(5회 동일), LIVO2는 입력이 같아도 비결정적.
  → 추가 검증 실험(MP 끈 빌드)을 모든 계획 런이 끝난 뒤에 하기로 함(실행 중 빌드 금지 원칙 때문).

## Phase 4 (05:15~06:57 런, 06:57~ 분석)
### 계획
- 2ndfloor 4조건×5 = 20런 → mainlab과 같은 분석(collect_stats, analyze_seq, plot.py, corridor_compare) → `results/2ndfloor_analysis.md`, `results/mainlab_vs_2ndfloor.md`.
### 실제로 한 것
- 20런 모두 complete (실패 0). 분석은 Phase 5 런과 겹쳐서 모두 `nice -n 19`로 실행(로그 `results/phase4_analysis.log`).
- 예정에 없던 보조 스크립트 `scripts/analyze_2ndfloor_extra.py` 추가: 런별 발산 시각/위치, 발산 전 드롭률, 첫 |z|>1·2 m 시각, 발산 전 구간만 그린 궤적, z 시계열.
- `corridor_compare.py`: 산포·복도 마스크를 비발산 런으로만 계산하도록 수정(divergence.json 사용).
### 계획과 달라진 점 / 원인
- **2ndfloor는 모든 조건이 실패**(FAST-LIO2 5/5 발산 동일, LIVO2 both 2/5·left 2/5·right 3/5 발산). 발산 런 좌표가 수 km~수십 km라
  기존 그림(plot.py, traj_xy, spread_time)과 평균 기반 지표가 쓸모없어짐 → 발산 시각 기준 분석으로 바꿈.
- 루프 분할(1→2회차 겹침 오차)이 대부분 불가능(nan) → mainlab 주 지표를 그대로 못 씀. 대신 발산 여부·발산 시각·첫 |z|>1 m 시각·비발산 런 간 편차를 씀.
- 복도 마스크는 서로 모양이 다른 비발산 3런의 중앙값 궤적으로 만들 수밖에 없어서 신뢰도 낮다고 명시.
### 예상과 다른 결과
- 단일 카메라 런은 발산 전 드롭률 0%인데도 발산 → 드롭 원인설 지지되지 않음(2ndfloor).
- **both 모드 드롭 급증이 두 bag 모두 재생 후 ≈140 s에 시작**(2ndfloor는 240 s에 끝남). 이미 발산한 both_1도 같은 모양 → 추정 결과와 무관한 입력/실행 쪽 현상.
  140 s 전후로 LIO 사이클 수 780→450 /20 s, LIO 처리 6.4→10 ms, old 드롭이 도착 2 ms 만에 발생, 데이터 지연 0.08→0.14 s.
  - 가설 1 (두 카메라 위상 겹침): bag 타임스탬프로 확인 → 위상차 전 구간 ≈15 ms 일정 → **기각**.
  - 가설 2 (단일 30~40 GB mcap 읽기가 페이지 캐시 23 GB 한계): 240 s에 정상화되는 것과 재생 벽시계 정상(295.9 s)을 설명 못 해 약함.
  - 가설 3 (녹화 시 이미지/LiDAR 수신 지연 변화): bag의 log_time − header.stamp를 토픽별로 봐야 함. 수십 GB 전체 읽기라
    **실행 중 타이밍 간섭 금지 원칙** 때문에 모든 배치 런 종료 후 수행하기로 미룸.
- 2ndfloor 드롭률 28%는 mainlab 21%보다 높지만 차이는 거의 고드롭 구간 길이(100 s vs ≈40 s) 때문. 처리 시간은 두 시퀀스가 같음.

## Phase 5 (06:57~07:34 런, 07:34~ 분석)
### 계획
- mainlab both_drop20 / both_drop50 × 5 (forced_drop_ratio 0.2 / 0.5, seed = 회차) → 실제 총 드롭률 x축 그래프, `results/drop_ablation.md`.
### 실제로 한 것
- 10런 모두 complete. `analyze_drop_ablation.py`의 세로축을 끝점 drift → 루프 자기 일관성(겹침 p90/median, 끝점→1회차, z 최대) + 5회 편차 + 기준 평균까지 RMS로 바꿈(시작~끝은 참고 열).
- 추가로 "기준 평균 궤적에서 처음 1 m/3 m 벗어나는 시각"을 계산해 갈라짐 위치를 확인.
### 계획과 달라진 점 / 원인
- 지표 변경: mainlab bag이 출발점에서 끝나지 않는 문제(Phase 3 준비 절) 때문. 시작~끝 지표만 보면 드롭이 늘수록 '좋아지는'(19.6→14.1→12.8 m, ρ=−0.61) 잘못된 결론이 나옴 — 기록으로 남김.
- drop50_3은 루프가 닫히지 않아 겹침 오차 nan → 표에 "실패"로 표시하고 평균은 n=4(과소평가)라고 명시.
### 예상과 다른 결과
- 인위 드롭이 자연 드롭을 줄임(21.1 → 17.7 → 15.8%). 총 드롭률은 파라미터만큼 늘지 않음.
- 인위 드롭 런의 갈라짐은 Phase 3의 T≈62 s / 155 s 위치에 몰림 → 드롭은 민감 지점에서 갈라질 확률을 높이는 방식으로 작용.
- 결론: 드롭률 증가 → 일관성 악화는 **지지됨**(ρ≈0.7~0.8, p<0.01). 단 자연 드롭 21%를 없앴을 때 좋아진다는 것은 이 실험으로 알 수 없음.

## 추가 실험 준비 (07:45경, diag 런 진행 중 — 빌드 없음)
### 계획 (원래 메모)
- MP 끈 빌드(-DMP_PROC_NUM=1, MP_EN 없음)로 다시 빌드해 left ×3 결정성 시험 → 원래 빌드로 복구.
### 실제로 한 것 / 달라진 점과 이유
- **재빌드 대신 환경변수 `OMP_THREAD_LIMIT=1`(+`OMP_NUM_THREADS=1`)** 사용. OpenMP 규격상 thread-limit은 코드의
  `omp_set_num_threads(MP_PROC_NUM)`보다 우선하는 상한이라, 병렬 구간(voxel_map.cpp:689 LIO 잔차, vio.cpp:1557 VIO reduction)이 1스레드로 돈다.
  이유: 빌드 산출물을 바꿨다가 복구하는 위험(복구 실패 시 이후 실험 전체 오염)과 실행 중 빌드 금지 원칙을 피함. yaml도 기본값과 동일.
- `run_batch.py`에 조건 접미사 `_nomp` 추가(조건 해석 전에 떼어내고 env만 설정; 기존 조건 동작 변화 없음 — 실행 중인 run_all의 다음 run_batch 호출에도 안전하게 하위 호환).
- `scripts/run_extra.sh`: run_all 종료("run_all finished")를 기다렸다가 mainlab_left_nomp_1~3 → `scripts/bag_latency.py`(bag 수신 지연, 읽기 전용) 순차 실행.
  타이밍에 민감한 런을 먼저, 디스크를 많이 읽는 스캔을 나중에 둠.
- Phase 7 분석 스크립트 수정: LIVO는 이미지마다 스캔을 잘라 LIO 업데이트하므로 업데이트당 λt가 점 수(n_eff, 수백~수천)에 비례해 출렁임
  (첫 diag 런에서 원래 정의로 퇴화 구간 1458개, 시간 25%). → 점당 λt/n_eff의 1 s 중앙값으로 판단, 임계 0.5×중앙값. 카메라 보완 비율도 1 s 합 비율로.

## 추가 실험 1 결과 — OpenMP 1스레드 결정성 시험 (08:18~08:29)
- mainlab_left_nomp_1~3 (OMP_THREAD_LIMIT=1, run_info.json에 env 기록). LIO 평균 8.79 → 7.09 ms로 바뀌어 설정이 적용된 것은 확인.
- **결과: 여전히 비결정적.** 런 쌍별로 궤적이 처음 1 mm 이상 달라지는 시각 15~16 s, 10 cm 58~60 s, 1 m 61~64 s — MP 켠 left 런(15.7~17 s / 60~61 s / 61.5~63.6 s)과 같은 양상.
- → "OpenMP reduction 합산 순서가 원인"이라는 가설은 **지지되지 않음**. 남은 후보: ROS 콜백 도착 타이밍(LIO 업데이트 시점의 버퍼 내용 — horizon = min(lidar, imu 최신)에 따라 IMU 적분 구간·스캔 분할이 바뀜). 미검증.
- 해석: mm 수준의 작은 차이가 15 s부터 생기고, LIO 정보량이 약해지는 55~66 s 창(λt/n 42 vs 평소 64, cond_t 11 vs 5~7 — Phase 7)에서 m 수준으로 증폭된다.
- 결정적 비교(로깅 on/off 비트 비교)가 불가능해졌으므로, 로깅 영향은 통계로 확인하기로 함 → 추가 실험 2.

## Phase 6/7 중 발견한 문제
- **diag 로깅 버그(내 코드)**: vio.cpp `computeJacobianAndUpdateEKF`에서 `total_points==0` 조기 return이 per-frame 리셋보다 앞에 있어,
  시각점 0개 프레임이 직전 프레임의 정보행렬을 valid=1로 다시 기록함. → 분석에서 n_points==0 행을 무효 처리(이미 수집한 데이터로 충분), 소스는 리셋을 return 앞으로 옮김.
  추정 동작에는 영향 없음(기록용 변수만). 재빌드는 모든 실행이 끝난 뒤.
- **로깅 on/off 비교에서 의심 신호**: 드롭률(21.1 vs 21.3%)·처리 시간(8.58 vs 8.64 ms)은 같지만 mainlab 겹침 p90이 both 5/5 ≤1.4 m, both_diag 3/5 > 2.9 m(17.0, 6.79, 2.95).
  0/5 vs 3/5 Fisher p≈0.17로 유의하지 않음. 코드상 복사만 하므로 계산 결과는 입력이 같으면 같아야 하고, 차이는 타이밍 경로로만 가능.
  → mainlab both 6~10, both_diag 6~10을 추가로 번갈아 실행해 n=10 대 10으로 확인(`scripts/run_extra2.sh`, bag 지연 스캔 뒤).

## 추가 실험 3 결과 — bag 녹화 수신 지연 (08:30, `scripts/bag_latency.py`, 읽기 전용)
- 두 bag 모두 전 구간에서 log_time − header.stamp가 일정: 이미지 ≈44 ms, LiDAR ≈51.6 ms, IMU 0.4 ms, 20 s당 메시지 수도 일정(이미지 600, LiDAR 400, IMU 4000).
- → "녹화 당시 지연 변화가 140 s 드롭 급증의 원인" 가설(Phase 4 가설 3) **기각**. 데이터 자체의 시간 성질은 140 s 전후로 같다.
- 남은 설명: 재생/실행 쪽(재생 시작 후 경과 시간에 묶인 현상). 단서: 140 s 이후 old 드롭이 도착 2 ms 만에 일어남 → 같은 카메라 프레임이 몰려 도착(burst)했을 가능성.
  단일 카메라에는 없는 이유는 미해명.
- 분리 실험 추가(`scripts/run_extra3.sh`): `run_batch.py`에 `_offNN` 조건 접미사(= `ros2 bag play --start-offset NN`, yaml 동일) 추가.
  mainlab both_off60 ×2, 2ndfloor both_off60 ×1. bag 시각에 묶이면 재생 80 s에, 재생 경과 시간에 묶이면 재생 140 s에 급증해야 한다.

## 추가 실험 2 결과 — 로깅 on/off (08:30~09:07)
- mainlab both 6~10, both_diag 6~10 번갈아 실행(10/10 complete).
- n=10 대 10: 드롭률 20.7 vs 21.4%, 사이클 8.48 vs 8.60 ms, 겹침 p90 중앙값 0.87 vs 2.60 m, MWU p=0.47, > 2 m 런 2/10 vs 6/10(Fisher p=0.17) → **유의한 차이 없음**.
- **예상과 다른 결과**: 기준 both 6~10회가 1~5회보다 나쁨(겹침 p90 중앙값 1.99 vs 0.42 m). 처음 5회가 좋은 쪽으로 치우쳐 있었다.
  → Phase 3("both 압도적으로 일관")과 Phase 5(추세 p≤0.003)의 강도가 낮아짐. 각 문서에 갱신 절을 덧붙였다(원래 수치는 기록으로 유지).
  Phase 5 갱신: 겹침 p90 ρ=0.43 p=0.067(루프 실패 런을 최악으로 넣으면 ρ=0.48 p=0.031), 편차 ρ=0.60 p=0.005.

## 추가 실험 4 결과 — 재생 시작 위치 (09:07~09:17)
- mainlab_both_off60_1·2, 2ndfloor_both_off60_1 (`ros2 bag play --start-offset 60`).
- mainlab: bag 140~180 s(= 재생 80~120 s)에서 드롭 7~9%, 급증 없음. 2ndfloor: 급증이 bag 180~200 s(= 재생 120~140 s)에 시작해 끝까지.
- → 드롭 급증은 **재생 경과 시간 ≈120~140 s**에 묶인 실행 환경 현상. bag 데이터의 성질이 아님. 메커니즘은 미확인(SUMMARY 5절에 다음 실험).
- 이유: 결론(자연 드롭의 절반은 실험 환경 산물)이 질문 1·4의 답을 바꾸므로 3런(≈10분)을 들여 확인할 가치가 있다고 판단.

## Phase 8 (09:20~)
- vio.cpp diag 리셋 수정 재빌드(fast_livo, 16 s, 에러 0) 후 FASTLIVO2 커밋 5dc7634. 수정 후 diag 런으로 검증은 하지 않음(기록 변수만 바뀜; 이미 수집한 데이터는 분석에서 n_points==0 무효 처리).
- `results/SUMMARY.md` 작성. 5개 질문 답 + 확신도/다음 실험 표.
- git 정리: Phase 4 prep 커밋이 진행 중이던 2ndfloor_both_2 일부 파일을 담고 있었고 이후 커밋은 sequences/를 빼서 저장소 상태가 어긋나 있었음(파일 자체는 05:40 이후 변경 없음 확인).
  run.log(합계 ~2 GB)는 .gitignore에 추가하고 추적만 해제(디스크에 그대로), 나머지 런 결과(csv/txt/json/yaml, 186 MB)는 커밋 d60221b.
