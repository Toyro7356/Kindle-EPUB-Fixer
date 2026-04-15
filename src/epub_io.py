import os
import zipfile
from pathlib import Path

from lxml import etree

from .constants import NSMAP


def unpack_epub(epub_path: str, temp_dir: str) -> None:
    with zipfile.ZipFile(epub_path, "r") as zf:
        zf.extractall(temp_dir)


def repack_epub(temp_dir: str, output_path: str) -> None:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype_path = Path(temp_dir) / "mimetype"
        if mimetype_path.exists():
            zf.write(str(mimetype_path), "mimetype", compress_type=zipfile.ZIP_STORED)
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d != "__MACOSX"]
            for file in files:
                abs_path = Path(root) / file
                arcname = str(abs_path.relative_to(temp_dir)).replace(os.sep, "/")
                if arcname == "mimetype":
                    continue
                zf.write(str(abs_path), arcname)


def find_opf(temp_dir: str) -> str:
    container_path = Path(temp_dir) / "META-INF" / "container.xml"
    if not container_path.exists():
        raise FileNotFoundError("META-INF/container.xml 不存在")
    tree = etree.parse(str(container_path))
    for rf in tree.xpath("//container:rootfiles/container:rootfile", namespaces=NSMAP):
        full_path = rf.get("full-path")
        if full_path:
            return str(Path(temp_dir) / full_path.replace("/", os.sep))
    raise FileNotFoundError("container.xml 中未找到 rootfile")


def opf_dir(opf_path: str) -> str:
    return str(Path(opf_path).parent)
