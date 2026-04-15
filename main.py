#!/usr/bin/env python3
"""命令行入口：python main.py <input.epub> [output.epub]"""

import sys

from src import __version__
from src.core import process_epub


def cli() -> None:
    if len(sys.argv) < 2:
        print(f"Kindle EPUB Fixer v{__version__}")
        print(f"用法: python {sys.argv[0]} <input.epub> [output.epub]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    result = process_epub(input_file, output_file, log=lambda msg: print(f"[INFO] {msg}"))
    print(f"处理完成: {result}")


if __name__ == "__main__":
    cli()
