from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__


def _handle_skills(args: argparse.Namespace) -> int:
    from .skills import add_skill, discover_skills, remove_skill, user_skills_dir

    command = args.skills_command
    if command == "path":
        print(user_skills_dir())
        return 0
    if command == "add":
        try:
            path = add_skill(args.name, args.description or "")
        except (ValueError, FileExistsError) as exc:
            print(f"orchestra: {exc}", file=sys.stderr)
            return 1
        print(f"created {path}")
        print(f"edit it, then restart orchestra. list skills with: orchestra skills list")
        return 0
    if command == "remove":
        try:
            path = remove_skill(args.name)
        except FileNotFoundError as exc:
            print(f"orchestra: {exc}", file=sys.stderr)
            return 1
        print(f"removed {path}")
        return 0

    workspace = Path(args.dir).expanduser().resolve()
    skills = discover_skills(workspace)
    if not skills:
        print(f"no skills found. add one with: orchestra skills add <name>")
        print(f"user skills live in: {user_skills_dir()}")
        return 0
    name_width = max(len(skill.name) for skill in skills)
    source_width = max(len(skill.source) for skill in skills)
    print(f"{len(skills)} skill(s) visible to orchestrators and workers:")
    for skill in skills:
        description = skill.description or "(no description)"
        if len(description) > 72:
            description = description[:69] + "..."
        print(f"  {skill.name:<{name_width}}  {skill.source:<{source_width}}  {description}")
    print(f"\nuser skills live in: {user_skills_dir()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orchestra",
        description="Talk to one planner agent; it dispatches real worker agent instances you can watch.",
    )
    parser.add_argument("--version", action="version", version=f"orchestra {__version__}")
    parser.add_argument("--dir", default=".", help="workspace directory the agents operate in (default: current directory)")
    parser.add_argument("--model", default=None, help="model override for every agent, e.g. provider/model")
    parser.add_argument(
        "--effort",
        default=None,
        help="reasoning effort passed to opencode as --variant (minimal, low, medium, high, max)",
    )
    parser.add_argument("--max-workers", type=int, default=4, help="maximum concurrently running workers (default: 4)")
    parser.add_argument("--no-voice", action="store_true", help="disable speech-to-text input")
    parser.add_argument("--check-voice", action="store_true", help="diagnose microphone and speech-to-text setup, then exit")

    subparsers = parser.add_subparsers(dest="command")
    skills_parser = subparsers.add_parser("skills", help="manage skills available to orchestrators and workers")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")
    skills_subparsers.add_parser("list", help="list skills Orchestra can see")
    skills_subparsers.add_parser("path", help="print the user skills directory")
    add_parser = skills_subparsers.add_parser("add", help="create a new skill template")
    add_parser.add_argument("name")
    add_parser.add_argument("--description", default="", help="one-line description of when to use the skill")
    remove_parser = skills_subparsers.add_parser("remove", help="delete a skill from the user skills directory")
    remove_parser.add_argument("name")

    args = parser.parse_args(argv)

    if args.command == "skills":
        return _handle_skills(args)

    if args.check_voice:
        from .voice import voice_diagnostics

        return voice_diagnostics()

    workspace = Path(args.dir).expanduser().resolve()
    if not workspace.is_dir():
        print(f"orchestra: not a directory: {workspace}", file=sys.stderr)
        return 2
    if shutil.which("opencode") is None:
        print("orchestra: the 'opencode' CLI was not found on PATH", file=sys.stderr)
        return 2
    if args.max_workers < 1:
        print("orchestra: --max-workers must be >= 1", file=sys.stderr)
        return 2

    from .app import OrchestraApp
    from .effort import resolve_effort
    from .models import resolve_model

    model = args.model or resolve_model()
    effort = args.effort or resolve_effort()
    app = OrchestraApp(
        workspace=workspace,
        model=model,
        effort=effort,
        voice_enabled=not args.no_voice,
        max_workers=args.max_workers,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
