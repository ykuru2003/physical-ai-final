"""Check existing command paths without importing ROS or starting services."""
import ast
from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    'check_environment.py', 'demo_drive.py', 'run_step2_once.py',
    'stop_step2.py', 'wait_step2_ready.py', 'complete_step3.py',
    'qualify_destinations.py', 'drive_to_goal.py', 'drive_to_goal_v2.py',
    'drive_to_goal_v3.py', 'drive_to_goal_v4.py',
)


class CommandTests(unittest.TestCase):
    def test_existing_commands_delegate_once_and_preserve_arguments(self):
        for filename in COMMANDS:
            with self.subTest(command=filename):
                path = ROOT / 'scripts' / filename
                tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                target = next(n for n in tree.body if isinstance(n, ast.ImportFrom))
                module = ModuleType(target.module)
                for symbol in target.names:
                    setattr(module, symbol.name, Mock(return_value=7))
                arguments = [str(path), '--example', 'value with spaces']
                with patch.dict(sys.modules, {target.module: module}), patch.object(sys, 'argv', arguments):
                    try:
                        runpy.run_path(str(path), run_name='__main__')
                    except SystemExit as error:
                        self.assertEqual(error.code, 7)
                    module.main.assert_called_once_with()
                    self.assertEqual(sys.argv, arguments)


if __name__ == '__main__':
    unittest.main()
