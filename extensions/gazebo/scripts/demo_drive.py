"""Short motion check only: this is not an AI controller."""

import time

import rclpy
from geometry_msgs.msg import Twist


def main():
    rclpy.init()
    node = rclpy.create_node("demo_drive")
    publisher = node.create_publisher(Twist, "/cmd_vel", 10)
    try:
        deadline = time.monotonic() + 15
        while publisher.get_subscription_count() == 0:
            rclpy.spin_once(node, timeout_sec=0.1)
            if time.monotonic() > deadline:
                raise RuntimeError("No ROS-Gazebo bridge subscriber on /cmd_vel")
        for seconds, speed, turn in [(3, 0.15, 0.0), (2, 0.0, 0.5)]:
            command = Twist()
            command.linear.x, command.angular.z = speed, turn
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                publisher.publish(command)
                rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        for _ in range(5):
            publisher.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.1)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
