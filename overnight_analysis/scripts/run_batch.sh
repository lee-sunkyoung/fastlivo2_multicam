#!/usr/bin/env bash
# ROS 환경을 source 한 뒤 run_batch.py 실행. 인자는 그대로 전달.
# 예: scripts/run_batch.sh --seq mainlab --cond both left right fastlio --runs 1-5
# (set -u 사용 안 함: ROS setup.bash가 unbound 변수를 참조함)
source /opt/ros/jazzy/setup.bash
source "$HOME/dlr_ws/install/setup.bash"
cd "$HOME/dlr_ws"
exec python3 -u "$HOME/dlr_ws/scripts/run_batch.py" "$@"
