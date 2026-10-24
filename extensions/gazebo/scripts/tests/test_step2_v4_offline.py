"""Run v4 synthetic navigation checks without ROS or simulator startup."""
from navigation import drive_to_goal_v4 as driver
from tests.offline_navigation import run_checks


def main():
    run_checks(
        driver, report_name='step2-v4-offline-tests.json',
        test_type='V4 OFFLINE SYNTHETIC ONLY; NOT GAZEBO/ROS', goal_tolerance=.03,
    )


if __name__ == '__main__':
    main()
