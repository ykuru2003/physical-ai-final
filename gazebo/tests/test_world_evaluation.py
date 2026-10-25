"""Tests that independent evaluation does not confuse odometry with true arrival."""
import math
from types import SimpleNamespace as NS
import unittest

from evaluate_navigation import driver_command, score_run, select_world_pose


class WorldEvaluationTests(unittest.TestCase):
    def score(self, actual=(2.9, 1.), odometry=(2.9, 1.), fresh=True, support=10, collisions=None):
        return score_run('GOAL REACHED!', 0, actual, odometry, fresh, support, collisions or [])

    def test_driver_commands_use_canonical_executables(self):
        for profile in ('baseline', 'precise'):
            with self.subTest(profile=profile):
                command = driver_command(profile, (3., 1.), 'result.json')
                self.assertEqual(command[2:], [
                    '/workspace/scripts/reference_navigation.py', '--profile', profile])
        command = driver_command('navigation', (1., -1.), 'result.json')
        self.assertEqual(command[2:], ['/workspace/scripts/navigate_to_goal.py',
                                     '--goal-x', '1.0', '--goal-y', '-1.0',
                                     '--output', 'result.json'])
        with self.assertRaises(ValueError):
            driver_command('invalid', (3., 1.), 'result.json')

    def test_odometry_success_can_be_world_failure(self):
        r = self.score(actual=(2.65, 1.17), odometry=(2.7584, 1.0458))
        self.assertTrue(r['odometry_goal_reached'])
        self.assertFalse(r['world_goal_reached'])
        self.assertEqual(r['status'], 'FAIL')
        self.assertGreater(r['world_goal_error_m'], .38)

    def test_actual_arrival_and_monitor_required(self):
        self.assertEqual(self.score()['status'], 'PASS')
        self.assertEqual(self.score(fresh=False)['status'], 'INCOMPLETE')
        self.assertEqual(self.score(support=0)['status'], 'INCOMPLETE')
        self.assertEqual(self.score(actual=None)['status'], 'INCOMPLETE')
        self.assertEqual(self.score(actual=(math.nan, 1))['status'], 'INCOMPLETE')
        self.assertEqual(self.score(collisions=[['practice_robot', 'obstacle']])['status'], 'FAIL')

    def test_failed_driver_cannot_pass(self):
        r = score_run('TIMEOUT', 1, (3,1), (3,1), True, 10, [])
        self.assertEqual(r['status'], 'INCOMPLETE')

    def test_select_only_world_to_robot(self):
        def tf(parent, child, x=1.):
            return NS(header=NS(frame_id=parent, stamp=NS(sec=3, nanosec=500000000)),
                      child_frame_id=child, transform=NS(translation=NS(x=x,y=2.,z=0.)))
        message=NS(transforms=[tf('practice_robot','base_link'), tf('practice','obstacle'), tf('/practice','/practice_robot')])
        self.assertEqual(select_world_pose(message), ((1.,2.), 3.5))
        self.assertIsNone(select_world_pose(NS(transforms=[tf('odom','practice_robot')])))
        self.assertIsNone(select_world_pose(NS(transforms=[tf('practice','practice_robot',math.nan)])))


if __name__ == '__main__':
    unittest.main()
