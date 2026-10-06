from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import base_dir

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
FIELD = re.compile(r"^(name|description)\s*:\s*(.*)$", re.MULTILINE)

SKILL_TEMPLATE = """---
name: {name}
description: {description}
---

# {name}

Write the workflow you want Orchestra to follow here. Be concrete: say when the skill applies, the
steps to take, and any rules or checks. Orchestrators load matching skills and fold them into the
tasks they dispatch, and workers can load them too.
"""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    source: str


def user_skills_dir() -> Path:
    return base_dir() / "skills"


def _strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)//.*$", "", text)


def global_config_skill_paths() -> list[str]:
    paths: list[str] = []
    for name in ("opencode.json", "opencode.jsonc"):
        path = Path.home() / ".config" / "opencode" / name
        try:
            data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
        skills = data.get("skills") if isinstance(data, dict) else None
        if isinstance(skills, dict):
            for item in skills.get("paths") or []:
                if isinstance(item, str) and item.strip():
                    paths.append(item.strip())
    return paths


def config_skill_paths() -> list[str]:
    candidates = [str(user_skills_dir())]
    candidates.extend(global_config_skill_paths())
    result: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        expanded = str(Path(value).expanduser())
        if expanded not in seen:
            seen.add(expanded)
            result.append(expanded)
    return result


def _parse_skill(path: Path) -> Skill:
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        pass
    name = path.parent.name
    description = ""
    match = FRONTMATTER.match(text)
    if match:
        for field, value in FIELD.findall(match.group(1)):
            value = value.strip().strip('"').strip("'")
            if field == "name" and value:
                name = value
            elif field == "description":
                description = value.splitlines()[0].strip() if value else ""
    return Skill(name=name, description=description, path=path, source="")


def discover_skills(workspace: Path | None = None) -> list[Skill]:
    home = Path.home()
    roots: list[tuple[Path, str]] = [
        (user_skills_dir(), "orchestra"),
        (home / ".config" / "opencode" / "skill", "opencode"),
        (home / ".config" / "opencode" / "skills", "opencode"),
        (home / ".claude" / "skills", "claude"),
        (home / ".agents" / "skills", "agents"),
    ]
    for value in global_config_skill_paths():
        roots.append((Path(value).expanduser(), "opencode config"))
    if workspace is not None:
        roots.append((workspace / ".opencode" / "skill", "workspace"))
        roots.append((workspace / ".opencode" / "skills", "workspace"))
    skills: dict[str, Skill] = {}
    for root, label in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("SKILL.md")):
            skill = _parse_skill(path)
            skills.setdefault(skill.name, Skill(name=skill.name, description=skill.description, path=path, source=label))
    return sorted(skills.values(), key=lambda skill: skill.name)


def add_skill(name: str, description: str = "") -> Path:
    slug = name.strip().lower().replace(" ", "-")
    if not NAME_PATTERN.match(slug):
        raise ValueError("skill names may contain lowercase letters, numbers, and hyphens")
    directory = user_skills_dir() / slug
    path = directory / "SKILL.md"
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    directory.mkdir(parents=True, exist_ok=True)
    blurb = description.strip() or "Use when ... Describe what this skill does and when to use it."
    path.write_text(SKILL_TEMPLATE.format(name=slug, description=blurb), encoding="utf-8")
    return path


def remove_skill(name: str) -> Path:
    slug = name.strip().lower().replace(" ", "-")
    directory = user_skills_dir() / slug
    if not (directory / "SKILL.md").exists():
        raise FileNotFoundError(f"no user skill named {slug!r}")
    shutil.rmtree(directory)
    return directory
