# 밤샘 작업: FAST-LIVO2 멀티카메라 프레임 드롭 영향 분석 + 퇴화 진단

## 0. 작업 원칙 (가장 중요)
- 나는 자고 있어서 질문에 답할 수 없다. 모호한 부분은 가장 합리적인 해석을 골라 진행하고,
  그 선택과 이유를 ~/dlr_ws/probsolv.md에 기록한다.
- probsolv.md에는 단계마다 "계획 / 실제로 한 것 / 계획과 달라진 점과 원인 분석 / 그렇게 선택한 이유"를 적는다.
  에러, 예상과 다른 결과, 우회한 방법도 전부 여기에 적는다.
- 어떤 단계가 실패해도 전체를 멈추지 말고, 원인을 기록한 뒤 그 단계에 의존하지 않는 다음 단계로 넘어간다.
- 단계(Phase)가 끝날 때마다 git commit (메시지에 Phase 번호).
- 실행은 반드시 한 번에 하나씩 순차로 한다. 동시 실행 금지 (타이밍이 드롭률에 영향을 줌).
  실행 중에는 다른 무거운 작업(빌드 등)을 하지 않는다.
- 결과를 원하는 결론에 맞추지 않는다. 가설이 지지되지 않으면 "지지되지 않음"이라고 쓰고 근거를 남긴다.
- 원본 bag 파일(~/dlr_ros2_bag)은 절대 수정하거나 삭제하지 않는다.
- 새로 넣는 로깅 기능은 yaml 파라미터로 on/off할 수 있게 하고, 기본값에서 알고리즘 동작이 바뀌면 안 된다.
- ros2 launch / bag play 출력은 절대 화면(대화)에 그대로 출력하지 말고 파일로 리다이렉트한다
  (예: > sequences/<seq_name>/run.log 2>&1). 확인할 때는 img_stats 줄이나 tail -n 20 등 필요한 부분만 본다.
- 실행 대기는 짧은 간격 폴링으로 출력을 남기지 말고, 스크립트 안에서 끝날 때까지 기다리게 한다.


## 환경
- 워크스페이스: ~/dlr_ws, 실행: `ros2 launch fast_livo mapping_justin.launch.py`
- bag: ~/dlr_ros2_bag/ros2_bag_livo_2_cams_main_lab_2_loops/ , ~/dlr_ros2_bag/ros2_bag_livo_2_cams_2nd_floor/
- 재생: `ros2 bag play <bag> --rate 1.0`
- 실행마다 자동 저장되는 것:
  - Log/ 아래 드롭 기록 csv (현재 이름: selected_YYYYMMDD_HHMMSS.csv)
  - Log/result/ 아래 path (yaml의 evo.seq_name 이름으로 저장)
  - Log/PCD/ 아래 pcd
- 왼쪽만/오른쪽만/양쪽 설정과 FAST-LIO2 실행 방법은 이전 실험(~/pcd_save/{both,left,right}_path*, ~/pcd_save/fastlio2/)을
  어떻게 만들었는지 코드·yaml·launch 파일을 보고 파악한다. 파악한 방법을 probsolv.md에 적는다. 초기 실행시 probsolv.md가 없다면 ~/dlr_ws/src/ 에 생성후 진행한다.

## 이어서 하기 (중단 대비)
- ~/dlr_ws/PROGRESS.md에 Phase별 체크리스트와 완료된 런 목록을 유지하고, 런이 하나 끝날 때마다 갱신한다.
- 작업을 다시 시작하면 먼저 PROGRESS.md와 probsolv.md를 읽고, sequences/ 아래에 결과 파일(path, csv, pcd)이
  다 있는 런은 건너뛰고 이어서 진행한다. 결과가 일부만 있는 런은 지우지 말고 이름 끝에 _incomplete를 붙여 옮긴 뒤 다시 실행한다.
- 배치 실행 스크립트도 이미 완료된 seq_name은 자동으로 건너뛰게 만든다.

## Phase 1. 저장 방식 수정
1. 드롭 csv 파일 이름도 yaml의 seq_name과 같게 저장되도록 코드를 수정한다.
2. 런마다 seq_name을 `<시퀀스>_<조건>_<회차>` 형식으로 바꿔 가며 실행하는 스크립트를 만든다
   (~/dlr_ws/scripts/run_batch.sh 또는 .py).
   - 시퀀스 이름: mainlab, 2ndfloor
   - 조건: both, left, right, fastlio (Phase 5에서는 both_drop20, both_drop50)
   - 예: mainlab_both_1, mainlab_left_3, 2ndfloor_fastlio_5, mainlab_both_drop50_2
3. 한 런의 절차: yaml에 seq_name 설정 → launch → 준비될 때까지 대기 → bag 1배속 재생 → 재생이 끝나면 몇 초 대기
   → launch에 SIGINT를 보내 정상 종료시킴(저장이 끝날 때까지 대기) → 결과 이동.
4. 런이 끝나면 ~/dlr_ws/sequences/<seq_name>/ 폴더를 만들고 그 런의 path, 드롭 csv, pcd, 실행 로그(img_stats 포함)를 옮긴다.
   FAST-LIO는 path만 있어도 된다 (드롭 csv 없음).
5. 먼저 짧게 1런만 테스트해서 파일 4종이 제대로 옮겨지는지 확인한 뒤 본 실행에 들어간다.

## Phase 2. main_lab 데이터셋 (20런)
- mainlab_both / left / right / fastlio × 각 5회.
- 런마다 로그의 img_stats(recv, used, skipped(old), overflow 등)와 프레임당 처리 시간을 csv로 정리해 둔다. (fastlio 제외)
  처리 시간 로그가 없으면 최소한의 타이밍 로그를 추가한다 (기본 동작은 그대로 유지).

