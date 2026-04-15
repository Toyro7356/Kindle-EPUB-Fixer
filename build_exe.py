#!/usr/bin/env python3
"""PyInstaller 打包脚本"""

import subprocess
import sys

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
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"\nBuild finished. Version: {__version__}")
    print("Output: dist/Kindle EPUB Fixer.exe")


if __name__ == "__main__":
    build()
