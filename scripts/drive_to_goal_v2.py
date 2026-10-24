import math
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist

class GoalDriver(Node):
    def __init__(self):
        super().__init__("goal_driver_v2")
        self.waypoints = [(0.0, 1.0), (3.0, 1.0)]
        self.index = 0
        self.pose = None
        self.last_odom = None
        self.start = time.monotonic()
        self.last_log = 0
        self.done = False

        self.pub = self.create_publisher(
            Twist, "/cmd_vel", 10
        )
        self.sub = self.create_subscription(
            Odometry, "/odom",
            self.on_odom, qos_profile_sensor_data
        )
        self.timer = self.create_timer(0.1, self.control)
        print("START: Waiting for /odom...", flush=True)

    def on_odom(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(
            2 * (q.w*q.z + q.x*q.y),
            1 - 2*(q.y*q.y + q.z*q.z)
        )
        self.pose = (p.x, p.y, yaw)
        self.last_odom = time.monotonic()

    def stop(self, message):
        print(message, flush=True)
        self.pub.publish(Twist())
        self.done = True

    def control(self):
        if self.done:
            return

        now = time.monotonic()

        if self.pose is None:
            if now - self.start > 10:
                self.stop("ERROR: /odom not received")
            return

        if now - self.last_odom > 3:
            self.stop("ERROR: /odom stopped updating")
            return

        if now - self.start > 120:
            self.stop("TIMEOUT: Goal not reached")
            return

        x, y, yaw = self.pose
        gx, gy = self.waypoints[self.index]
        distance = math.hypot(gx-x, gy-y)

        if distance < (0.18 if self.index == 0 else 0.30):
            if self.index == 0:
                self.index = 1
                print("WAYPOINT REACHED", flush=True)
                gx, gy = self.waypoints[self.index]
                distance = math.hypot(gx-x, gy-y)
            else:
                self.stop("GOAL REACHED!")
                return

        target = math.atan2(gy-y, gx-x)
        error = math.atan2(
            math.sin(target-yaw),
            math.cos(target-yaw)
        )

        cmd = Twist()
        cmd.angular.z = max(-1.0, min(1.0, 2.0*error))

        if abs(error) < 0.25:
            cmd.linear.x = min(0.25, 0.5*distance)

        self.pub.publish(cmd)

        if now - self.last_log > 1:
            print(
                f"POS=({x:.2f},{y:.2f}) "
                f"GOAL=({gx:.1f},{gy:.1f}) "
                f"CMD=({cmd.linear.x:.2f},{cmd.angular.z:.2f})",
                flush=True
            )
            self.last_log = now

def main():
    rclpy.init()
    node = GoalDriver()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        print("Interrupted", flush=True)
    finally:
        for _ in range(5):
            node.pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.05)
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
