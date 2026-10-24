"""Publish zero velocity and confirm fresh stationary odometry; requires ROS."""
import math
import time


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    rclpy.init(args=[])
    node = Node('language_goal_safety_stop')
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)
    state = {'stationary_since': None, 'received': 0., 'samples': 0}

    def on_odom(msg):
        now = time.monotonic()
        v = msg.twist.twist
        values = (v.linear.x, v.linear.y, v.linear.z, v.angular.x, v.angular.y, v.angular.z)
        stationary = all(math.isfinite(x) and abs(x) < .02 for x in values)
        if not stationary or now - state['received'] > .5:
            state['stationary_since'] = None
            state['samples'] = 0
        if stationary:
            if state['stationary_since'] is None:
                state['stationary_since'] = now
            state['samples'] += 1
        state['received'] = now

    subscription = node.create_subscription(Odometry, '/odom', on_odom, qos_profile_sensor_data)
    confirmed = False
    try:
        deadline = time.monotonic() + 8.
        while rclpy.ok() and time.monotonic() < deadline:
            publisher.publish(Twist())
            rclpy.spin_once(node, timeout_sec=.05)
            now = time.monotonic()
            if (publisher.get_subscription_count() > 0 and state['samples'] >= 5
                    and state['stationary_since'] is not None
                    and now - state['stationary_since'] >= .5 and now - state['received'] < .3):
                confirmed = True
                break
    finally:
        publisher.publish(Twist())
        node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()
    print('STOP: ' + ('CONFIRMED_STATIONARY' if confirmed else 'UNCONFIRMED'), flush=True)
    return 0 if confirmed else 1


if __name__ == '__main__':
    raise SystemExit(main())
