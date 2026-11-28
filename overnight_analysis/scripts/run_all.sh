#!/usr/bin/env bash
# 전체 런 순차 실행 (한 번에 하나). 중단 후 다시 실행하면 완료된 seq_name은 run_batch가 건너뛴다.
# 출력은 sequences/_batch_logs/ 아래 파일로만.
cd "$HOME/dlr_ws"
L=sequences/_batch_logs
mkdir -p $L
echo "[$(date '+%F %T')] run_all start" >> $L/run_all.log
scripts/run_batch.sh --seq mainlab  --cond both left right fastlio --runs 1-5 >> $L/phase2_mainlab.log 2>&1
echo "[$(date '+%F %T')] phase2 mainlab done" >> $L/run_all.log
scripts/run_batch.sh --seq 2ndfloor --cond both left right fastlio --runs 1-5 >> $L/phase4_2ndfloor.log 2>&1
echo "[$(date '+%F %T')] phase4 2ndfloor done" >> $L/run_all.log
scripts/run_batch.sh --seq mainlab  --cond both_drop20 both_drop50 --runs 1-5 >> $L/phase5_drop.log 2>&1
echo "[$(date '+%F %T')] phase5 drop done" >> $L/run_all.log
scripts/run_batch.sh --seq mainlab  --cond both_diag --runs 1-5 >> $L/phase7_diag.log 2>&1
scripts/run_batch.sh --seq 2ndfloor --cond both_diag --runs 1-5 >> $L/phase7_diag.log 2>&1
echo "[$(date '+%F %T')] phase7 diag done" >> $L/run_all.log
echo "[$(date '+%F %T')] run_all finished" >> $L/run_all.log
