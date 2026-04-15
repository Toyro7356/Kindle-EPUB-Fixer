from pathlib import Path
from typing import Callable

from lxml import etree

LogCallback = Callable[[str], None]


def _default_log(msg: str) -> None:
    pass


def write_xhtml_doc(doc: etree._ElementTree, path: Path) -> None:
    doc.write(str(path), encoding="utf-8", xml_declaration=True, doctype="<!DOCTYPE html>")
