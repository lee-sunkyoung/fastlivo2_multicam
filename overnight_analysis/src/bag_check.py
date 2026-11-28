#!/usr/bin/env python3
"""
bag 안에서 토픽 메시지가 header.stamp 기준으로 순서가 뒤바뀐 곳을 찾는다.
(bag 기록 순서 = 재생 순서)

사용:
  python3 check_bag_order.py <bag_dir> /cam0/image_raw [/cam1/image_raw ...]
"""
import sys

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def stamp_sec(msg):
    s = msg.header.stamp
    return s.sec + s.nanosec * 1e-9


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    bag, topics = sys.argv[1], sys.argv[2:]

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    for tp in topics:
        if tp not in types:
            print(f'[!] {tp} 없음. 있는 토픽: {list(types)}')
            sys.exit(1)
    reader.set_filter(rosbag2_py.StorageFilter(topics=topics))
    cls = {tp: get_message(types[tp]) for tp in topics}

    t0 = None
    last = {tp: None for tp in topics}      # 직전 (stamp, bag_time)
    n = {tp: 0 for tp in topics}
    swaps = {tp: [] for tp in topics}
    delay = {tp: [] for tp in topics}       # bag 기록시간 - header.stamp

    while reader.has_next():
        tp, data, bag_ns = reader.read_next()
        msg = deserialize_message(data, cls[tp])
        st = stamp_sec(msg)
        bt = bag_ns * 1e-9
        if t0 is None:
            t0 = st
        n[tp] += 1
        delay[tp].append(bt - st)
        if last[tp] is not None and st < last[tp][0]:
            swaps[tp].append((st - t0, last[tp][0] - st,
                              delay[tp][-1], delay[tp][-2]))
        last[tp] = (st, bt)

    for tp in topics:
        d = sorted(delay[tp])
        print(f'\n=== {tp}  msgs={n[tp]}')
        if d:
            print(f'  기록지연(bag시간-stamp) ms: '
                  f'median={1000*d[len(d)//2]:.1f}  max={1000*d[-1]:.1f}')
        print(f'  순서 뒤바뀜: {len(swaps[tp])}건')
        for rel, back, dl, dprev in swaps[tp]:
            print(f'   +{rel:8.2f}s  이전보다 {1000*back:6.1f}ms 과거 stamp '
                  f'(이 msg 지연 {1000*dl:.1f}ms, 직전 msg 지연 {1000*dprev:.1f}ms)')


if __name__ == '__main__':
    main()

