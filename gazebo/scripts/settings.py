"""Repository-relative configuration shared by host-side navigation tools."""

import os
from pathlib import Path

GAZEBO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = GAZEBO_ROOT.parent


def setting(name, default):
    if name in os.environ:
        return os.environ[name]
    path = REPOSITORY_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return default


def default_model():
    return setting("OLLAMA_MODEL", "qwen3:1.7b")


def default_port():
    port = int(setting("OLLAMA_PORT", "11434"))
    if not 1024 <= port <= 65535:
        raise ValueError("OLLAMA_PORT must be between 1024 and 65535")
    return port


def compose_command(*arguments):
    command = ["docker", "compose", "--file", str(GAZEBO_ROOT / "compose.yaml")]
    env_file = REPOSITORY_ROOT / ".env"
    if env_file.exists():
        command += ["--env-file", str(env_file)]
    return command + list(arguments)
