"""Layout contracts requiring no ML packages or services."""

import importlib.util
import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extensions" / "gazebo"


class LayoutTests(unittest.TestCase):
    def test_workshop_is_at_the_root(self):
        for name in (
            "src/roboops/__main__.py",
            "src/roboops/training.py",
            "src/roboops/evaluation.py",
            "src/roboops/data.py",
            "configs/train_ci.yaml",
            "configs/eval_ci.yaml",
            "notebooks/01_roboops_workshop.ipynb",
            "Dockerfile",
            "uv.lock",
        ):
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file())
        self.assertFalse((ROOT / "workshop").exists())
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"], ["src/roboops"]
        )
        self.assertEqual(config["tool"]["pytest"]["ini_options"]["testpaths"], ["tests"])

    def test_promoted_sources_and_notebook_cells_compile(self):
        for source in (ROOT / "src").rglob("*.py"):
            compile(source.read_text(encoding="utf-8-sig"), str(source), "exec")
        notebook = json.loads(
            (ROOT / "notebooks/01_roboops_workshop.ipynb").read_text(encoding="utf-8")
        )
        self.assertEqual(notebook["nbformat"], 4)
        self.assertTrue(any(cell["cell_type"] == "code" for cell in notebook["cells"]))
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"notebook:{index}", "exec")
            self.assertFalse(
                any(item.get("output_type") == "error" for item in cell.get("outputs", []))
            )

    def test_extension_certificates_survive_relocation(self):
        spec = importlib.util.spec_from_file_location(
            "gazebo_layout_check", EXTENSION / "scripts/destination_control.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.ROOT, EXTENSION)
        registry = module.load_registry()
        destinations = [d for d in registry["destinations"] if d["state"] == "qualified"]
        self.assertGreaterEqual(len(destinations), 2)
        for destination in destinations:
            with self.subTest(destination=destination["id"]):
                self.assertTrue(module.qualified(destination))
        report = json.loads(
            (EXTENSION / "outputs/local-ai-validation.json").read_text(encoding="utf-8")
        )
        self.assertTrue(
            module.language_validated(
                registry,
                {
                    "model": report["model"],
                    "model_digest": report["model_digest"],
                },
            )
        )

    def test_summary_references_are_portable_and_scoped(self):
        report = json.loads(
            (EXTENSION / "outputs/step3-final-verification.json").read_text(encoding="utf-8")
        )
        for record in report["integration_results"]:
            path = Path(record["path"])
            self.assertFalse(path.is_absolute())
            self.assertTrue((EXTENSION / path).resolve().is_relative_to(EXTENSION / "outputs"))


if __name__ == "__main__":
    unittest.main()
