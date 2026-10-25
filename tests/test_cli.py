"""The CLI help path must work before Torch, LeRobot, Gym or ROS are imported."""

import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class CommandHelpTests(unittest.TestCase):
    def test_evaluation_cli_preserves_failure_exit_codes(self):
        config = ModuleType("roboops.config")
        config.load_yaml = Mock(return_value={"test": "configuration"})
        for result in ("PASS", "FAIL"):
            evaluation = ModuleType("roboops.evaluation")
            evaluation.run_evaluation = Mock(return_value={"result": result})
            with (
                self.subTest(result=result),
                patch.dict(
                    sys.modules,
                    {
                        "roboops.config": config,
                        "roboops.evaluation": evaluation,
                    },
                ),
                patch.object(sys, "argv", ["roboops", "evaluate", "--save-video"]),
            ):
                if result == "FAIL":
                    with self.assertRaises(SystemExit) as error:
                        runpy.run_module("roboops", run_name="__main__")
                    self.assertEqual(error.exception.code, 1)
                else:
                    runpy.run_module("roboops", run_name="__main__")
                evaluation.run_evaluation.assert_called_once_with(
                    {"test": "configuration"}, save_video=True
                )

    def test_help_does_not_load_optional_runtime_packages(self):
        for name in ("download", "validate", "train", "evaluate"):
            with self.subTest(command=name):
                code = (
                    "import runpy,sys; from pathlib import Path; "
                    "sys.path.insert(0,str(Path('.').resolve())); "
                    f"sys.argv=['roboops','{name}','--help']; "
                    "\ntry: runpy.run_module('roboops',run_name='__main__')"
                    "\nexcept SystemExit as error: assert error.code==0"
                    "\nassert not any(n in sys.modules for n in ('torch','lerobot','gymnasium','rclpy'))"
                )
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
