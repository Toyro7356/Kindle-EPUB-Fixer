#!/usr/bin/env python3
"""Build the Python repair backend used by the native WinUI frontend."""

import os
import subprocess
import sys

from src import __version__


def build() -> None:
    project_root = os.path.dirname(os.path.abspath(__file__))
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--name",
        "KindleEpubFixer.Backend",
        "--specpath",
        os.path.join(project_root, "build"),
        "main_backend.py",
    ]

    fonts_dir = os.path.join(project_root, "fonts")
    if os.path.isdir(fonts_dir):
        cmd.extend(["--add-data", f"{fonts_dir};fonts"])
    else:
        print("Warning: fonts directory not found, bundled font assets will be unavailable.")

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"\nBackend build finished. Version: {__version__}")
    print("Output: dist/KindleEpubFixer.Backend.exe")


if __name__ == "__main__":
    build()
