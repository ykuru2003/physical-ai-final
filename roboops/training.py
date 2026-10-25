"""ACT training: episode split, loaders, optimization and checkpoint reporting."""

from __future__ import annotations

import importlib.metadata
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from lerobot.policies.act.modeling_act import ACTPolicy
from torch.utils.data import DataLoader, TensorDataset

from roboops.data import (
    DatasetBundle,
    action_chunks,
    load_npz_dataset,
    normalization_stats,
    split_episode_indices,
)
from roboops.normalization import normalize, save_normalization
from roboops.policy import build_act_policy
from roboops.schema import ACTION_KEY, AGENT_STATE_KEY, ENVIRONMENT_STATE_KEY


def make_loader(
    bundle: DatasetBundle,
    indices: np.ndarray,
    stats: dict[str, dict[str, np.ndarray]],
    chunk_size: int,
    batch_size: int,
    shuffle: bool,
    seed: int,
) -> DataLoader:
    chunks, padding = action_chunks(bundle, indices, chunk_size)
    dataset = TensorDataset(
        torch.from_numpy(normalize(bundle.agent_state[indices], stats, AGENT_STATE_KEY)),
        torch.from_numpy(
            normalize(
                bundle.environment_state[indices],
                stats,
                ENVIRONMENT_STATE_KEY,
            )
        ),
        torch.from_numpy(normalize(chunks, stats, ACTION_KEY)),
        torch.from_numpy(padding),
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        generator=torch.Generator().manual_seed(seed),
    )


def act_batch(values: list[torch.Tensor]) -> dict[str, torch.Tensor]:
    state, environment, action, padding = values
    return {
        AGENT_STATE_KEY: state.float(),
        ENVIRONMENT_STATE_KEY: environment.float(),
        ACTION_KEY: action.float(),
        "action_is_pad": padding,
    }


def evaluate_loss(policy: ACTPolicy, loader: DataLoader) -> float:
    policy.eval()
    losses = []
    with torch.inference_mode():
        for values in loader:
            loss, _ = policy(act_batch(values))
            losses.append(float(loss.item()))
    return float(np.mean(losses))


def prepare_loaders(
    bundle: DatasetBundle,
    model_config: dict[str, Any],
    training: dict[str, Any],
) -> tuple[DataLoader, DataLoader, dict[str, dict[str, np.ndarray]]]:
    """Build train/validation loaders using statistics from training episodes only."""
    seed = int(training["seed"])
    train_indices, validation_indices = split_episode_indices(
        bundle,
        float(training["validation_ratio"]),
        seed,
    )
    stats = normalization_stats(bundle, train_indices)
    loader_args = {
        "bundle": bundle,
        "stats": stats,
        "chunk_size": int(model_config["chunk_size"]),
        "batch_size": int(training["batch_size"]),
        "seed": seed,
    }
    train_loader = make_loader(indices=train_indices, shuffle=True, **loader_args)
    validation_loader = make_loader(indices=validation_indices, shuffle=False, **loader_args)

    return train_loader, validation_loader, stats


def train_policy(
    policy: ACTPolicy,
    train_loader: DataLoader,
    validation_loader: DataLoader,
    training: dict[str, Any],
) -> tuple[list[dict[str, float | int]], int]:
    """Optimize the policy, respecting both the epoch limit and total update limit."""
    optimizer = torch.optim.AdamW(
        policy.parameters(),
        lr=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
    )
    epochs = int(training["epochs"])
    max_steps = int(training["max_steps"])
    history: list[dict[str, float | int]] = []
    global_step = 0

    for epoch in range(1, epochs + 1):
        policy.train()
        train_losses = []
        for values in train_loader:
            loss, _ = policy(act_batch(values))
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()
            train_losses.append(float(loss.detach().item()))
            global_step += 1
            if global_step >= max_steps:
                break
        train_loss = float(np.mean(train_losses))
        validation_loss = evaluate_loss(policy, validation_loader)
        history.append(
            {
                "epoch": epoch,
                "step": global_step,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
            }
        )
        print(
            f"Epoch {epoch:02d}/{epochs:02d} | step={global_step:03d} "
            f"| train_loss={train_loss:.4f} | validation_loss={validation_loss:.4f}"
        )
        if global_step >= max_steps:
            break

    return history, global_step


def run_training(config: dict[str, Any]) -> dict[str, Any]:
    """Run one configured training job and return the saved metrics."""
    started_at = time.perf_counter()
    training = config["training"]
    model_config = config["model"]
    seed = int(training["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(int(training["torch_threads"]))

    bundle = load_npz_dataset(config["dataset"]["path"])
    train_loader, validation_loader, stats = prepare_loaders(bundle, model_config, training)

    policy = build_act_policy(model_config)
    print("## Official LeRobot ACT CI Training")
    print(f"Dataset: {bundle.dataset_id} ({bundle.episode_count} episodes)")
    print(f"Parameters: {sum(parameter.numel() for parameter in policy.parameters()):,}")
    history, global_step = train_policy(policy, train_loader, validation_loader, training)

    output = config["output"]
    checkpoint_dir = Path(output["checkpoint"])
    metrics_path = Path(output["metrics"])
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(checkpoint_dir)
    save_normalization(checkpoint_dir / "normalization.npz", stats)

    elapsed_seconds = time.perf_counter() - started_at
    metrics = {
        "result": "PASS",
        "architecture": "lerobot_act",
        "device": "cpu",
        "checkpoint": str(checkpoint_dir),
        "dataset": {
            "id": bundle.dataset_id,
            "revision": bundle.dataset_revision,
            "episodes": bundle.episode_count,
            "frames": bundle.frame_count,
        },
        "model": model_config,
        "training": training,
        "steps": global_step,
        "parameters": sum(parameter.numel() for parameter in policy.parameters()),
        "elapsed_seconds": elapsed_seconds,
        "history": history,
        "versions": {"lerobot": importlib.metadata.version("lerobot")},
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    checkpoint_size = sum(
        path.stat().st_size for path in checkpoint_dir.glob("*") if path.is_file()
    )
    print(f"Checkpoint: {checkpoint_dir} ({checkpoint_size / 1024:.1f} KiB)")
    print(f"Training: {elapsed_seconds:.1f}s")
    print("RESULT: PASS")
    return metrics
