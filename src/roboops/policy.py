"""Build the official ACT model and adapt it to PushT observations/actions."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from lerobot.configs.types import FeatureType, PolicyFeature
from lerobot.policies.act.configuration_act import ACTConfig
from lerobot.policies.act.modeling_act import ACTPolicy

from roboops.normalization import denormalize_action as denormalize_action
from roboops.normalization import load_normalization as load_normalization
from roboops.normalization import normalize as normalize
from roboops.normalization import save_normalization as save_normalization
from roboops.schema import ACTION_KEY, AGENT_STATE_KEY, ENVIRONMENT_STATE_KEY, EXPECTED_SHAPES


def build_act_policy(model_config: dict[str, Any]) -> ACTPolicy:
    """LeRobot公式ACTをCI向けのstate-only構成で作ります。"""
    config = ACTConfig(
        input_features={
            AGENT_STATE_KEY: PolicyFeature(FeatureType.STATE, EXPECTED_SHAPES[AGENT_STATE_KEY]),
            ENVIRONMENT_STATE_KEY: PolicyFeature(
                FeatureType.ENV, EXPECTED_SHAPES[ENVIRONMENT_STATE_KEY]
            ),
        },
        output_features={
            ACTION_KEY: PolicyFeature(FeatureType.ACTION, EXPECTED_SHAPES[ACTION_KEY])
        },
        chunk_size=int(model_config["chunk_size"]),
        n_action_steps=1,
        pre_norm=True,
        dim_model=int(model_config["dim_model"]),
        n_heads=int(model_config["n_heads"]),
        dim_feedforward=int(model_config["dim_feedforward"]),
        n_encoder_layers=int(model_config["n_encoder_layers"]),
        n_decoder_layers=int(model_config["n_decoder_layers"]),
        use_vae=bool(model_config["use_vae"]),
        temporal_ensemble_coeff=float(model_config["temporal_ensemble_coeff"]),
        dropout=float(model_config["dropout"]),
        device="cpu",
    )
    return ACTPolicy(config)


class PushTPolicyRunner:
    """Adapt ACT's normalized tensor interface to raw PushT observations/actions."""

    def __init__(self, policy: ACTPolicy, stats: dict[str, dict[str, np.ndarray]]) -> None:
        self.policy = policy
        self.stats = stats

    def reset(self) -> None:
        self.policy.reset()

    def select_action(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        batch = {
            AGENT_STATE_KEY: torch.from_numpy(
                normalize(observation["agent_pos"], self.stats, AGENT_STATE_KEY)
            )
            .float()
            .unsqueeze(0),
            ENVIRONMENT_STATE_KEY: torch.from_numpy(
                normalize(observation["environment_state"], self.stats, ENVIRONMENT_STATE_KEY)
            )
            .float()
            .unsqueeze(0),
        }
        with torch.inference_mode():
            normalized_action = self.policy.select_action(batch)[0].cpu().numpy()
        return denormalize_action(normalized_action, self.stats)
