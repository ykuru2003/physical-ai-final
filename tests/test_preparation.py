"""Data and normalization contracts, using synthetic data without downloads or model imports."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from roboops.data import (
    DatasetBundle,
    action_chunks,
    load_npz_dataset,
    normalization_stats,
    split_episode_indices,
)
from roboops.normalization import (
    denormalize_action,
    load_normalization,
    normalize,
    save_normalization,
)
from roboops.validation import validate

ROOT = Path(__file__).resolve().parents[1]


def sample_bundle(episode_count=4):
    rows = episode_count * 5
    return DatasetBundle(
        agent_state=np.arange(rows * 2, dtype=np.float32).reshape(rows, 2),
        environment_state=np.zeros((rows, 16), dtype=np.float32),
        action=np.arange(rows * 2, dtype=np.float32).reshape(rows, 2),
        episode_index=np.repeat(np.arange(episode_count), 5),
        frame_index=np.tile(np.arange(5), episode_count),
    )


class PreparationTests(unittest.TestCase):
    def test_episode_split_is_deterministic_and_statistics_exclude_validation(self):
        bundle = sample_bundle()
        training, validation = split_episode_indices(bundle, 0.25, 42)
        self.assertEqual(len(training), 15)
        self.assertEqual(len(validation), 5)
        self.assertEqual(
            set(bundle.episode_index[training]) & set(bundle.episode_index[validation]), set()
        )
        repeated = split_episode_indices(bundle, 0.25, 42)
        np.testing.assert_array_equal(training, repeated[0])
        bundle.agent_state[validation] = 10000
        stats = normalization_stats(bundle, training)
        np.testing.assert_allclose(
            stats["observation.state"]["mean"], bundle.agent_state[training].mean(0)
        )
        self.assertLess(stats["observation.state"]["mean"].max(), 10000)
        self.assertTrue((stats["observation.environment_state"]["std"] > 0).all())

    def test_invalid_splits_fail_early_and_both_sets_remain_nonempty(self):
        for ratio in (0.0, 1.0, -1.0, float("nan")):
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                split_episode_indices(sample_bundle(), ratio, 42)
        with self.assertRaises(ValueError):
            split_episode_indices(sample_bundle(1), 0.2, 42)
        training, validation = split_episode_indices(sample_bundle(2), 0.99, 42)
        self.assertGreater(len(training), 0)
        self.assertGreater(len(validation), 0)

    def test_chunks_follow_frame_order_and_repeat_last_action_only_for_padding(self):
        bundle = DatasetBundle(
            agent_state=np.zeros((4, 2)),
            environment_state=np.zeros((4, 16)),
            action=np.arange(8, dtype=np.float32).reshape(4, 2),
            episode_index=np.array([0, 1, 0, 1]),
            frame_index=np.array([1, 1, 0, 0]),
        )
        chunks, padding = action_chunks(bundle, np.array([2, 3]), 3)
        np.testing.assert_array_equal(chunks[0], bundle.action[[2, 0, 0]])
        np.testing.assert_array_equal(chunks[1], bundle.action[[3, 1, 1]])
        self.assertEqual(padding.tolist(), [[False, False, True], [False, False, True]])

    def test_dataset_and_normalization_round_trip(self):
        fixture = ROOT / ".cache/test-runs"
        fixture.mkdir(parents=True, exist_ok=True)
        bundle = sample_bundle()
        with tempfile.TemporaryDirectory(dir=fixture) as folder:
            path = Path(folder) / "data.npz"
            np.savez(
                path,
                **{
                    "observation.state": bundle.agent_state,
                    "observation.environment_state": bundle.environment_state,
                    "action": bundle.action,
                    "episode_index": bundle.episode_index,
                    "dataset_id": np.asarray("test/source"),
                },
            )
            loaded = load_npz_dataset(path)
            self.assertEqual(loaded.dataset_id, "test/source")
            np.testing.assert_array_equal(loaded.frame_index, np.arange(bundle.frame_count))
            stats = normalization_stats(bundle, np.arange(bundle.frame_count))
            path = Path(folder) / "normalization.npz"
            save_normalization(path, stats)
            restored = load_normalization(path)
            for feature, values in stats.items():
                for name, expected in values.items():
                    np.testing.assert_array_equal(restored[feature][name], expected)
            np.testing.assert_allclose(
                normalize(bundle.action, stats, "action").mean(0), 0, atol=1e-6
            )
            extreme = denormalize_action(np.array([-1e8, 1e8]), stats)
            np.testing.assert_array_equal(extreme, [0.0, 512.0])

    def test_validation_preserves_named_checks_and_rejects_broken_data(self):
        valid = {
            "observation.state": np.ones((5, 2)),
            "observation.environment_state": np.ones((5, 16)),
            "action": np.ones((5, 2)),
            "episode_index": np.zeros(5, dtype=int),
        }
        checks = validate(valid)
        self.assertEqual(len(checks), 7)
        self.assertTrue(all(check.passed for check in checks))
        for key, value in (
            ("action", np.full((5, 2), np.nan)),
            ("action", np.ones((5, 3))),
            ("observation.state", np.full((5, 2), 2048.0)),
        ):
            with self.subTest(key=key, shape=value.shape):
                self.assertFalse(
                    all(check.passed for check in validate(dict(valid, **{key: value})))
                )
        self.assertFalse(any(check.passed for check in validate({})))


if __name__ == "__main__":
    unittest.main()
