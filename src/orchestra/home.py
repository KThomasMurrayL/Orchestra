from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .agents import build_config
from .process import opencode_command
from .skills import config_skill_paths


@dataclass(frozen=True)
class Home:
    base: Path
    config: Path
    plugin: Path
    inbox: Path
    plugin_ready: bool


def base_dir() -> Path:
    return Path(os.environ.get("ORCHESTRA_HOME", Path.home() / ".orchestra")).expanduser()


def write_config(config: Path, model: str | None) -> None:
    payload = build_config(model, config_skill_paths())
    config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def prepare_home(model: str | None = None) -> Home:
    base = base_dir()
    plugin_dir = base / "plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin = plugin_dir / "orchestra.ts"
    source = resources.files("orchestra").joinpath("assets/plugin/orchestra.ts")
    plugin.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    config = base / "opencode.json"
    write_config(config, model)
    (base / "skills").mkdir(parents=True, exist_ok=True)
    inbox = base / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    plugin_ready = _ensure_plugin_deps(base)
    return Home(base=base, config=config, plugin=plugin, inbox=inbox, plugin_ready=plugin_ready)


def _opencode_version() -> str | None:
    try:
        result = subprocess.run([opencode_command(), "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip().split()
    return output[0] if output else None


def _npm_install_plugin(base: Path) -> bool:
    version = _opencode_version()
    specs = [f"@opencode-ai/plugin@{version}"] if version else []
    specs.append("@opencode-ai/plugin")
    for spec in specs:
        try:
            result = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund", "--prefix", str(base), spec],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return True
    return False


def _ensure_plugin_deps(base: Path) -> bool:
    link = base / "node_modules"
    target = link / "@opencode-ai" / "plugin"
    if target.exists():
        return True
    if os.environ.get("ORCHESTRA_SKIP_PLUGIN_INSTALL") == "1":
        return False
    if link.is_symlink() and not link.exists():
        try:
            link.unlink()
        except OSError:
            pass
    vendor = Path.home() / ".config" / "opencode" / "node_modules"
    vendor_plugin = vendor / "@opencode-ai" / "plugin"
    if not link.exists() and vendor_plugin.exists():
        try:
            link.symlink_to(vendor, target_is_directory=True)
            return target.exists()
        except OSError:
            pass
    return _npm_install_plugin(base) and target.exists()
