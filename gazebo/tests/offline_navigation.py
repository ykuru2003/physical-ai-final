"""Synthetic LiDAR trials shared by baseline/precise offline checks; no ROS imports."""
import json
import math
from functools import partial
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ('empty', None, 0),
    ('path_obstacle', (1.25, .15, 1.75, .85), 0),
    ('original_obstacle', (1.75, -.35, 2.25, .35), 0),
    ('path_obstacle_scan_delay_100ms', (1.25, .15, 1.75, .85), 1),
    ('path_obstacle_scan_delay_300ms', (1.25, .15, 1.75, .85), 3),
)


def scan_at(pose, box):
    """Ray cast a full-circle scanner against an optional axis-aligned box."""
    x, y, yaw = pose
    origin = (x + 0.12 * math.cos(yaw), y + 0.12 * math.sin(yaw))
    ranges = []
    for i in range(180):
        a = -math.pi + i * 2 * math.pi / 179
        direction = (math.cos(yaw + a), math.sin(yaw + a))
        lo, hi = (0.0, 8.0)
        if box is None:
            ranges.append(math.inf)
            continue
        for o, d, lower, upper in zip(origin, direction, box[:2], box[2:]):
            if abs(d) < 1e-10:
                if not lower <= o <= upper:
                    hi = -1
            else:
                t1, t2 = sorted(((lower - o) / d, (upper - o) / d))
                lo, hi = (max(lo, t1), min(hi, t2))
        ranges.append(lo if 0.05 <= lo <= hi else math.inf)
    return SimpleNamespace(
        ranges=ranges, angle_min=-math.pi, angle_increment=2 * math.pi / 179,
        range_min=0.05, range_max=8.0,
    )


def trial(driver, name, box, delay_steps=0):
    planner = driver.LidarPlanner()
    pose = (0.0, 0.0, 0.0)
    minimum, avoids = (100.0, 0)
    scan_history = []
    for step in range(2400):
        scan_history.append(scan_at(pose, box))
        delayed_scan = scan_history[max(0, len(scan_history) - 1 - delay_steps)]
        v, w, state, _ = planner.command(pose, delayed_scan)
        if state == 'GOAL':
            return dict(
                name=name, result='PASS', seconds=step * 0.1, final_pose=pose,
                avoid_steps=avoids, min_circumscribed_margin=minimum if box else None,
            )
        assert state not in ('BLOCKED', 'INVALID_SCAN'), (name, pose, state)
        avoids += state == 'AVOID'
        x, y, yaw = pose
        pose = (
            x + 0.1 * v * math.cos(yaw + 0.05 * w),
            y + 0.1 * v * math.sin(yaw + 0.05 * w),
            driver.wrap(yaw + 0.1 * w),
        )
        if box:
            dx = max(box[0] - pose[0], 0.0, pose[0] - box[2])
            dy = max(box[1] - pose[1], 0.0, pose[1] - box[3])
            margin = math.hypot(dx, dy) - 0.33
            minimum = min(minimum, margin)
            assert margin > 0, (name, 'synthetic collision', pose)
    raise AssertionError((name, 'timeout', pose))


def check_scan_safety(driver):
    planner = driver.LidarPlanner()
    scan = scan_at((0, 0, 0), None)
    for value in (math.nan, -math.inf, 0.):
        scan.ranges[90] = value
        assert planner.command((0, 0, 0), scan)[2] == 'INVALID_SCAN'
    scan.ranges = [.2] * 180
    assert planner.command((0, 0, 0), scan)[2] == 'BLOCKED'
    scan.ranges = []
    assert planner.command((0, 0, 0), scan)[2] == 'INVALID_SCAN'


def check_sources_and_world():
    for source in (ROOT / 'scripts').rglob('*.py'):
        compile(source.read_text(encoding='utf-8-sig'), str(source), 'exec')
    world = ET.parse(ROOT / 'simulation/worlds/practice.sdf')
    assert world.find(".//model[@name='obstacle']/pose").text == '1.5 0.5 0.4 0 0 0'
    robot = world.find(".//model[@name='practice_robot']")
    assert robot.find("link[@name='front_caster']/pose").text == '0.20 0 0.05 0 0 0'
    assert robot.find("joint[@name='front_caster_joint']/child").text == 'front_caster'
    contact = world.find(".//sensor[@name='obstacle_contact']/contact/topic")
    assert contact.text == '/robot/obstacle_contacts'
    assert world.find(".//sensor[@name='attitude']") is not None


def run_checks(driver, *, report_name, test_type, goal_tolerance=None):
    results = [trial(driver, name, box, delay) for name, box, delay in CASES]
    check_scan_safety(driver)
    check_sources_and_world()
    if goal_tolerance is not None:
        for case in results:
            assert math.hypot(3 - case['final_pose'][0], 1 - case['final_pose'][1]) < goal_tolerance
        # Historical baseline drift bound, not a new physical-world measurement.
        assert .178143970581869 + goal_tolerance < .25
    report = dict(
        test_type=test_type, cases=results, invalid_scan_and_blocked='PASS',
        python_syntax='PASS', sdf_xml_front_support_and_sensors='PASS',
    )
    output = ROOT / '.cache' / report_name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


def main():
    import reference_navigation as reference

    for profile, report, tolerance in (
            ('baseline', 'reference-baseline-tests.json', None),
            ('precise', 'reference-precise-tests.json', .03)):
        driver = SimpleNamespace(LidarPlanner=partial(reference.planner_for, profile),
                                 wrap=reference.wrap)
        run_checks(driver, report_name=report,
                   test_type=f'{profile.upper()} OFFLINE SYNTHETIC ONLY; NOT GAZEBO/ROS',
                   goal_tolerance=tolerance)


if __name__ == '__main__':
    main()
