"""Reusable workshop modules. Importing data helpers does not load the ACT model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lerobot.policies.act.modeling_act import ACTPolicy

__all__ = ["build_act_policy"]


def build_act_policy(model_config: dict[str, Any]) -> ACTPolicy:
    """Compatibility entry point; import model dependencies when a policy is requested."""
    from roboops.policy import build_act_policy as build

    return build(model_config)
