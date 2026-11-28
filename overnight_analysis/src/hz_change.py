#!/usr/bin/env python3
"""
/livox/lidar (livox_ros_driver2/CustomMsg, 예: 20Hz) 를 받아
점별 타임스탬프 기준으로 1/rate 초 창으로 다시 잘라 /livox/lidar_hz 로 발행.

실행 예:
  ros2 bag play <bag> --clock
  python3 lidar_resplit.py --ros-args -p use_sim_time:=true -p rate:=30.0
"""
import bisect

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from livox_ros_driver2.msg import CustomMsg


class LidarResplit(Node):
    def __init__(self):
        super().__init__('lidar_resplit')
        self.declare_parameter('input_topic', '/livox/lidar')
        self.declare_parameter('output_topic', '/livox/lidar_hz')
        self.declare_parameter('rate', 30.0)

        in_topic = self.get_parameter('input_topic').value
        out_topic = self.get_parameter('output_topic').value
        rate = float(self.get_parameter('rate').value)
        self.period_ns = int(round(1e9 / rate))

        self.buf_t = []        # 각 점의 절대시간 [ns]
        self.buf_p = []        # CustomPoint
        self.win_start = None  # 현재 창 시작 [ns]
        self.last_tb = None
        self.frame_id = ''
        self.lidar_id = 0
        self.n_msgs = 0
        self.dropped = 0

        qos = QoSProfile(depth=100,
                         reliability=ReliabilityPolicy.RELIABLE,
                         history=HistoryPolicy.KEEP_LAST)
        self.pub = self.create_publisher(CustomMsg, out_topic, qos)
        self.sub = self.create_subscription(CustomMsg, in_topic, self.cb, qos)
        self.get_logger().info(
            f'{in_topic} -> {out_topic}, {rate:.1f} Hz (period {self.period_ns} ns)')

    def reset(self):
        self.buf_t.clear()
        self.buf_p.clear()
        self.win_start = None

    def cb(self, msg: CustomMsg):
        tb = msg.timebase
        if tb == 0:  # timebase가 비어있으면 header stamp 사용
            tb = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec

        # bag 루프/되감기 등으로 시간이 뒤로 가면 초기화
        if self.last_tb is not None and tb < self.last_tb:
            self.get_logger().warn('time jumped backwards, resetting buffer')
            self.reset()
        self.last_tb = tb
        self.frame_id = msg.header.frame_id
        self.lidar_id = msg.lidar_id

        new_t = [tb + p.offset_time for p in msg.points]
        new_p = list(msg.points)

        # 디버그: 메시지 시간 범위 (처음 몇 개만)
        if self.n_msgs < 5 and new_t:
            self.get_logger().info(
                f'msg tb={tb} pts={len(new_t)} '
                f'offset[min,max]=[{min(new_t) - tb}, {max(new_t) - tb}] ns')
        self.n_msgs += 1

        # 이미 발행한 창보다 이전 시간의 점은 버림 (메시지 간 시간 겹침)
        if self.win_start is not None:
            keep = [i for i, t in enumerate(new_t) if t >= self.win_start]
            n_drop = len(new_t) - len(keep)
            if n_drop:
                self.dropped += n_drop
                self.get_logger().warn(
                    f'dropped {n_drop} late points (total {self.dropped})',
                    throttle_duration_sec=2.0)
                new_t = [new_t[i] for i in keep]
                new_p = [new_p[i] for i in keep]
        # 정렬 보장 (대부분 이미 정렬돼 있음)
        if any(new_t[i] > new_t[i + 1] for i in range(len(new_t) - 1)):
            pairs = sorted(zip(new_t, new_p), key=lambda x: x[0])
            new_t = [a for a, _ in pairs]
            new_p = [b for _, b in pairs]
        if self.buf_t and new_t and new_t[0] < self.buf_t[-1]:
            pairs = sorted(zip(self.buf_t + new_t, self.buf_p + new_p),
                           key=lambda x: x[0])
            self.buf_t = [a for a, _ in pairs]
            self.buf_p = [b for _, b in pairs]
        else:
            self.buf_t.extend(new_t)
            self.buf_p.extend(new_p)

        if not self.buf_t:
            return
        if self.win_start is None:
            self.win_start = self.buf_t[0]
        # 1초 넘는 공백(bag 일시정지 등)이면 창 시작을 건너뜀
        if self.buf_t[0] - self.win_start > 1_000_000_000:
            self.win_start = self.buf_t[0]

        # 버퍼가 창 끝을 넘어선 만큼 창 단위로 잘라서 발행
        latest = self.buf_t[-1]
        while self.win_start + self.period_ns <= latest:
            win_end = self.win_start + self.period_ns
            idx = bisect.bisect_left(self.buf_t, win_end)
            if idx > 0:
                self.publish_window(self.win_start,
                                    self.buf_t[:idx], self.buf_p[:idx])
                del self.buf_t[:idx]
                del self.buf_p[:idx]
            self.win_start = win_end

    def publish_window(self, t0, ts, pts):
        out = CustomMsg()
        out.header.frame_id = self.frame_id
        out.header.stamp.sec = t0 // 1_000_000_000
        out.header.stamp.nanosec = t0 % 1_000_000_000
        out.timebase = t0
        out.lidar_id = self.lidar_id
        for t, p in zip(ts, pts):
            p.offset_time = max(0, min(int(t - t0), 0xFFFFFFFF))
        out.points = pts
        out.point_num = len(pts)
        self.pub.publish(out)


def main():
    rclpy.init()
    node = LidarResplit()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
