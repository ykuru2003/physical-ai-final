"""Checkpoint loading, seeded PushT evaluation and result persistence."""

from __future__ import annotations

import importlib.metadata
import json
import os
import time
import warnings
from pathlib import Path
from typing import Any

import imageio.v3 as iio
import numpy as np
from lerobot.policies.act.modeling_act import ACTPolicy

from roboops.normalization import load_normalization
from roboops.policy import PushTPolicyRunner
from roboops.rollout import evaluate_episode, summarize_episodes


def run_evaluation(config: dict[str, Any], *, save_video: bool = False) -> dict[str, Any]:
    """Load a checkpoint, evaluate fixed seeds, then save metrics and optional video."""
    started_at = time.perf_counter()
    evaluation = config["evaluation"]
    if bool(evaluation["headless"]):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API.*",
        category=UserWarning,
    )
    import gym_pusht  # noqa: F401
    import gymnasium as gym

    checkpoint_dir = Path(evaluation["checkpoint"])
    if not checkpoint_dir.exists():
        raise FileNotFoundError(
            f"Checkpoint not found: {checkpoint_dir}. "
            "Run: python src/train.py --config configs/train_ci.yaml"
        )
    policy = ACTPolicy.from_pretrained(checkpoint_dir)
    policy.eval()
    stats = load_normalization(checkpoint_dir / "normalization.npz")
    training_metrics = json.loads(
        (checkpoint_dir / "training_metrics.json").read_text(encoding="utf-8")
    )

    episodes = int(evaluation["episodes"])
    max_steps = int(evaluation["max_steps"])
    seed = int(evaluation["seed"])
    save_video = save_video or bool(evaluation["save_video"])
    if episodes < 1 or max_steps < 1:
        raise ValueError("episodes and max_steps must be at least 1")
    runner = PushTPolicyRunner(policy, stats)
    frames: list[np.ndarray] = []
    episode_results: list[dict[str, Any]] = []
    env = gym.make(
        "gym_pusht/PushT-v0",
        obs_type="environment_state_agent_pos",
        render_mode="rgb_array" if save_video else None,
        max_episode_steps=max_steps,
        visualization_width=384,
        visualization_height=384,
    )

    print("## Official LeRobot ACT CI Evaluation")
    try:
        for episode in range(episodes):
            result, episode_frames = evaluate_episode(
                env,
                runner,
                episode=episode + 1,
                seed=seed + episode,
                max_steps=max_steps,
                capture_frames=save_video and episode == 0,
            )
            episode_results.append(result)
            frames.extend(episode_frames)
            print(
                f"Episode {episode + 1}/{episodes} | max_reward={result['max_reward']:.3f} "
                f"| reward_gain={result['reward_gain']:.3f} "
                f"| success={'yes' if result['success'] else 'no'}"
            )
    finally:
        env.close()

    if save_video and frames:
        video_path = Path(evaluation["video_path"])
        video_path.parent.mkdir(parents=True, exist_ok=True)
        iio.imwrite(video_path, np.stack(frames), fps=10, codec="libx264")
        print(f"Video: {video_path}")

    summary = summarize_episodes(episode_results)
    mean_reward = summary["mean_max_reward"]
    mean_reward_gain = summary["mean_reward_gain"]
    success_rate = summary["success_rate"]
    min_reward = float(evaluation["min_mean_reward"])
    min_reward_gain = float(evaluation["min_mean_reward_gain"])
    passed = mean_reward >= min_reward and mean_reward_gain >= min_reward_gain
    elapsed_seconds = time.perf_counter() - started_at
    metrics = {
        "result": "PASS" if passed else "FAIL",
        "architecture": "lerobot_act",
        "environment": "gym_pusht/PushT-v0",
        "checkpoint": str(checkpoint_dir),
        "dataset": training_metrics["dataset"],
        "model": training_metrics["model"],
        "versions": {
            "lerobot": importlib.metadata.version("lerobot"),
            "gym-pusht": importlib.metadata.version("gym-pusht"),
        },
        "episodes": episodes,
        "mean_max_reward": mean_reward,
        "mean_reward_gain": mean_reward_gain,
        "success_rate": success_rate,
        "elapsed_seconds": elapsed_seconds,
        "thresholds": {
            "min_mean_reward": min_reward,
            "min_mean_reward_gain": min_reward_gain,
        },
        "episode_results": episode_results,
    }
    metrics_path = Path(config["output"]["metrics"])
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Mean max reward: {mean_reward:.3f}")
    print(f"Mean reward gain: {mean_reward_gain:.3f}")
    print(f"Success rate: {success_rate:.0%}")
    print(f"Evaluation: {elapsed_seconds:.1f}s")
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    return metrics
