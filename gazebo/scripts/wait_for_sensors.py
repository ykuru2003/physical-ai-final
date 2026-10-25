"""Wait for actual ROS odometry and lidar messages while Gazebo starts."""
import json
import sys
import time
from pathlib import Path

import rclpy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan, Imu
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


def main():
    rclpy.init()
    node = Node('wait_for_sensors')
    received = {}
    started = time.monotonic()
    subscriptions = []
    for topic, message_type in (('/odom', Odometry), ('/scan', LaserScan), ('/robot/imu', Imu)):
        subscriptions.append(node.create_subscription(
            message_type, topic,
            lambda msg, name=topic: received.__setitem__(name, time.monotonic()),
            qos_profile_sensor_data))
    report = {'result': 'FAIL'}
    try:
        last_log = 0.0
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
            now = time.monotonic()
            missing = [name for name in ('/odom', '/scan', '/robot/imu')
                       if now - received.get(name, -float('inf')) > 1.0]
            if not missing:
                report = {'result': 'PASS', 'elapsed_seconds': now-started,
                          'topics': sorted(received)}
                print('READY: fresh /odom, /scan and /robot/imu received', flush=True)
                return 0
            if now-started >= 120:
                report['missing_or_stale_topics'] = missing
                print('ERROR: startup timed out; missing/stale: '+', '.join(missing), flush=True)
                return 1
            if now-last_log >= 5:
                print(f'WAIT {now-started:.0f}s: '+', '.join(missing), flush=True)
                last_log = now
        report['error'] = 'ROS shutdown while waiting'
        return 1
    except KeyboardInterrupt:
        report['error'] = 'Interrupted'
        return 130
    finally:
        output = Path('/workspace/outputs/sensor-readiness.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
