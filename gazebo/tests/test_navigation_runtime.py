"""Exercise the current navigation ROS lifecycle with deterministic fake messages and no services."""
import json
import math
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import navigate_to_goal as runtime


class RuntimeTests(unittest.TestCase):
    def run_fake(self, event='GOAL', *, goal=(3., 1.)):
        holder = {}

        class Twist:
            def __init__(self):
                self.linear = NS(x=0., y=0., z=0.)
                self.angular = NS(x=0., y=0., z=0.)

        class Node:
            def __init__(self, name):
                self.name = name
                self.callbacks = {}
                self.publisher = Mock()
                self.publisher.get_subscription_count.return_value = 1
                self.destroy_node = Mock()
                holder['node'] = self

            def create_publisher(self, *args):
                return self.publisher

            def create_subscription(self, message_type, topic, callback, qos):
                self.callbacks[topic] = callback
                return Mock()

            def create_timer(self, period, callback):
                self.control_callback = callback
                return Mock()

        modules = {name: ModuleType(name) for name in (
            'rclpy', 'rclpy.node', 'rclpy.qos', 'geometry_msgs', 'geometry_msgs.msg',
            'nav_msgs', 'nav_msgs.msg', 'sensor_msgs', 'sensor_msgs.msg',
            'ros_gz_interfaces', 'ros_gz_interfaces.msg',
        )}
        ros = modules['rclpy']
        ros.init = Mock()
        ros.ok = Mock(return_value=True)
        ros.shutdown = Mock()
        modules['rclpy.node'].Node = Node
        modules['rclpy.qos'].qos_profile_sensor_data = object()
        for name, classes in (
            ('geometry_msgs.msg', ('Twist',)), ('nav_msgs.msg', ('Odometry',)),
            ('sensor_msgs.msg', ('LaserScan', 'Imu')), ('ros_gz_interfaces.msg', ('Contacts',)),
        ):
            for cls in classes:
                setattr(modules[name], cls, Twist if cls == 'Twist' else NS)
        planner = Mock(detour_side=0)
        planner.command.return_value = (0., 0., event, 1.)
        fired = False

        def spin(node, timeout_sec):
            nonlocal fired
            if fired:
                return
            fired = True
            if event == 'INTERRUPT':
                raise KeyboardInterrupt
            if event == 'EXCEPTION':
                raise RuntimeError('spin failure')
            if event == 'SHUTDOWN':
                ros.ok.return_value = False
                return
            q = NS(w=1., x=0., y=0., z=0.)
            x = float('nan') if event == 'INVALID_ODOM' else 0.
            node.callbacks['/odom'](NS(pose=NS(pose=NS(position=NS(x=x, y=0.), orientation=q))))
            node.callbacks['/robot/imu'](NS(orientation=q))
            node.callbacks['/scan'](NS(ranges=[1.], angle_min=0., angle_increment=.1, header=NS(stamp=NS(sec=0, nanosec=0))))
            node.callbacks['/robot/support_contacts'](NS(contacts=[object()]))
            if event == 'CONTACT':
                node.callbacks['/robot/obstacle_contacts'](NS(contacts=[NS(
                    collision1=NS(name='practice_robot::body'), collision2=NS(name='obstacle'),
                )]))
            node.control_callback()

        ros.spin_once = Mock(side_effect=spin)
        path = Mock()
        clock = Mock(side_effect=[0., 241.] if event == 'TIMEOUT' else None, return_value=0.)
        # TIMEOUT must pass initialization and callbacks before control reads its clock.
        if event == 'TIMEOUT':
            clock.side_effect = [0., 0., 0., 0., 241.]
        with patch.dict(sys.modules, modules), patch.object(runtime, 'Path', return_value=path), \
                patch.object(runtime.time, 'monotonic', clock), patch('builtins.print'), \
                patch.object(runtime, 'LidarPlanner', return_value=planner), \
                patch.object(sys, 'argv', ['navigate', '--goal-x', str(goal[0]), '--goal-y', str(goal[1]), '--output', 'result.json']):
            try:
                code = runtime.main()
            except (OSError, RuntimeError):
                if event != 'EXCEPTION':
                    raise
                code = None
        node = holder['node']
        self.assertEqual(node.name, 'goal_driver_navigation')
        node.destroy_node.assert_called_once()
        ros.shutdown.assert_called_once()
        commands = [call.args[0] for call in node.publisher.publish.call_args_list]
        self.assertGreaterEqual(len(commands), 5)
        self.assertTrue(all(c.linear.x == 0. and c.angular.z == 0. for c in commands[-5:]))
        report = json.loads(path.write_text.call_args.args[0])
        return code, report

    def test_goal_and_report_schema(self):
        code, report = self.run_fake()
        self.assertEqual(code, 0)
        self.assertEqual(report['result'], 'GOAL REACHED!')
        self.assertEqual(report['goal'], [3, 1])
        self.assertEqual(report['support_contact_count'], 1)
        self.assertEqual(report['obstacle_collisions'], [])

    def test_sensor_collision_timeout_and_interruption_stop(self):
        for event, expected in (
            ('INVALID_ODOM', 'ERROR: invalid odometry'),
            ('CONTACT', 'ERROR: obstacle collision detected'),
            ('BLOCKED', 'ERROR: BLOCKED'), ('INVALID_SCAN', 'ERROR: INVALID_SCAN'),
            ('TIMEOUT', 'TIMEOUT: Goal not reached'), ('INTERRUPT', 'INTERRUPTED'),
            ('SHUTDOWN', 'ERROR: ROS shutdown'), ('EXCEPTION', 'ERROR: spin failure'),
        ):
            with self.subTest(event=event):
                code, report = self.run_fake(event)
                self.assertEqual(report['result'], expected)
                self.assertEqual(code, None if event == 'EXCEPTION' else 1)


    def test_configurable_goal_is_written_to_report(self):
        code, report = self.run_fake(goal=(1., -1.))
        self.assertEqual(code, 0)
        self.assertEqual(report['goal'], [1., -1.])



if __name__ == '__main__':
    unittest.main()
