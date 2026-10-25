"""Shared reference navigation for the baseline/precise stop-tolerance profiles."""
import argparse
import math
from functools import partial


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


class LidarPlanner:
    goal_tolerance = 0.03
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
        if distance < self.goal_tolerance:
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


PROFILE_TOLERANCES = {'baseline': .25, 'precise': .03}


def planner_for(profile):
    planner = LidarPlanner()
    planner.goal_tolerance = PROFILE_TOLERANCES[profile]
    return planner


def run_profile(version):
    from ros_driver import run_driver

    messages = {
        'baseline': 'START: Waiting for /odom and /scan; GOAL=(3,1), no waypoints',
        'precise': 'START precise: Waiting for /odom and /scan; GOAL=(3,1), odometry stop tolerance=0.03m, no waypoints',
    }
    return run_driver(partial(planner_for, version), node_name='goal_driver_' + version,
                      start_message=messages[version])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=tuple(PROFILE_TOLERANCES), default='baseline')
    return run_profile(parser.parse_args(argv).profile)


if __name__ == '__main__':
    raise SystemExit(main())
