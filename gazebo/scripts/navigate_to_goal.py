"""Goal navigation: configurable goal, preserving precise stopping and safety logic.

The world evaluator still requires actual goal error <= 0.25 m. This driver
stops within 0.03 m in odometry to leave room for the measured ~0.18 m drift.
This is a stopping-margin adjustment, not an odometry-bias correction or a
world-accuracy guarantee. Ground truth is never used for navigation.



Planner imports without ROS for offline verification. Geometry matches practice.sdf.

"""

import argparse

import json

import math

import time

from pathlib import Path





def wrap(a):

    return math.atan2(math.sin(a), math.cos(a))





class LidarPlanner:

    radius = 0.48  # Body/wheels circumscribed radius plus margin.

    lidar_x = 0.12



    def __init__(self):

        self.previous_world = None

        self.detour_side = 0

        self.direct_clear_count = 0



    def command(self, pose, scan, goal=(3.0, 1.0)):

        x, y, yaw = pose

        distance = math.hypot(goal[0]-x, goal[1]-y)

        target = wrap(math.atan2(goal[1]-y, goal[0]-x)-yaw)

        points = []

        if (len(scan.ranges) < 30 or not math.isfinite(scan.angle_increment)

                or scan.angle_increment <= 0

                or (len(scan.ranges)-1)*scan.angle_increment < 6.0

                or not math.isfinite(scan.angle_min)):

            return 0., 0., 'INVALID_SCAN', None

        for i, r in enumerate(scan.ranges):

            if r == math.inf:

                continue

            if not math.isfinite(r) or not scan.range_min <= r <= scan.range_max:

                return 0., 0., 'INVALID_SCAN', None

            a = scan.angle_min + i*scan.angle_increment

            points.append((self.lidar_x+r*math.cos(a), r*math.sin(a)))

        clearance = min((math.hypot(px, py)-0.33 for px, py in points), default=scan.range_max)

        if clearance < 0.05:

            return 0., 0., 'BLOCKED', clearance

        if distance < 0.03:

            return 0., 0., 'GOAL', clearance

        horizon = min(1., distance)



        def free(a):

            c, s = math.cos(a), math.sin(a)

            for px, py in points:

                along, across = px*c+py*s, -px*s+py*c

                closest = max(0., min(horizon, along))

                # Points behind the travel direction do not block escape.

                if along > 0. and math.hypot(along-closest, across) < self.radius:

                    return False

            return True



        safe = [a for a in [target]+[i*math.pi/90 for i in range(-90, 91)] if free(a)]

        if not safe:

            return 0., 0., 'BLOCKED', clearance

        # Keep the chosen side until the goal corridor has been clear for

        # several scans. Re-selecting both sides every tick can cause spinning.

        self.direct_clear_count = self.direct_clear_count + 1 if free(target) else 0

        if self.direct_clear_count >= 5:

            self.detour_side = 0

        previous = (wrap(self.previous_world-yaw)

                    if self.previous_world is not None else target)



        def score(a):

            return abs(wrap(a-target)) + 0.18*abs(wrap(a-previous)) - 0.001*a



        if not free(target) and self.detour_side == 0:

            first = min(safe, key=score)

            self.detour_side = 1 if wrap(first-target) >= 0 else -1

        if self.detour_side:

            same_side = [a for a in safe

                         if self.detour_side*wrap(a-target) >= -0.02]

            if not same_side:

                return 0., 0., 'BLOCKED', clearance

            safe = same_side

        heading = min(safe, key=score)

        self.previous_world = wrap(yaw+heading)

        angular = max(-0.8, min(0.8, 2*heading))

        linear = min(0.22, 0.5*distance) if abs(heading) < 0.20 and free(0.) else 0.

        return linear, angular, 'DIRECT' if abs(wrap(heading-target)) < 0.03 else 'AVOID', clearance





def main():

    parser = argparse.ArgumentParser(description='Drive to a goal using LiDAR obstacle avoidance.')
    parser.add_argument('--goal-x', type=float, default=3.0, help='Goal x coordinate in metres (default: 3.0).')
    parser.add_argument('--goal-y', type=float, default=1.0, help='Goal y coordinate in metres (default: 1.0).')
    parser.add_argument('--output', default='/workspace/outputs/navigation-run.json', help='Per-run result JSON path.')
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in (args.goal_x, args.goal_y)):
        parser.error('--goal-x and --goal-y must be finite numbers')

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import rclpy

    from rclpy.node import Node

    from rclpy.qos import qos_profile_sensor_data

    from geometry_msgs.msg import Twist

    from nav_msgs.msg import Odometry

    from sensor_msgs.msg import LaserScan, Imu

    from ros_gz_interfaces.msg import Contacts



    class GoalDriver(Node):

        def __init__(self, goal):

            super().__init__('goal_driver_navigation')

            self.goal = tuple(goal)

            self.pose = self.scan = None

            self.last_odom = self.last_scan = self.last_log = 0.

            self.started = time.monotonic()

            self.result = None

            self.trace = []

            self.attitude = None

            self.max_tilt = 0.

            self.support_contacts = 0

            self.obstacle_contact_messages = 0

            self.last_scan_snapshot = 0.

            self.contact_events = []

            self.planner = LidarPlanner()

            self.pub = self.create_publisher(Twist, '/cmd_vel', 10)

            self.odom_sub = self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data)

            self.scan_sub = self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)

            self.imu_sub = self.create_subscription(Imu, '/robot/imu', self.on_imu, qos_profile_sensor_data)

            self.contact_sub = self.create_subscription(Contacts, '/robot/obstacle_contacts', self.on_contact, qos_profile_sensor_data)

            self.support_sub = self.create_subscription(Contacts, '/robot/support_contacts', self.on_support, qos_profile_sensor_data)

            self.timer = self.create_timer(0.1, self.control)

            print(f'START navigation: Waiting for /odom and /scan; GOAL=({self.goal[0]:g},{self.goal[1]:g}), odometry stop tolerance=0.03m, no waypoints', flush=True)



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

            linear, angular, state, clearance = self.planner.command(self.pose, self.scan, goal=self.goal)

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

            self.trace.append(dict(elapsed=now-self.started, pose=self.pose, linear=linear, angular=angular, state=state, clearance=clearance, attitude=self.attitude, detour_side=self.planner.detour_side, scan_stamp=[self.scan.header.stamp.sec, self.scan.header.stamp.nanosec], scan_min=min((r for r in self.scan.ranges if math.isfinite(r)), default=None)))

            if now-self.last_log >= 1:

                print(f'POS=({self.pose[0]:.2f},{self.pose[1]:.2f}) STATE={state} CMD=({linear:.2f},{angular:.2f}) CLEARANCE={clearance:.3f}', flush=True)

                self.last_log = now



    rclpy.init(args=[])

    node = GoalDriver((args.goal_x, args.goal_y))

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

        output_path.write_text(json.dumps(dict(result=node.result or 'ERROR: ROS shutdown', goal=list(node.goal), final_pose=node.pose, max_tilt_rad=node.max_tilt, support_contact_count=node.support_contacts, obstacle_contact_message_count=node.obstacle_contact_messages, obstacle_collisions=node.contact_events, trace=node.trace), indent=2)+'\n', encoding='utf-8')

        node.destroy_node()

        rclpy.shutdown()

    return 0 if node.result == 'GOAL REACHED!' else 1





if __name__ == '__main__':

    raise SystemExit(main())

