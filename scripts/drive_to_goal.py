
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist


class GoalDriver(Node):
    def __init__(self):
        super().__init__("goal_driver")

        # 中継点 → 最終ゴール
        self.waypoints = [(0.0, 1.0), (3.0, 1.0)]
        self.index = 0
        self.pose = None
        self.finished = False
        self.started = time.monotonic()

        self.publisher = self.create_publisher(
            Twist, "/cmd_vel", 10
        )
        self.create_subscription(
            Odometry, "/odom",
            self.on_odom, qos_profile_sensor_data
        )
        self.create_timer(0.1, self.control)

    def on_odom(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(
            2 * (q.w * q.z + q.x * q.y),
            1 - 2 * (q.y**2 + q.z**2)
        )
        self.pose = (p.x, p.y, yaw)

    def control(self):
        if self.finished:
            return

        cmd = Twist()

        if time.monotonic() - self.started > 90:
            print("TIMEOUT: 停止します")
            self.finished = True
            self.publisher.publish(cmd)
            return

        if self.pose is None:
            return

        x, y, yaw = self.pose
        gx, gy = self.waypoints[self.index]

        distance = math.hypot(gx - x, gy - y)

        threshold = 0.18 if self.index == 0 else 0.30

        if distance < threshold:
            if self.index == 0:
                self.index = 1
                print("中継点に到達。ゴールへ向かいます")
            else:
                print("GOAL REACHED!")
                self.finished = True
                self.publisher.publish(Twist())
                return

        gx, gy = self.waypoints[self.index]
        angle = math.atan2(gy - y, gx - x)
        error = math.atan2(
            math.sin(angle - yaw),
            math.cos(angle - yaw)
        )

        cmd.angular.z = max(-1.0, min(1.0, 1.5 * error))

        if abs(error) < 0.2:
            cmd.linear.x = min(
                0.25, 0.5 * math.hypot(gx - x, gy - y)
            )

        self.publisher.publish(cmd)


def main():
    rclpy.init()
    node = GoalDriver()

    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        for _ in range(3):
            node.publisher.publish(Twist())
            time.sleep(0.1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

