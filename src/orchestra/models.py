from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from .process import opencode_command

ANSI = re.compile(r"\x1b\[[0-9;]*m")
FREE_PROVIDER = "opencode"
CACHE_TTL = 300.0

_CACHE: tuple[float, list[str]] | None = None


def base_dir() -> Path:
    return Path(os.environ.get("ORCHESTRA_HOME", Path.home() / ".orchestra")).expanduser()


def parse_models(output: str) -> list[str]:
    models: set[str] = set()
    for line in ANSI.sub("", output).splitlines():
        line = line.strip()
        if line and "/" in line and " " not in line:
            models.add(line)
    return sorted(models)


def list_models(ttl: float = CACHE_TTL) -> list[str]:
    global _CACHE
    if _CACHE is not None and ttl >= 0 and time.monotonic() - _CACHE[0] < ttl:
        return list(_CACHE[1])
    try:
        result = subprocess.run([opencode_command(), "models"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return list(_CACHE[1]) if _CACHE is not None else []
    models = parse_models(result.stdout)
    _CACHE = (time.monotonic(), models)
    return list(models)


def usable_models() -> tuple[list[str], int]:
    all_models = list_models()
    usable = [model for model in all_models if not model.startswith(f"{FREE_PROVIDER}/")]
    return usable, len(all_models) - len(usable)


def saved_model() -> str | None:
    try:
        text = (base_dir() / "model").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def save_model(model: str) -> None:
    path = base_dir() / "model"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.strip() + "\n", encoding="utf-8")


def global_config_model() -> str | None:
    for name in ("opencode.json", "opencode.jsonc"):
        path = Path.home() / ".config" / "opencode" / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("model"), str) and data["model"].strip():
            return data["model"].strip()
    return None


def authenticated_providers() -> list[str]:
    data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "opencode"
    try:
        data = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return [name for name, value in data.items() if isinstance(value, dict)]


def first_model_for(provider: str) -> str | None:
    try:
        result = subprocess.run(
            [opencode_command(), "models", provider],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in ANSI.sub("", result.stdout).splitlines():
        line = line.strip()
        if line.startswith(f"{provider}/"):
            return line
    return None


def resolve_model() -> str | None:
    for candidate in (saved_model(), global_config_model()):
        if candidate:
            return candidate
    for provider in authenticated_providers():
        model = first_model_for(provider)
        if model:
            return model
    return None
