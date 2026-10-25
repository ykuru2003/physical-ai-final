"""Success at the wrong goal, rejected inputs and unconfirmed stops must fail."""

import copy
import unittest

from task_results import navigation_succeeded
from tests.test_destination_control import valid_report


class TaskResultTests(unittest.TestCase):
    def setUp(self):
        self.audit = {
            "status": "PASS",
            "movement_started": True,
            "qualified": True,
            "language_validated": True,
            "destination": "east_station",
            "selection": {"destination_id": "east_station"},
            "goal": [3.0, 1.0],
            "world_evaluation": valid_report(),
            "final_stop": "CONFIRMED_STATIONARY",
        }

    def test_verified_result_passes_with_matching_constraints(self):
        self.assertTrue(navigation_succeeded(self.audit))
        self.assertTrue(
            navigation_succeeded(
                self.audit, destination="east_station", goal=[3.0, 1.0]
            )
        )

    def test_success_at_a_different_destination_is_not_the_requested_trial(self):
        self.assertFalse(navigation_succeeded(self.audit, destination="south_station"))
        self.assertFalse(navigation_succeeded(self.audit, goal=[1.0, -1.0]))
        self.audit["selection"]["destination_id"] = "south_station"
        self.assertFalse(navigation_succeeded(self.audit))

    def test_missing_or_unconfirmed_runtime_evidence_never_passes(self):
        for field in ("movement_started", "qualified", "language_validated"):
            audit = copy.deepcopy(self.audit)
            audit[field] = False
            with self.subTest(field=field):
                self.assertFalse(navigation_succeeded(audit))
        self.audit["final_stop"] = "UNCONFIRMED"
        self.assertFalse(navigation_succeeded(self.audit))

    def test_collision_is_rejected_even_if_top_level_status_says_pass(self):
        self.audit["world_evaluation"]["obstacle_collisions"] = ["contact"]
        self.assertFalse(navigation_succeeded(self.audit))

    def test_incomplete_or_malformed_audit_never_passes(self):
        for audit in (None, [], {}, {"selection": None}, {"status": "REJECTED"}):
            with self.subTest(audit=audit):
                self.assertFalse(navigation_succeeded(audit))


if __name__ == "__main__":
    unittest.main()
