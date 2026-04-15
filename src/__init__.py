"""Kindle EPUB Fixer"""

from .__version__ import __version__
from .core import process_epub, process_files

__all__ = ["__version__", "process_epub", "process_files"]
