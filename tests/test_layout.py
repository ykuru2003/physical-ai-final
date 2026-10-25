"""Submission layout and evidence contracts; no live services required."""

import hashlib
import importlib.util
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "gazebo"
sys.path.insert(0, str(EXTENSION / "scripts"))


class LayoutTests(unittest.TestCase):
    def test_submission_has_all_runtime_entry_points(self):
        for name in (
            "project.ps1",
            "gazebo/compose.yaml",
            "gazebo/Dockerfile",
            "gazebo/scripts/destination_control.py",
            "gazebo/scripts/settings.py",
            "gazebo/scripts/project_commands.ps1",
            "gazebo/scripts/task_results.py",
            "gazebo/scripts/submission_check.py",
            "gazebo/scripts/record_submission.py",
        ):
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file())
        for name in ("experiments/pusht", "roboops", "workshop.ipynb"):
            self.assertFalse((ROOT / name).exists())

    def test_submission_python_sources_compile(self):
        for source in (EXTENSION / "scripts").glob("*.py"):
            compile(source.read_text(encoding="utf-8-sig"), str(source), "exec")

    def test_extension_evidence_matches_its_certified_runtime(self):
        spec = importlib.util.spec_from_file_location(
            "gazebo_layout_check", EXTENSION / "scripts/destination_control.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.ROOT, EXTENSION)
        registry = module.load_registry()
        destinations = registry["destinations"]
        self.assertGreaterEqual(len(destinations), 2)
        for destination in destinations:
            with self.subTest(destination=destination["id"]):
                evidence = destination.get("qualification")
                if evidence is None:
                    self.assertFalse(module.qualified(destination))
                    self.assertEqual(
                        destination["state"], "pending_current_runtime_qualification"
                    )
                    continue
                available = True
                for record in evidence["reports"]:
                    path = (EXTENSION / record["path"]).resolve()
                    self.assertTrue(path.is_relative_to(EXTENSION / "outputs"))
                    if not path.exists():
                        available = False
                        continue
                    self.assertEqual(
                        hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"]
                    )
                    self.assertTrue(
                        module.report_passes(
                            json.loads(path.read_text(encoding="utf-8")),
                            destination["goal"],
                        )
                    )
                current = evidence["fingerprint"] == module.fingerprint()
                self.assertEqual(module.qualified(destination), current and available)
        certificate = EXTENSION / "outputs/local-ai-validation.json"
        if certificate.exists():
            report = json.loads(certificate.read_text(encoding="utf-8"))
            expected = (
                report.get("status") == "PASS"
                and report.get("selector_sha256")
                == module.digest(EXTENSION / "scripts/destination_control.py")
                and report.get("validator_sha256")
                == module.digest(EXTENSION / "scripts/validate_local_ai.py")
                and report.get("language_signature")
                == module.language_signature(registry)
            )
            self.assertEqual(
                module.language_validated(
                    registry,
                    {
                        "model": report["model"],
                        "model_digest": report["model_digest"],
                    },
                ),
                expected,
            )
        else:
            self.assertFalse(
                module.language_validated(
                    registry,
                    {
                        "model": "qwen3:1.7b",
                        "model_digest": None,
                    },
                )
            )

    def test_robot_topics_match_world_bridge_and_runtime(self):
        topics = {
            "/robot/imu",
            "/robot/support_contacts",
            "/robot/obstacle_contacts",
            "/robot/ground_truth",
        }
        world = ET.parse(EXTENSION / "simulation/worlds/practice.sdf")
        self.assertTrue(
            topics.issubset({node.text for node in world.findall(".//topic")})
        )
        bridge = (EXTENSION / "simulation/config/bridge.yaml").read_text(
            encoding="utf-8"
        )
        for side in ("ros", "gz"):
            self.assertEqual(
                set(re.findall(side + r"_topic_name:\s*(/robot/[a-z_]+)", bridge)),
                topics,
            )
        for name, required in (
            ("navigate_to_goal.py", topics - {"/robot/ground_truth"}),
            ("evaluate_navigation.py", topics - {"/robot/imu"}),
            ("wait_for_sensors.py", {"/robot/imu"}),
        ):
            with self.subTest(script=name):
                source = (EXTENSION / "scripts" / name).read_text(encoding="utf-8")
                self.assertTrue(
                    required.issubset(set(re.findall(r"/robot/[a-z_]+", source)))
                )

    def test_summary_references_are_portable_and_scoped(self):
        report = json.loads(
            (EXTENSION / "outputs/navigation-verification.json").read_text(
                encoding="utf-8"
            )
        )
        for record in report["integration_results"]:
            path = Path(record["path"])
            self.assertFalse(path.is_absolute())
            self.assertTrue(
                (EXTENSION / path).resolve().is_relative_to(EXTENSION / "outputs")
            )


if __name__ == "__main__":
    unittest.main()
