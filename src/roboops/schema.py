"""PushT field names, shapes and pinned dataset shared by all workshop commands."""

from pathlib import Path

AGENT_STATE_KEY = "observation.state"
ENVIRONMENT_STATE_KEY = "observation.environment_state"
ACTION_KEY = "action"
EPISODE_KEY = "episode_index"
FRAME_KEY = "frame_index"
REQUIRED_KEYS = (AGENT_STATE_KEY, ENVIRONMENT_STATE_KEY, ACTION_KEY, EPISODE_KEY)
EXPECTED_SHAPES = {AGENT_STATE_KEY: (2,), ENVIRONMENT_STATE_KEY: (16,), ACTION_KEY: (2,)}

DATASET_ID = "lerobot/pusht_keypoints"
DATASET_REVISION = "ace8c161a68bc025c21a5f29f85b86a9a2c5e64b"
DEFAULT_DATA = Path("data/processed/pusht_keypoints.npz")
DEFAULT_RAW_ROOT = Path("data/raw/lerobot_pusht_keypoints") / DATASET_REVISION
