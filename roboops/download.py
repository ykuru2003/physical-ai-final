"""Pinned LeRobot dataset download, cache checks and NPZ materialization."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

import numpy as np

from roboops.schema import DATASET_ID, DATASET_REVISION, EXPECTED_SHAPES

# Upstream LeRobot paths -> flat, descriptive source filenames.
DATASET_FILES = {
    "meta/info.json": "info.json",
    "meta/stats.json": "stats.json",
    "meta/tasks.parquet": "tasks.parquet",
    "meta/episodes/chunk-000/file-000.parquet": "episodes.parquet",
    "data/chunk-000/file-000.parquet": "frames.parquet",
}


def _to_numpy(value: object, dtype: np.dtype) -> np.ndarray:
    import torch

    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy().astype(dtype, copy=False)
    return np.asarray(value, dtype=dtype)


def prepare_source(raw_root: Path, *, cache_root: Path = Path(".cache/lerobot")) -> Path:
    """Verify flat source files and return a disposable LeRobot-compatible root.

    Native chunk/meta directories are generated only in the cache. The source
    manifest binds the readable local filenames to their pinned revision/hashes.
    """
    native_root = cache_root
    if native_root.resolve().is_relative_to(raw_root.resolve()):
        raise ValueError("LeRobot cache must stay outside the source directory")
    manifest_path = raw_root / "source.json"
    valid = False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        valid = (
            manifest["dataset_id"] == DATASET_ID
            and manifest["dataset_revision"] == DATASET_REVISION
            and all(
                hashlib.sha256((raw_root / name).read_bytes()).hexdigest()
                == manifest["files"][name]
                for name in DATASET_FILES.values()
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        pass

    if not valid:
        from huggingface_hub import hf_hub_download

        raw_root.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for upstream, filename in DATASET_FILES.items():
            cached = hf_hub_download(
                repo_id=DATASET_ID,
                filename=upstream,
                repo_type="dataset",
                revision=DATASET_REVISION,
            )
            target = raw_root / filename
            shutil.copyfile(cached, target)
            hashes[filename] = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest = {
            "dataset_id": DATASET_ID,
            "dataset_revision": DATASET_REVISION,
            "files": hashes,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for upstream, filename in DATASET_FILES.items():
        target = native_root / upstream
        if (
            not target.exists()
            or hashlib.sha256(target.read_bytes()).hexdigest() != manifest["files"][filename]
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(raw_root / filename, target)
    return native_root


def _cache_matches(output: Path, manifest_path: Path, requested_episodes: int) -> bool:
    if not output.exists() or not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        manifest.get("dataset_id") == DATASET_ID
        and manifest.get("dataset_revision") == DATASET_REVISION
        and manifest.get("requested_episodes", manifest.get("episodes")) == requested_episodes
    )


def download_dataset(
    output: Path, raw_root: Path, max_episodes: int = 60, *, force: bool = False
) -> None:
    """Download pinned state-only files and materialize the requested episode subset."""
    # この教材は動画を取得しないため、利用しないTorchCodecのfallback警告は表示しない。
    logging.getLogger("lerobot.utils.import_utils").setLevel(logging.ERROR)
    # 公開Datasetは未認証でも取得できるため、rate-limit案内で初学者を迷わせない。
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
    from lerobot.datasets import LeRobotDataset, LeRobotDatasetMetadata

    if max_episodes < 1:
        raise ValueError("max_episodes must be at least 1")
    manifest_path = output.with_suffix(".manifest.json")
    if not force and _cache_matches(output, manifest_path, max_episodes):
        print(f"Dataset already exists: {output}")
        print("Cached revision and episode count match the request.")
        return

    print("## Dataset Download")
    print(f"Source: https://huggingface.co/datasets/{DATASET_ID}")
    print(f"Pinned revision: {DATASET_REVISION[:12]}")

    native_root = prepare_source(raw_root)
    metadata = LeRobotDatasetMetadata(
        DATASET_ID,
        root=native_root,
        revision=DATASET_REVISION,
    )
    episode_count = min(max_episodes, metadata.total_episodes)
    episodes = list(range(episode_count))
    dataset = LeRobotDataset(
        DATASET_ID,
        root=native_root,
        episodes=episodes,
        revision=DATASET_REVISION,
        download_videos=False,
    )

    agent_states: list[np.ndarray] = []
    environment_states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    episode_indices: list[int] = []
    frame_indices: list[int] = []
    for sample in dataset:
        agent_states.append(_to_numpy(sample["observation.state"], np.float32))
        environment_states.append(_to_numpy(sample["observation.environment_state"], np.float32))
        actions.append(_to_numpy(sample["action"], np.float32))
        episode_indices.append(int(_to_numpy(sample["episode_index"], np.int64).item()))
        frame_indices.append(int(_to_numpy(sample["frame_index"], np.int64).item()))

    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        **{
            "observation.state": np.stack(agent_states),
            "observation.environment_state": np.stack(environment_states),
            "action": np.stack(actions),
            "episode_index": np.asarray(episode_indices, dtype=np.int64),
            "frame_index": np.asarray(frame_indices, dtype=np.int64),
            "dataset_id": np.asarray(DATASET_ID),
            "dataset_revision": np.asarray(DATASET_REVISION),
            "fps": np.asarray(metadata.fps, dtype=np.int64),
        },
    )
    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_revision": DATASET_REVISION,
        "source_url": f"https://huggingface.co/datasets/{DATASET_ID}",
        "requested_episodes": max_episodes,
        "episodes": episode_count,
        "frames": len(actions),
        "features": {key: list(shape) for key, shape in EXPECTED_SHAPES.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Episodes: {episode_count}")
    print(f"Frames: {len(actions)}")
    print(f"Saved: {output}")
    print("RESULT: PASS")
