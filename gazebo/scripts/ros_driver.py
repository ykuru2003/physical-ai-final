"""Shared ROS lifecycle for the fixed-goal baseline/precise reference drivers.

ROS imports stay inside run_driver so planners remain usable offline.
The certified navigation runtime is intentionally self-contained.
"""
import json
import math
import time
from pathlib import Path


def run_driver(planner_factory, *, node_name, start_message):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan, Imu
    from ros_gz_interfaces.msg import Contacts

    class GoalDriver(Node):
        def __init__(self):
            super().__init__(node_name)
            self.pose = self.scan = None
            self.last_odom = self.last_scan = self.last_log = 0.
            self.started = time.monotonic()
            self.result = None
            self.trace = []
            self.attitude = None
            self.max_tilt = 0.
            self.support_contacts = 0
            self.obstacle_contact_messages = 0
            self.contact_events = []
            self.planner = planner_factory()
            self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
            self.odom_sub = self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)
            self.scan_sub = self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
            self.imu_sub = self.create_subscription(Imu, '/robot/imu', self.on_imu, qos_profile_sensor_data)
            self.contact_sub = self.create_subscription(Contacts, '/robot/obstacle_contacts', self.on_contact, qos_profile_sensor_data)
            self.support_sub = self.create_subscription(Contacts, '/robot/support_contacts', self.on_support, qos_profile_sensor_data)
            self.timer = self.create_timer(0.1, self.control)
            print(start_message, flush=True)

        def on_odom(self, msg):
            p, q = msg.pose.pose.position, msg.pose.pose.orientation
            yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            if not all(math.isfinite(v) for v in (p.x, p.y, yaw)):
                self.finish('ERROR: invalid odometry')
                return
            self.pose = (p.x, p.y, yaw)
            self.last_odom = time.monotonic()

        def on_imu(self, msg):
            q = msg.orientation
            roll = math.atan2(2*(q.w*q.x+q.y*q.z), 1-2*(q.x*q.x+q.y*q.y))
            pitch = math.asin(max(-1., min(1., 2*(q.w*q.y-q.z*q.x))))
            self.attitude = (roll, pitch)
            self.max_tilt = max(self.max_tilt, abs(roll), abs(pitch))
            self.last_imu = time.monotonic()
            if max(abs(roll), abs(pitch)) > 0.20:
                self.finish(f'ERROR: robot tilted; roll={roll:.3f}, pitch={pitch:.3f}')

        def on_support(self, msg):
            self.support_contacts += len(msg.contacts)

        def on_contact(self, msg):
            self.obstacle_contact_messages += 1
            for contact in msg.contacts:
                names = (contact.collision1.name, contact.collision2.name)
                if any('practice_robot' in name for name in names):
                    self.contact_events.append(names)
                    self.finish('ERROR: obstacle collision detected')

        def on_scan(self, msg):
            self.scan = msg
            self.last_scan = time.monotonic()

        def finish(self, result):
            if self.result is None:
                self.result = result
                print(result, flush=True)
            self.pub.publish(Twist())

        def control(self):
            if self.result:
                return
            now = time.monotonic()
            if now-self.started > 240:
                self.finish('TIMEOUT: Goal not reached')
                return
            if self.pose is None or self.scan is None or self.attitude is None or self.pub.get_subscription_count() == 0:
                self.pub.publish(Twist())
                if now-self.started > 30:
                    self.finish('ERROR: ROS topics/bridge not ready')
                return
            if now-self.last_odom > 1. or now-self.last_scan > 1. or now-self.last_imu > 1.:
                self.finish('ERROR: stale /odom, /scan or /robot/imu')
                return
            linear, angular, state, clearance = self.planner.command(self.pose, self.scan)
            if state == 'GOAL':
                self.finish('GOAL REACHED!')
                return
            if state in ('BLOCKED', 'INVALID_SCAN'):
                self.trace.append(dict(elapsed=now-self.started, pose=self.pose, state=state, clearance=clearance, attitude=self.attitude,
                                       scan_ranges=[r if math.isfinite(r) else None for r in self.scan.ranges],
                                       angle_min=self.scan.angle_min, angle_increment=self.scan.angle_increment))
                self.finish('ERROR: '+state)
                return
            cmd = Twist()
            cmd.linear.x, cmd.angular.z = linear, angular
            self.pub.publish(cmd)
            self.trace.append(dict(
                elapsed=now-self.started, pose=self.pose, linear=linear, angular=angular,
                state=state, clearance=clearance, attitude=self.attitude,
                detour_side=self.planner.detour_side,
                scan_stamp=[self.scan.header.stamp.sec, self.scan.header.stamp.nanosec],
                scan_min=min((r for r in self.scan.ranges if math.isfinite(r)), default=None),
            ))
            if now-self.last_log >= 1:
                print(f'POS=({self.pose[0]:.2f},{self.pose[1]:.2f}) STATE={state} CMD=({linear:.2f},{angular:.2f}) CLEARANCE={clearance:.3f}', flush=True)
                self.last_log = now

    rclpy.init()
    node = GoalDriver()
    try:
        while rclpy.ok() and node.result is None:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        node.finish('INTERRUPTED')
    except Exception as error:
        node.finish(f'ERROR: {error}')
        raise
    finally:
        for _ in range(5):
            node.pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.05)
        try:
            report = dict(
                result=node.result or 'ERROR: ROS shutdown', goal=[3, 1],
                final_pose=node.pose, max_tilt_rad=node.max_tilt,
                support_contact_count=node.support_contacts,
                obstacle_contact_message_count=node.obstacle_contact_messages,
                obstacle_collisions=node.contact_events, trace=node.trace,
            )
            Path('/workspace/outputs/navigation-run.json').write_text(
                json.dumps(report, indent=2)+'\n', encoding='utf-8',
            )
        finally:
            node.destroy_node()
            rclpy.shutdown()
    return 0 if node.result == 'GOAL REACHED!' else 1

