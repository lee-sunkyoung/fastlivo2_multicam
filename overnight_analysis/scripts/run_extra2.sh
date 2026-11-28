#!/bin/bash
# 로깅 on/off 영향 확인용 추가 런: mainlab both 6~10, both_diag 6~10 (run_major로 번갈아). bag 지연 스캔 종료 후 시작.
cd ~/dlr_ws
L=sequences/_batch_logs
until grep -q "extra latency done" $L/run_all.log; do sleep 20; done
echo "[$(date '+%F %T')] extra2 start (both/both_diag 6-10)" >> $L/run_all.log
bash scripts/run_batch.sh --seq mainlab --cond both both_diag --runs 6-10 >> $L/extra2_onoff.log 2>&1
echo "[$(date '+%F %T')] extra2 done" >> $L/run_all.log
