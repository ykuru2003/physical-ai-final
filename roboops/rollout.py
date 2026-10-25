"""PushT rollout and scoring, independent of Torch, LeRobot and Gym imports."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np


class EvaluationPolicy(Protocol):
    """Policy interface used by rollout: reset state, then return raw action coordinates."""

    def reset(self) -> None: ...

    def select_action(self, observation: dict[str, np.ndarray]) -> np.ndarray: ...


def evaluate_episode(
    env: Any,
    policy: EvaluationPolicy,
    *,
    episode: int,
    seed: int,
    max_steps: int,
    capture_frames: bool = False,
) -> tuple[dict[str, Any], list[np.ndarray]]:
    """Evaluate one seeded episode; reward gain is relative to initial goal coverage."""
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    observation, _ = env.reset(seed=seed)
    policy.reset()
    initial_coverage = env.unwrapped._get_coverage()
    initial_reward = float(np.clip(initial_coverage / env.unwrapped.success_threshold, 0.0, 1.0))
    maximum_reward = initial_reward
    reward_sum = 0.0
    success = False
    steps = 0
    frames = [np.asarray(env.render())] if capture_frames else []
    for _ in range(max_steps):
        action = policy.select_action(observation)
        observation, reward, terminated, truncated, info = env.step(action)
        steps += 1
        reward_sum += float(reward)
        maximum_reward = max(maximum_reward, float(reward))
        success = success or bool(info.get("is_success", False))
        if capture_frames:
            frames.append(np.asarray(env.render()))
        if terminated or truncated:
            break
    return {
        "episode": episode,
        "seed": seed,
        "steps": steps,
        "initial_reward": initial_reward,
        "max_reward": maximum_reward,
        "reward_gain": maximum_reward - initial_reward,
        "mean_step_reward": reward_sum / max(steps, 1),
        "success": success,
    }, frames


def summarize_episodes(episode_results: list[dict[str, Any]]) -> dict[str, float]:
    """Keep rollout measurements distinct from the configured PASS/FAIL thresholds."""
    if not episode_results:
        raise ValueError("Evaluation requires at least one episode")
    return {
        "mean_max_reward": float(np.mean([item["max_reward"] for item in episode_results])),
        "mean_reward_gain": float(np.mean([item["reward_gain"] for item in episode_results])),
        "success_rate": float(np.mean([item["success"] for item in episode_results])),
    }
