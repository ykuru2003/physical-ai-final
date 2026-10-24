"""STEP 2: full-circle lidar avoidance without supplied waypoints.

Planner imports without ROS for offline verification. Geometry matches practice.sdf.
"""
import math


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
        if distance < 0.25:
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
    from navigation.ros_driver import run_driver

    return run_driver(
        LidarPlanner, node_name="goal_driver_v3",
        start_message='START: Waiting for /odom and /scan; GOAL=(3,1), no waypoints',
    )


if __name__ == "__main__":
    raise SystemExit(main())
