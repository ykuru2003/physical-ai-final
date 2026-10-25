"""Shared success criteria for submission trials and recorded navigation runs."""

import destination_control as dc


def navigation_succeeded(audit, *, destination=None, goal=None):
    """Require real selection, matching navigation evidence and confirmed final stop.

    Optional destination/goal constraints keep a scripted trial from passing when
    the robot reached a different registered destination successfully.
    """
    if not isinstance(audit, dict):
        return False
    selection = audit.get("selection")
    if not isinstance(selection, dict):
        return False
    selected_id = audit.get("destination")
    if not isinstance(selected_id, str) or not selected_id:
        return False
    if destination is not None and selected_id != destination:
        return False
    if goal is not None and audit.get("goal") != goal:
        return False
    return (
        audit.get("status") == "PASS"
        and audit.get("movement_started") is True
        and audit.get("qualified") is True
        and audit.get("language_validated") is True
        and selected_id == selection.get("destination_id")
        and dc.report_passes(audit.get("world_evaluation", {}), audit.get("goal"))
        and audit.get("final_stop") == "CONFIRMED_STATIONARY"
    )
