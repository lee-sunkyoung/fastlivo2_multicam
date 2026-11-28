#!/usr/bin/env python3
"""~/tum.py와 같은 방식(/path 구독 → TUM)으로 FAST-LIO2 궤적을 저장. 출력 경로를 인자로 받는다.
사용: python3 path_to_tum.py <out.txt>
"""
import sys

import rclpy
from nav_msgs.msg import Path
from rclpy.node import Node


class PathToTUM(Node):
    def __init__(self, out):
        super().__init__('path_to_tum')
        self.output = open(out, 'w', buffering=1)
        self.seen = set()
        self.sub = self.create_subscription(Path, '/path', self.callback, 10)

    def callback(self, msg):
        for pose in msg.poses:
            st = pose.header.stamp
            key = (st.sec, st.nanosec)
            if key in self.seen:
                continue
            self.seen.add(key)
            t = st.sec + st.nanosec * 1e-9
            p, q = pose.pose.position, pose.pose.orientation
            self.output.write(f'{t:.9f} {p.x:.9f} {p.y:.9f} {p.z:.9f} {q.x:.9f} {q.y:.9f} {q.z:.9f} {q.w:.9f}\n')


def main():
    rclpy.init()
    node = PathToTUM(sys.argv[1])
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, Exception):
        pass
    finally:
        node.output.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
