#!/bin/bash
# 드롭 급증(재생 ≈140 s) 원인 분리: bag을 60 s 지점부터 재생. bag 시각에 묶이면 재생 80 s에, 재생 경과에 묶이면 재생 140 s에 급증.
cd ~/dlr_ws
L=sequences/_batch_logs
until grep -q "extra2 done" $L/run_all.log; do sleep 20; done
echo "[$(date '+%F %T')] extra3 start (off60)" >> $L/run_all.log
bash scripts/run_batch.sh --seq mainlab --cond both_off60 --runs 1-2 >> $L/extra3_offset.log 2>&1
bash scripts/run_batch.sh --seq 2ndfloor --cond both_off60 --runs 1 >> $L/extra3_offset.log 2>&1
echo "[$(date '+%F %T')] extra3 done" >> $L/run_all.log
