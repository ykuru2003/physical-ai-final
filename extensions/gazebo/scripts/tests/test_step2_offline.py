"""Run v3 synthetic navigation checks without ROS or simulator startup."""
from navigation import drive_to_goal_v3 as driver
from tests.offline_navigation import run_checks


def main():
    run_checks(
        driver, report_name='step2-offline-tests.json',
        test_type='OFFLINE SYNTHETIC ONLY; NOT GAZEBO/ROS',
    )


if __name__ == '__main__':
    main()
