from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orchestra",
        description="Talk to one planner agent; it dispatches real worker agent instances you can watch.",
    )
    parser.add_argument("--version", action="version", version=f"orchestra {__version__}")
    parser.add_argument("--dir", default=".", help="workspace directory the agents operate in (default: current directory)")
    parser.add_argument("--model", default=None, help="model override for every agent, e.g. provider/model")
    parser.add_argument("--max-workers", type=int, default=4, help="maximum concurrently running workers (default: 4)")
    parser.add_argument("--no-voice", action="store_true", help="disable speech-to-text input")
    args = parser.parse_args(argv)

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
    from .models import resolve_model

    model = args.model or resolve_model()
    app = OrchestraApp(
        workspace=workspace,
        model=model,
        voice_enabled=not args.no_voice,
        max_workers=args.max_workers,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
