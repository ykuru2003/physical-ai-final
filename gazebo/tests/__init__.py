"""Offline regression tests; all external services are mocked."""
from pathlib import Path

CACHE_ROOT = Path(__file__).resolve().parents[2] / ".cache" / "tests" / "gazebo"
