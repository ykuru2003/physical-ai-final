"""Configuration precedence and working-directory-independent Compose commands."""

from tests import CACHE_ROOT
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        cache = CACHE_ROOT / 'test-runs'
        cache.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_environment_overrides_file_and_file_overrides_default(self):
        (self.root / ".env").write_text(
            'OLLAMA_MODEL="local-test"\nOLLAMA_PORT=12345\n', encoding="utf-8"
        )
        with (
            patch.object(settings, "REPOSITORY_ROOT", self.root),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(settings.default_model(), "local-test")
            self.assertEqual(settings.default_port(), 12345)
            with patch.dict(os.environ, {"OLLAMA_MODEL": "env-test"}):
                self.assertEqual(settings.default_model(), "env-test")

    def test_invalid_port_is_rejected(self):
        with patch.dict(os.environ, {"OLLAMA_PORT": "80"}):
            with self.assertRaises(ValueError):
                settings.default_port()

    def test_compose_uses_absolute_paths_and_shared_environment(self):
        (self.root / ".env").write_text("OLLAMA_MODEL=test\n", encoding="utf-8")
        with (
            patch.object(settings, "REPOSITORY_ROOT", self.root),
            patch.object(settings, "GAZEBO_ROOT", self.root / "gazebo"),
        ):
            cmd = settings.compose_command(
                "exec", "-T", "simulator", "echo", "one argument; unchanged"
            )
        self.assertEqual(
            cmd[:4],
            ["docker", "compose", "--file", str(self.root / "gazebo/compose.yaml")],
        )
        self.assertEqual(cmd[4:6], ["--env-file", str(self.root / ".env")])
        self.assertEqual(cmd[-1], "one argument; unchanged")


if __name__ == "__main__":
    unittest.main()
