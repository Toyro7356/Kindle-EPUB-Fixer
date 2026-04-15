#!/usr/bin/env python3
"""PyInstaller 打包脚本"""

import os
import subprocess
import sys

import tkinterdnd2

from src import __version__


def build():
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "Kindle EPUB Fixer",
        "--icon", "NONE",
        "main_gui.py",
    ]

    # Bundle tkinterdnd2 native tcl/dll files
    tkdnd_dir = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")
    if os.path.isdir(tkdnd_dir):
        # PyInstaller --add-data syntax on Windows: SRC;DEST
        cmd.extend(["--add-data", f"{tkdnd_dir};tkinterdnd2\\tkdnd"])
    else:
        print("Warning: tkinterdnd2 tkdnd directory not found, drag-and-drop may not work in the bundled exe.")

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"\nBuild finished. Version: {__version__}")
    print("Output: dist/Kindle EPUB Fixer.exe")


if __name__ == "__main__":
    build()
