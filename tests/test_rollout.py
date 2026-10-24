"""Verify rollout accounting with deterministic environments and raw-coordinate policies."""

import unittest

import numpy as np

from roboops.rollout import evaluate_episode, summarize_episodes


class FakeEnvironment:
    def __init__(self, *, truncate_at=None):
        self.unwrapped = self
        self.success_threshold = 0.8
        self.events = []
        self.steps = 0
        self.render_calls = 0
        self.truncate_at = truncate_at

    def reset(self, *, seed):
        self.events.append(("environment_reset", seed))
        self.steps = 0
        return {"step": 0}, {}

    def _get_coverage(self):
        return 0.4

    def step(self, action):
        np.testing.assert_array_equal(action, [128.0, 256.0])
        reward = [0.2, 0.8, 0.6][self.steps]
        self.steps += 1
        return (
            {"step": self.steps},
            reward,
            self.steps == 3,
            self.steps == self.truncate_at,
            {"is_success": self.steps == 2},
        )

    def render(self):
        self.render_calls += 1
        return np.full((2, 2, 3), self.steps, dtype=np.uint8)


class FakePolicy:
    def __init__(self, environment):
        self.environment = environment
        self.observations = []

    def reset(self):
        self.environment.events.append(("policy_reset", None))

    def select_action(self, observation):
        self.observations.append(observation["step"])
        return np.array([128.0, 256.0])


class RolloutTests(unittest.TestCase):
    def test_reward_gain_and_success_include_initial_coverage_and_all_steps(self):
        env = FakeEnvironment()
        policy = FakePolicy(env)
        result, frames = evaluate_episode(
            env, policy, episode=1, seed=1000, max_steps=100, capture_frames=True
        )
        self.assertEqual(env.events[:2], [("environment_reset", 1000), ("policy_reset", None)])
        self.assertEqual(policy.observations, [0, 1, 2])
        self.assertEqual(result["steps"], 3)
        self.assertEqual(result["initial_reward"], 0.5)
        self.assertAlmostEqual(result["reward_gain"], 0.3)
        self.assertAlmostEqual(result["mean_step_reward"], 1.6 / 3)
        self.assertTrue(result["success"])
        self.assertEqual(len(frames), 4)

    def test_truncation_and_step_limit_stop_without_rendering(self):
        for truncate_at, limit, expected in ((2, 100, 2), (None, 1, 1)):
            with self.subTest(truncate_at=truncate_at, limit=limit):
                env = FakeEnvironment(truncate_at=truncate_at)
                result, frames = evaluate_episode(
                    env, FakePolicy(env), episode=2, seed=1001, max_steps=limit
                )
                self.assertEqual(result["steps"], expected)
                self.assertEqual(frames, [])
                self.assertEqual(env.render_calls, 0)

    def test_episode_summary_and_invalid_limits(self):
        results = [
            {"max_reward": 0.8, "reward_gain": 0.3, "success": True},
            {"max_reward": 0.4, "reward_gain": 0.1, "success": False},
        ]
        summary = summarize_episodes(results)
        self.assertAlmostEqual(summary["mean_max_reward"], 0.6)
        self.assertAlmostEqual(summary["mean_reward_gain"], 0.2)
        self.assertEqual(summary["success_rate"], 0.5)
        with self.assertRaises(ValueError):
            summarize_episodes([])
        with self.assertRaises(ValueError):
            env = FakeEnvironment()
            evaluate_episode(env, FakePolicy(env), episode=1, seed=0, max_steps=0)


if __name__ == "__main__":
    unittest.main()