## Phase 3. 분석 (main_lab)
1. ~/dlr_ws/src/plot.py의 경로를 수정해서 sequences/ 아래 런들을 조건별 그룹으로 불러와 띄울 수 있게 한다.
   그림은 png로도 저장한다 (results/ 폴더).
2. 정량 지표: 조건별 5회의 끝점 drift(루프의 시작~끝 위치 차이), 5회 궤적 간 편차(평균 궤적 대비 RMS),
   가능하면 복도 축 방향과 수직 방향으로 나눠서.
3. scripts/compare_selected.py를 수정해서 LIVO2 런들(both/left/right 각각)의 5회 드롭 csv를 비교한다:
   - 5회 모두 같은 프레임(타임스탬프)이 드롭됐는지, 런마다 드롭된 프레임이 다른지 (일치율, 런 간 Jaccard 등)
   - 드롭이 특정 구간에 몰리는지 (시간축 히스토그램)
   - skipped(old)의 원인 단서: 가능하면 드롭 시점의 이미지 지연 정도 기록
4. 결과를 ~/dlr_ws/results/mainlab_analysis.md에 정리한다 (그림 경로 포함).

## Phase 4. 2nd_floor (20런 + 분석)
- Phase 2~3을 2ndfloor로 똑같이 반복한다. 토픽 이름이 main_lab과 다르면 맞춰서 처리하고 기록한다.
- 결과: ~/dlr_ws/results/2ndfloor_analysis.md
- 두 bag 비교: ~/dlr_ws/results/mainlab_vs_2ndfloor.md
  - 같은 조건(both/left/right)에서 드롭률, 드롭 유형(old/overflow), 프레임당 처리 시간, 끝점 drift, 5회 편차를 표로 비교
  - 2층 복도 구간에서 드롭이 몰리거나 오차가 커지는지

## Phase 5. 인위적 드롭 실험 (main_lab, 양쪽 카메라)
1. yaml 파라미터 forced_drop_ratio(기본 0.0)를 추가한다. 원래라면 사용됐을 이미지 중 이 비율만큼 추가로 버린다.
   - 카메라별로 따로 적용한다. 드롭 여부는 난수 호출 순서가 아니라 hash(이미지 타임스탬프, 카메라 id, 런 회차)로 결정해서 재현 가능하게 한다.
   - 실제 총 드롭률(자연 드롭 + 인위적 드롭)을 로그와 csv에 기록한다.
2. mainlab_both_drop20 (forced_drop_ratio=0.2) × 5회, mainlab_both_drop50 (=0.5) × 5회를 실행한다.
3. 기존 mainlab_both(인위적 드롭 0) → drop20 → drop50 순서로 실제 총 드롭률, 끝점 drift, 5회 편차를 비교한다.
   드롭률이 커질수록 오차와 편차가 같이 커지는지 그래프(가로축: 실제 총 드롭률)로 보여 준다.
4. 결과: ~/dlr_ws/results/drop_ablation.md
   - 결론은 데이터대로 쓴다. 단조 증가하면 "드롭이 성능에 영향을 준다"는 근거로, 아니면 그렇다고 쓴다.

## Phase 6. T1 퇴화 진단 (코드 수정)
1. FAST-LIVO2의 LIO 업데이트에서 HᵀH(pose 6×6 블록)를 찾아, 매 LIO 업데이트마다 csv로 기록한다:
   timestamp, 6개 고유값, 최소 고유값의 고유벡터,
   병진 3×3 블록과 회전 3×3 블록 각각의 고유값과 최소 고유벡터(단위가 달라서 따로 봄), condition number.
2. 기록 기능은 yaml 파라미터로 on/off (기본 off). 켜도 추정 결과가 바뀌면 안 된다.

## Phase 7. T2 소스별 보완량 (코드 수정 + 실행)
1. VIO 업데이트마다 그 카메라 업데이트의 정보행렬(pose 블록, HᵀR⁻¹H 형태)을 구하고,
   같은 시점의 LIO 최소 병진 고유벡터 v에 투영한 값 vᵀ·H_visᵀH_vis·v를 카메라 id와 함께 csv로 기록한다.
2. mainlab_both, 2ndfloor_both를 T1·T2 로깅을 켜고 각 5회 실행한다
   (seq_name: mainlab_both_diag_N, 2ndfloor_both_diag_N).
3. 그림: 최소 병진 고유값의 시간 그래프, 궤적 위 색 표시, 최소 고유벡터와 복도 축(궤적 진행 방향)의 각도,
   cam0/cam1 보완량의 시간 그래프(퇴화 구간 음영 표시).
4. 결과: ~/dlr_ws/results/degeneracy_analysis.md
   - 복도 구간에서 최소 고유값이 떨어지는지, 그 방향이 복도 축 병진인지
   - 퇴화 구간에서 좌/우 카메라 보완량이 시간에 따라 엇갈리는지, 둘 다 약한지, 둘 다 강한지

## Phase 8. 최종 요약
~/dlr_ws/results/SUMMARY.md에 아래를 정리한다:
1. main_lab에서 드롭이 성능 저하의 원인이라고 볼 수 있는가 (Phase 3, 5 근거)
2. 그 드롭이 2층 복도가 많은 구간에서 문제를 일으키는가 (Phase 4 근거)
3. 복도에서 LiDAR 퇴화가 실제로 생기는가, 카메라가 그 방향을 보완하는가 (Phase 6, 7 근거)
4. 런 간에 드롭되는 프레임이 달라지는가 → run-to-run 편차의 원인 후보인가
5. 각 결론의 확신 정도와, 확신이 낮은 부분은 다음에 무슨 실험이 필요한지
