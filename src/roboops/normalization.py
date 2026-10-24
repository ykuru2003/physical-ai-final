"""Convert between raw PushT coordinates and normalized policy features."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def save_normalization(
    path: str | Path,
    stats: dict[str, dict[str, np.ndarray]],
) -> None:
    np.savez(
        path,
        **{
            f"{feature}.{stat}": value
            for feature, values in stats.items()
            for stat, value in values.items()
        },
    )


def load_normalization(path: str | Path) -> dict[str, dict[str, np.ndarray]]:
    stats: dict[str, dict[str, np.ndarray]] = {}
    with np.load(path, allow_pickle=False) as values:
        for key in values.files:
            feature, stat = key.rsplit(".", 1)
            stats.setdefault(feature, {})[stat] = np.asarray(values[key], dtype=np.float32)
    return stats


def normalize(
    value: np.ndarray,
    stats: dict[str, dict[str, np.ndarray]],
    feature: str,
) -> np.ndarray:
    return (np.asarray(value, dtype=np.float32) - stats[feature]["mean"]) / stats[feature]["std"]


def denormalize_action(
    value: np.ndarray,
    stats: dict[str, dict[str, np.ndarray]],
) -> np.ndarray:
    action = value * stats["action"]["std"] + stats["action"]["mean"]
    return np.clip(action, 0.0, 512.0).astype(np.float32)
