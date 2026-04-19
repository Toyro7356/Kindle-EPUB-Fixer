#!/usr/bin/env python3
"""PyInstaller build script."""

import os
import subprocess
import sys

import tkinterdnd2

from src import __version__


def build() -> None:
    project_root = os.path.dirname(os.path.abspath(__file__))
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name",
        "Kindle EPUB Fixer",
        "--icon",
        "NONE",
        "main_gui.py",
    ]

    tkdnd_dir = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")
    if os.path.isdir(tkdnd_dir):
        cmd.extend(["--add-data", f"{tkdnd_dir};tkinterdnd2\\tkdnd"])
    else:
        print("Warning: tkinterdnd2 tkdnd directory not found, drag-and-drop may not work in the bundled exe.")

    fonts_dir = os.path.join(project_root, "fonts")
    if os.path.isdir(fonts_dir):
        cmd.extend(["--add-data", f"{fonts_dir};fonts"])
    else:
        print("Warning: fonts directory not found, bundled font assets will be unavailable in the exe.")

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"\nBuild finished. Version: {__version__}")
    print("Output: dist/Kindle EPUB Fixer.exe")


if __name__ == "__main__":
    build()
