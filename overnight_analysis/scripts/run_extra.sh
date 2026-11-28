#!/bin/bash
# 계획 런(run_all) 종료 후 추가 실험: (1) OpenMP 1스레드 결정성 시험 mainlab left_nomp ×3, (2) bag 수신 지연 스캔
cd ~/dlr_ws
L=sequences/_batch_logs
until grep -q "run_all finished" $L/run_all.log; do sleep 30; done
echo "[$(date '+%F %T')] extra start" >> $L/run_all.log
bash scripts/run_batch.sh --seq mainlab --cond left_nomp --runs 1-3 >> $L/extra_nomp.log 2>&1
echo "[$(date '+%F %T')] extra nomp done" >> $L/run_all.log
source /opt/ros/jazzy/setup.bash
python3 scripts/bag_latency.py mainlab 2ndfloor > $L/extra_latency.log 2>&1
echo "[$(date '+%F %T')] extra latency done" >> $L/run_all.log
