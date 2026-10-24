"""Verify ROS -> Gazebo motion and Gazebo -> ROS odometry, lidar and clock."""

import json
import math
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan


def main():
    rclpy.init()
    node = Node("check_environment")
    messages = {}
    subscriptions = []
    for topic, message_type in [("/odom", Odometry), ("/scan", LaserScan), ("/clock", Clock)]:
        subscriptions.append(node.create_subscription(
            message_type, topic,
            lambda message, name=topic: messages.__setitem__(name, message),
            qos_profile_sensor_data,
        ))
    publisher = node.create_publisher(Twist, "/cmd_vel", 10)
    result = {"result": "FAIL"}

    def spin_for(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)

    try:
        deadline = time.monotonic() + 90
        while len(messages) < 3 or publisher.get_subscription_count() == 0:
            rclpy.spin_once(node, timeout_sec=0.2)
            if time.monotonic() > deadline:
                missing = sorted({"/odom", "/scan", "/clock"} - messages.keys())
                raise RuntimeError(f"ROS bridge not ready; missing topics: {missing}")
        start = messages["/odom"].pose.pose.position
        clock = messages["/clock"].clock
        start_time = clock.sec + clock.nanosec / 1e9
        scan = messages["/scan"]
        if not scan.ranges or not any(math.isfinite(value) for value in scan.ranges):
            raise RuntimeError("Lidar has no finite obstacle measurements")
        command = Twist()
        command.linear.x = 0.15
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            publisher.publish(command)
            spin_for(0.1)
        publisher.publish(Twist())
        spin_for(1)
        end = messages["/odom"].pose.pose.position
        distance = math.hypot(end.x - start.x, end.y - start.y)
        clock = messages["/clock"].clock
        sim_seconds = clock.sec + clock.nanosec / 1e9 - start_time
        result.update(distance_m=distance, simulation_seconds=sim_seconds, lidar_samples=len(scan.ranges))
        if distance < 0.02 or sim_seconds <= 0:
            raise RuntimeError(f"Robot did not move sufficiently: {distance:.3f} m")
        result["result"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        for _ in range(5):
            publisher.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.1)
        result["checked_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        output = Path("/workspace/outputs/environment-check.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
