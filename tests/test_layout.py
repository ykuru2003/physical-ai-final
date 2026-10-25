"""Layout contracts requiring no ML packages or services."""

import hashlib
import importlib.util
import json
import re
import tomllib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "gazebo"


class LayoutTests(unittest.TestCase):
    def test_workshop_is_at_the_root(self):
        for name in (
            "roboops/__main__.py",
            "roboops/training.py",
            "roboops/evaluation.py",
            "roboops/data.py",
            "configs/train_ci.yaml",
            "configs/eval_ci.yaml",
            "workshop.ipynb",
            "Dockerfile",
            "uv.lock",
        ):
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file())
        self.assertFalse((ROOT / "workshop").exists())
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"], ["roboops"]
        )
        self.assertEqual(config["tool"]["pytest"]["ini_options"]["testpaths"], ["tests"])

    def test_promoted_sources_and_notebook_cells_compile(self):
        for source in (ROOT / "roboops").rglob("*.py"):
            compile(source.read_text(encoding="utf-8-sig"), str(source), "exec")
        notebook = json.loads((ROOT / "workshop.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        self.assertTrue(any(cell["cell_type"] == "code" for cell in notebook["cells"]))
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"notebook:{index}", "exec")
            self.assertFalse(
                any(item.get("output_type") == "error" for item in cell.get("outputs", []))
            )

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
                    self.assertEqual(destination["state"], "pending_current_runtime_qualification")
                    continue
                for record in evidence["reports"]:
                    path = EXTENSION / record["path"]
                    self.assertEqual(
                        hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"]
                    )
                    self.assertTrue(
                        module.report_passes(json.loads(path.read_text()), destination["goal"])
                    )
                current = evidence["fingerprint"] == module.fingerprint()
                self.assertEqual(module.qualified(destination), current)
                self.assertEqual(
                    destination["state"],
                    "qualified" if current else "pending_current_runtime_qualification",
                )
        certificate = EXTENSION / "outputs/local-ai-validation.json"
        if certificate.exists():
            report = json.loads(certificate.read_text(encoding="utf-8"))
            expected = (
                report.get("status") == "PASS"
                and report.get("controller_sha256")
                == module.digest(EXTENSION / "scripts/destination_control.py")
                and report.get("validator_sha256")
                == module.digest(EXTENSION / "scripts/validate_local_ai.py")
                and report.get("language_signature") == module.language_signature(registry)
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
        self.assertTrue(topics.issubset({node.text for node in world.findall(".//topic")}))
        bridge = (EXTENSION / "simulation/config/bridge.yaml").read_text(encoding="utf-8")
        for side in ("ros", "gz"):
            self.assertEqual(
                set(re.findall(side + r"_topic_name:\s*(/robot/[a-z_]+)", bridge)), topics
            )
        for name, required in (
            ("navigate_to_goal.py", topics - {"/robot/ground_truth"}),
            ("ros_driver.py", topics - {"/robot/ground_truth"}),
            ("evaluate_navigation.py", topics - {"/robot/imu"}),
            ("wait_for_sensors.py", {"/robot/imu"}),
        ):
            with self.subTest(script=name):
                source = (EXTENSION / "scripts" / name).read_text(encoding="utf-8")
                self.assertTrue(required.issubset(set(re.findall(r"/robot/[a-z_]+", source))))

    def test_summary_references_are_portable_and_scoped(self):
        report = json.loads(
            (EXTENSION / "outputs/navigation-verification.json").read_text(encoding="utf-8")
        )
        for record in report["integration_results"]:
            path = Path(record["path"])
            self.assertFalse(path.is_absolute())
            self.assertTrue((EXTENSION / path).resolve().is_relative_to(EXTENSION / "outputs"))


if __name__ == "__main__":
    unittest.main()
