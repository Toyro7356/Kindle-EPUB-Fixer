"""Machine-readable backend used by the native WinUI frontend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import process_epub


def _emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=True), flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kindle EPUB Fixer backend")
    parser.add_argument("--input", help="Input EPUB path")
    parser.add_argument("--output", help="Output EPUB path or output directory")
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--version", action="store_true", help="Print backend version event")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.version:
        _emit("version", version=__version__)
        return

    if not args.input:
        _emit("error", message="Missing required argument: --input")
        sys.exit(2)

    input_path = Path(args.input).resolve()
    output_target = args.output or args.output_dir
    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        _emit("error", message=f"Input file does not exist: {input_path}")
        sys.exit(2)

    try:
        _emit("progress", status="分析中", progress=8)

        def log(message: str) -> None:
            _emit("log", message=message)

        output_path = process_epub(str(input_path), output_target, log=log)
        _emit("progress", status="完成", progress=100, output=output_path)
        _emit("done", output=output_path)
    except Exception as exc:
        _emit("error", message=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
