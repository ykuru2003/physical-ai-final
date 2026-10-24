"""Independent world-position evaluation of a selected STEP 2 driver.

Ground truth is used only for scoring and sensor-loss safety stops, never to
choose the navigation commands. Importable scoring functions do not need ROS.
"""
import argparse
import json
import math
import signal
import subprocess
import sys
import time
from pathlib import Path


def select_world_pose(message, world='practice', model='practice_robot'):
    for transform in message.transforms:
        if (transform.header.frame_id.lstrip('/') == world
                and transform.child_frame_id.lstrip('/') == model):
            p = transform.transform.translation
            if all(math.isfinite(v) for v in (p.x, p.y, p.z)):
                stamp = transform.header.stamp.sec + transform.header.stamp.nanosec/1e9
                return (p.x, p.y), stamp
    return None


def score_run(driver_result, driver_exit, actual_xy, odometry_xy,
              fresh_and_synchronized, support_contacts, collisions, tolerance=.25, goal=(3., 1.)):
    result = dict(status='INCOMPLETE', goal=list(goal), tolerance_m=tolerance,
                  driver_result=driver_result, driver_exit_code=driver_exit,
                  final_world_position=actual_xy, final_odometry=odometry_xy,
                  support_contact_count=support_contacts, obstacle_collisions=collisions)
    if (driver_exit != 0 or driver_result != 'GOAL REACHED!'
            or actual_xy is None or odometry_xy is None or not fresh_and_synchronized):
        result['reason'] = 'Driver failed or fresh, synchronized world/odom data unavailable'
        return result
    if (not all(math.isfinite(v) for v in (*actual_xy, *odometry_xy))
            or not math.isfinite(tolerance) or tolerance <= 0):
        result['reason'] = 'Invalid position or tolerance'
        return result
    actual_error = math.dist(actual_xy, result['goal'])
    odometry_error = math.dist(odometry_xy, result['goal'])
    drift = math.dist(actual_xy, odometry_xy)
    result.update(world_goal_error_m=actual_error, odometry_goal_error_m=odometry_error,
                  odometry_world_difference_m=drift,
                  odometry_goal_reached=odometry_error <= tolerance,
                  world_goal_reached=actual_error <= tolerance)
    if collisions:
        result.update(status='FAIL', reason='Obstacle contact detected')
    elif support_contacts <= 0:
        result['reason'] = 'Contact-monitor operation was not confirmed'
    elif actual_error > tolerance:
        result.update(status='FAIL', reason='Odometry reports arrival, but world position is outside tolerance')
    else:
        result.update(status='PASS', reason='World-position goal and contact checks passed')
    return result


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import Twist
    from ros_gz_interfaces.msg import Contacts
    from tf2_msgs.msg import TFMessage

    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--driver', choices=('v3', 'v4', 'v5'), default='v3')
    parser.add_argument('--goal-x', type=float, default=3.0)
    parser.add_argument('--goal-y', type=float, default=1.0)
    args = parser.parse_args()
    if not all(math.isfinite(v) for v in (args.goal_x, args.goal_y)):
        parser.error('Goal coordinates must be finite')
    if args.driver != 'v5' and (args.goal_x, args.goal_y) != (3., 1.):
        parser.error('Only v5 supports configurable goals')
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    driver_path = (output/'v5-result.json' if args.driver == 'v5'
                   else Path('/workspace/outputs/step2-run.json'))
    if args.driver == 'v5' and (driver_path.exists() or (output/'driver-run.json').exists()):
        raise RuntimeError('Refusing to reuse existing v5 evaluation results')
    previous_driver_report = driver_path.read_bytes() if driver_path.exists() else None

    class Monitor(Node):
        def __init__(self):
            super().__init__('step2_world_evaluator')
            self.actual = self.odom = None
            self.actual_stamp = self.odom_stamp = None
            self.actual_received = self.odom_received = 0.
            self.support = 0
            self.collisions = []
            self.samples = []
            self.observed_frames = set()
            self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
            self.subscriptions_held = [
                self.create_subscription(TFMessage, '/step2/ground_truth', self.on_actual, qos_profile_sensor_data),
                self.create_subscription(Odometry, '/odom', self.on_odom, qos_profile_sensor_data),
                self.create_subscription(Contacts, '/step2/support_contacts', self.on_support, qos_profile_sensor_data),
                self.create_subscription(Contacts, '/step2/obstacle_contacts', self.on_contact, qos_profile_sensor_data),
            ]

        def on_odom(self, msg):
            p = msg.pose.pose.position
            if math.isfinite(p.x) and math.isfinite(p.y):
                self.odom = (p.x, p.y)
                self.odom_stamp = msg.header.stamp.sec + msg.header.stamp.nanosec/1e9
                self.odom_received = time.monotonic()

        def on_actual(self, msg):
            for tf in msg.transforms:
                self.observed_frames.add((tf.header.frame_id, tf.child_frame_id))
            selected = select_world_pose(msg)
            if selected is not None:
                self.actual, self.actual_stamp = selected
                self.actual_received = time.monotonic()
                if self.synchronized():
                    self.samples.append(dict(sim_time=self.actual_stamp, world_position=self.actual,
                                             odometry=self.odom, stamp_gap_s=abs(self.actual_stamp-self.odom_stamp)))

        def on_support(self, msg):
            self.support += len(msg.contacts)

        def on_contact(self, msg):
            for c in msg.contacts:
                pair = (c.collision1.name, c.collision2.name)
                if any('practice_robot' in name for name in pair):
                    self.collisions.append(pair)

        def synchronized(self):
            now = time.monotonic()
            return (self.actual is not None and self.odom is not None
                    and now-self.actual_received < 1. and now-self.odom_received < 1.
                    and abs(self.actual_stamp-self.odom_stamp) <= .10)

    rclpy.init()
    node = Monitor()
    child = None
    report = dict(status='INCOMPLETE', reason='Evaluation did not finish')
    driver = {}
    try:
        print('EVALUATION: waiting for world position and odometry (up to 30s)', flush=True)
        deadline = time.monotonic()+30
        while rclpy.ok() and not node.synchronized():
            rclpy.spin_once(node, timeout_sec=.1)
            if time.monotonic() > deadline:
                raise RuntimeError('No synchronized world pose: check PosePublisher and /step2/ground_truth bridge')
        print(f'EVALUATION: world-position monitor ready; starting {args.driver} driver', flush=True)
        command = [sys.executable, '-u', f'/workspace/scripts/drive_to_goal_{args.driver}.py']
        if args.driver == 'v5':
            command += ['--goal-x', str(args.goal_x), '--goal-y', str(args.goal_y),
                        '--output', str(driver_path)]
        child = subprocess.Popen(command)
        deadline = time.monotonic()+260
        while child.poll() is None and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=.1)
            if (time.monotonic()-node.actual_received > 1.
                    or time.monotonic()-node.odom_received > 1.):
                raise RuntimeError('World/odometry measurement stopped during evaluation')
            if node.collisions:
                raise RuntimeError('Obstacle contact detected during evaluation')
            if time.monotonic() > deadline:
                raise RuntimeError('Evaluation timed out')
        if child.poll() is None:
            raise RuntimeError('ROS stopped while driver was running')
        # Score the stationary final pose, not a sample from before stopping.
        deadline = time.monotonic()+1.
        while rclpy.ok() and time.monotonic() < deadline:
            node.pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=.05)
        if driver_path.exists():
            driver = json.loads(driver_path.read_text())
            (output/'driver-run.json').write_text(json.dumps(driver, indent=2)+'\n')
        report = score_run(driver.get('result'), child.returncode, node.actual, node.odom,
                           node.synchronized(), node.support, node.collisions, goal=(args.goal_x, args.goal_y))
        report['world_sample_count'] = len(node.samples)
        report['max_world_odom_difference_m'] = max((math.dist(s['world_position'], s['odometry']) for s in node.samples), default=None)
    except KeyboardInterrupt:
        report = dict(status='INCOMPLETE', reason='Evaluation interrupted')
    except Exception as error:
        report = dict(status='INCOMPLETE', reason=str(error))
    finally:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        for _ in range(5):
            node.pub.publish(Twist())
            if rclpy.ok():
                rclpy.spin_once(node, timeout_sec=.05)
        if child is not None:
            if driver_path.exists() and not (output/'driver-run.json').exists():
                (output/'driver-run.json').write_bytes(driver_path.read_bytes())
            if previous_driver_report is not None:
                driver_path.write_bytes(previous_driver_report)
            elif driver_path.exists():
                driver_path.replace(output/'driver-run.json')
        report['observed_frames'] = sorted(node.observed_frames)
        report['driver_version'] = args.driver
        report['world_topic'] = '/step2/ground_truth'
        report['ground_truth_used_for_navigation'] = False
        (output/'evaluation.json').write_text(json.dumps(report, indent=2)+'\n')
        (output/'world-odom-trace.json').write_text(json.dumps(node.samples, indent=2)+'\n')
        node.destroy_node()
        rclpy.shutdown()
    print('WORLD EVALUATION: '+report['status'], flush=True)
    print(json.dumps(report, indent=2), flush=True)
    return {'PASS': 0, 'FAIL': 2, 'INCOMPLETE': 1}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())

